#!/usr/bin/env python3
"""
wk.py — zero-dependency CLI for the Workato Platform API.

Token resolution (first hit wins):
  1) $WORKATO_API_TOKEN
  2) ~/.config/workato/api_token   (file containing just the token)

Region base URL via --region (default us) or $WORKATO_REGION.

Examples:
  wk.py scope                          # which endpoints this token can hit (200/401/404)
  wk.py recipes --folder 31457942      # list recipes in a folder
  wk.py recipe 73250664 --code         # get a recipe; --code dumps the parsed code JSON
  wk.py jobs 73246557                   # list a recipe's job history
  wk.py job 73246557 j-AaQ3KaaT-...     # one job: lines[].output reveals REAL datapill field names
  wk.py versions 73250664
  wk.py create --name "My recipe" --folder 31457942 --code code.json --config config.json
  wk.py update 73250664 --code code.json
  wk.py start 73250664 / wk.py stop 73250664
  wk.py connections | wk.py folders --parent 31288668 | wk.py projects
  wk.py get  recipes/73250664          # generic passthrough
  wk.py post recipes --data body.json  # generic; --data @file or inline JSON
"""
import argparse, json, os, sys, urllib.request, urllib.error

REGIONS = {
    "us": "https://www.workato.com/api",
    "eu": "https://app.eu.workato.com/api",
    "jp": "https://app.jp.workato.com/api",
    "sg": "https://app.sg.workato.com/api",
    "au": "https://app.au.workato.com/api",
    "il": "https://app.il.workato.com/api",
}

def token():
    t = os.environ.get("WORKATO_API_TOKEN")
    if t:
        return t.strip()
    p = os.path.expanduser("~/.config/workato/api_token")
    if os.path.exists(p):
        return open(p).read().strip()
    sys.exit("No token: set $WORKATO_API_TOKEN or create ~/.config/workato/api_token")

def base():
    return REGIONS.get(os.environ.get("WORKATO_REGION", "us"), REGIONS["us"])

def call(method, path, payload=None, _base=None):
    url = (_base or base()) + "/" + path.lstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        r = urllib.request.urlopen(req, timeout=40)  # 40s = the Workato API's documented request timeout
        return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        # HTTP error WITH a body (4xx/5xx) — return it so callers can inspect the API's error JSON
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        # connection refused / DNS failure / timeout — no HTTP response to return; fail clearly
        sys.exit("Network error reaching %s: %s" % (url, getattr(e, "reason", e)))

def out(status, body, raw=False):
    if raw:
        print(body); return
    try:
        print(json.dumps(json.loads(body), indent=2))
    except Exception:
        print(body)
    if status >= 400:
        sys.stderr.write("\n[HTTP %s]\n" % status)

def load_json_arg(val):
    """Accept a path to a .json file OR an inline JSON string."""
    if val is None:
        return None
    if os.path.exists(val):
        val = open(val).read()
    return json.loads(val)  # validates; raises on bad JSON

def main():
    ap = argparse.ArgumentParser(description="Workato Platform API CLI")
    ap.add_argument("--region", help="us|eu|jp|sg|au|il (default us / $WORKATO_REGION)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scope")
    g = sub.add_parser("get");    g.add_argument("path")
    for m in ("post", "put"):
        p = sub.add_parser(m); p.add_argument("path"); p.add_argument("--data", help="@file or inline JSON")
    d = sub.add_parser("delete"); d.add_argument("path")

    r = sub.add_parser("recipes")
    r.add_argument("--folder"); r.add_argument("--running", action="store_true")
    r.add_argument("--per-page", default="20"); r.add_argument("--page", default="1")
    gr = sub.add_parser("recipe"); gr.add_argument("id"); gr.add_argument("--code", action="store_true")
    j = sub.add_parser("jobs"); j.add_argument("id"); j.add_argument("--per-page", default="10")
    jo = sub.add_parser("job"); jo.add_argument("id"); jo.add_argument("job_id"); jo.add_argument("--outputs", action="store_true")
    v = sub.add_parser("versions"); v.add_argument("id")

    c = sub.add_parser("create")
    c.add_argument("--name", required=True); c.add_argument("--folder", required=True)
    c.add_argument("--code", required=True); c.add_argument("--config", required=True)
    u = sub.add_parser("update")
    u.add_argument("id"); u.add_argument("--name"); u.add_argument("--code"); u.add_argument("--config")
    for verb in ("start", "stop"):
        s = sub.add_parser(verb); s.add_argument("id")
    sub.add_parser("connections")
    f = sub.add_parser("folders"); f.add_argument("--parent")
    sub.add_parser("projects")

    a = ap.parse_args()
    if a.region:
        os.environ["WORKATO_REGION"] = a.region

    if a.cmd == "scope":
        eps = ["recipes?per_page=1", "connections", "folders", "projects",
               "lookup_tables", "properties?prefix=x", "roles", "members",
               "api_collections", "api_clients", "activity_logs?per_page=1", "tags",
               "on_prem_groups", "managed_users"]
        for ep in eps:
            st, body = call("GET", ep)
            print("[%s] %s" % (st, ep.split("?")[0]))
        return

    if a.cmd == "get":      out(*call("GET", a.path)); return
    if a.cmd == "delete":   out(*call("DELETE", a.path)); return
    if a.cmd in ("post", "put"):
        payload = load_json_arg(a.data[1:] if a.data and a.data.startswith("@") else a.data)
        out(*call(a.cmd.upper(), a.path, payload)); return

    if a.cmd == "recipes":
        q = "recipes?per_page=%s&page=%s" % (a.per_page, a.page)
        if a.folder:  q += "&folder_id=" + a.folder
        if a.running: q += "&running=true"
        out(*call("GET", q)); return
    if a.cmd == "recipe":
        st, body = call("GET", "recipes/" + a.id)
        if a.code and st < 400:
            d = json.loads(body)
            print(json.dumps(json.loads(d["code"]), indent=2)); return
        out(st, body); return
    if a.cmd == "jobs":
        out(*call("GET", "recipes/%s/jobs?per_page=%s" % (a.id, a.per_page))); return
    if a.cmd == "job":
        st, body = call("GET", "recipes/%s/jobs/%s" % (a.id, a.job_id))
        if a.outputs and st < 400:
            d = json.loads(body)
            for ln in d.get("lines", []):
                print("== line %s %s.%s ==" % (ln.get("recipe_line_number"), ln.get("adapter_name"), ln.get("adapter_operation")))
                print("  output keys:", list((ln.get("output") or {}).keys()))
            return
        out(st, body); return
    if a.cmd == "versions":
        out(*call("GET", "recipes/%s/versions" % a.id)); return

    if a.cmd == "create":
        code = load_json_arg(a.code)       # validate JSON
        config = load_json_arg(a.config)
        body = {"recipe": {"name": a.name, "folder_id": str(a.folder),  # folder_id MUST be a string
                           "code": json.dumps(code), "config": json.dumps(config)}}  # code/config are JSON STRINGS
        out(*call("POST", "recipes", body)); return
    if a.cmd == "update":
        rec = {}
        if a.name:   rec["name"] = a.name
        if a.code:   rec["code"] = json.dumps(load_json_arg(a.code))
        if a.config: rec["config"] = json.dumps(load_json_arg(a.config))
        if not rec:  sys.exit("update: nothing to change (pass --name/--code/--config)")
        out(*call("PUT", "recipes/" + a.id, {"recipe": rec})); return

    if a.cmd in ("start", "stop"):
        out(*call("PUT", "recipes/%s/%s" % (a.id, a.cmd))); return
    if a.cmd == "connections": out(*call("GET", "connections")); return
    if a.cmd == "folders":
        out(*call("GET", "folders" + ("?parent_id=" + a.parent if a.parent else ""))); return
    if a.cmd == "projects":    out(*call("GET", "projects")); return

if __name__ == "__main__":
    main()

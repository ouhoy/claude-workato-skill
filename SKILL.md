---
name: workato
description: Drive a Workato account via its Platform REST API — inspect, build, fix, debug, and start/stop recipes; read connections, folders, projects, jobs. Use when a task touches a Workato account or recipe.
---

# Workato (Platform API)

Control a Workato account by calling its REST API with a token. This skill bakes in the
endpoint map, the recipe `code` JSON format, and the non-obvious traps that otherwise cost
hours. **Start every task by orienting (token + scope), then use `scripts/wk.py`** — it
encodes the base URL, auth, and the body quirks so you never rewrite curl.

## Setup & orientation (do this first)

- **Token:** `~/.config/workato/api_token` (or `$WORKATO_API_TOKEN`). A `wrkaus-…` prefix = US region.
- **Helper:** `python3 ~/.claude/skills/workato/scripts/wk.py …` (zero deps, stdlib only). Run `wk.py -h`.
- **Optional MCP server:** if a `workato` MCP server is registered, its read + start/stop tools
  also work — use fully-qualified names (`workato:list_recipes`, `workato:get_recipe`,
  `workato:list_connections`, `workato:list_folders`, `workato:list_projects`,
  `workato:list_recipe_jobs`, `workato:start_recipe`, `workato:stop_recipe`, `workato:workato_get`).
  Use them for reads if present, **but for creating/updating recipes use `wk.py`** (the MCP server
  has no write tools). The server is optional — `wk.py` alone covers everything.
- **Always check scope before promising anything:** `wk.py scope`. A token is scoped to one
  API client's role — many resources may be `401`. The token this was built for does
  **recipes (R/W) + jobs + versions + connections + folders + projects**; lookup tables,
  properties, roles, API platform, audit logs, tags, on-prem are typically `401`.

## What you can do (and the command for it)

| Goal | Command |
|---|---|
| See capability surface | `wk.py scope` |
| List recipes / running ones | `wk.py recipes [--folder ID] [--running]` |
| Inspect a recipe (and its code) | `wk.py recipe <id> [--code]` |
| List connections / folders / projects | `wk.py connections` · `wk.py folders [--parent ID]` · `wk.py projects` |
| Debug runs / discover field names | `wk.py jobs <id>` then `wk.py job <id> <job_id> --outputs` |
| See version history | `wk.py versions <id>` |
| Create a recipe (left stopped) | `wk.py create --name N --folder ID --code code.json --config config.json` |
| Update a recipe (must be stopped) | `wk.py update <id> [--name N] [--code code.json] [--config config.json]` |
| Start / stop | `wk.py start <id>` · `wk.py stop <id>` |
| Delete a (scratch) recipe | `wk.py delete recipes/<id>` |
| Anything else | `wk.py get|post|put|delete <path> [--data @file]` |

## Four golden rules (internalize these)

1. **The API stores recipe `code` verbatim and does NOT validate it.** A `{"success":true}`
   write can still be semantically broken (wrong operand key, wrong datapill field, bad input).
   Only the editor/runtime validate. So a created recipe isn't "working" until verified — never
   claim otherwise on the strength of the HTTP 200 alone.
2. **`wk.py start` IS a free validator.** It returns the editor's `code_errors` (invalid
   provider/action names, missing required fields, bad pills) without opening the UI — so
   unknown encodings can be discovered by probe loop on a scratch recipe (recipe-gotchas.md).
   Stop a scratch immediately if it starts and its trigger polls a real source.
3. **Discover real encodings empirically, don't guess.** Field names come from a real job:
   `GET /recipes/:id/jobs/:job_id` → per-step `lines[]` with RESOLVED input/output (unknown
   input keys are silently schema-filtered, so the surviving keys reveal an action's true
   schema). Pill/picklist encodings: build once in the editor and read back.
4. **Validation ≠ runtime.** Pills can validate yet resolve EMPTY (`_dp`+`"first"` trap),
   and runtime-only failures exist (`lookup()` wrong table name, nil-chain errors, Shopify
   "Sold out"/"Record is invalid"). Full verification = start + one real job + inspect the
   created record. Validation errors also hide behind HTTP 200 (`{"success":false,…}`).

## Core workflows

### Inspect / explore an account
`wk.py scope` → `wk.py recipes` / `connections` / `folders` / `projects`. To see how a recipe
ran, list jobs then dump a job. This is read-only and safe.

### Build a recipe
1. Pick a **non-root** folder (`wk.py folders`) and the **connection id** (`wk.py connections`).
2. Write the `code` tree (trigger = step 0; children in `block`) and a `config` array. Follow
   **references/recipe-code-dsl.md** for step structure, control flow (IF/ELSE_IF/ELSE as
   sibling steps, `foreach`/`repeat` loops, `try`/`catch`), the verified condition operand
   table, and datapill encoding. Get connector field names from **references/connectors-gmail.md**
   (or a real job for other connectors).
3. `wk.py create …` (leaves it **stopped**). Read it back: `wk.py recipe <id> --code`.
4. **Verify** before declaring success (golden rule #1): have the user open it in the editor, or
   inspect a job once it runs. Then `wk.py start <id>` when ready.

### Fix / debug a recipe
`wk.py recipe <id> --code` to see the current tree → locate the bad step → fix in a local
`code.json` → `wk.py update <id> --code code.json`. The usual culprits (all in
**references/recipe-gotchas.md**): an invalid operand key (`doesnt_contain` → must be
`not_contains`; full table in the DSL ref), a datapill pointing at a non-existent field
(e.g. `from` instead of `from_email`), or `folder_id`/`code` body-type mistakes on create.
**A fix isn't done at the `update` 200** (golden rule #1): re-read the code, then re-validate
with `wk.py start` and/or one real job before declaring it fixed.

### Trigger timing
Most triggers (Gmail `new_email` included) are **polling**, not real-time; the interval is
plan-gated and **cannot be changed via the API**. Real-time needs a webhook trigger / external
push (Gmail → Pub/Sub). Details in recipe-gotchas.md.

## When to read which reference

- **references/recipe-code-dsl.md** — building/fixing recipe `code`: step keywords, control
  flow (IF/ELSE, `foreach`/`repeat` loops, `try`/`catch`), the verified operand table, datapill
  formats (incl. the **array-pill validation-vs-runtime
  table**, **`=` formula mode** for non-first elements/ternaries/`lookup()`, list
  **`.where(field:'val')` filtering + the backward-compatible null-safe guard** for the
  `[0]['x']`-on-nil crash, the **DB batch-insert `rows`/`____source` shape**, the
  extended-schema rules, formula conditions, and the `stop` step), a full worked example.
  *Read this for any build-or-fix task.*
- **references/recipe-gotchas.md** — before any create/update: the verbatim-storage trap, the
  **start-as-validator probe loop**, job `lines[]` debugging (incl. `?include_payloads=true`
  and the **try/catch-hides-failure** trap — job `succeeded` while the source system shows
  FAILED), **editing a live recipe safely** (backup → leaf-diff assert → stop/update/start →
  rollback → re-test), forcing an immediate poll (stop+start), editor re-save rewrites,
  `folder_id`-string / `code`-string rules, field discovery, polling vs real-time.
- **references/connectors-utilities.md** — verified encodings for **json_parser** (parse a
  JSON-string output into pills; `document` root + labeled-schema traps), **logger**
  (`log_message` as a pill-resolution probe), **lookup tables** (the `lookup()` formula vs
  the half-mapped `lookup_table` connector; API is 401 — tables are UI-maintained).
  *Read this whenever a connector returns JSON as a string, or a mapping needs a lookup table.*
- **references/api-endpoints.md** — exact endpoints, regions, rate limits, the broader (often
  `401`) API surface, the error model, and how to widen token scope.
- **references/connectors-gmail.md** — Gmail `new_email` outputs + `send_mail` inputs.
- **references/connectors-orderful-shopify.md** — inbound-EDI playbook: Orderful → Workato →
  Shopify (Walmart 850 PO → Shopify draft order). The poller-bucket **routing trap**
  (Orderful Communication Channels, UI-only — recipe gets 0 jobs if inbound isn't routed to a
  POLLER channel), the bucketId trailing-space bug, the Orderful poller trigger + `get_record`
  (returns the parsed message as a JSON **string** → json_parser), Shopify
  `create_draft_order` (full verified input incl. addresses/note, the
  extended_input_schema requirement, `province`/`country` naming, "Sold out" /
  "Record is invalid" causes) and `search_product` (handle-only lookup → handle=UPC
  convention), the **three-tier item matching** pattern (Shopify → lookup table → stop with
  details), how to inject a test 850, and the full proven recipe with mapping formulas.
  *Read this for any Orderful/EDI-inbound recipe or Shopify draft-order action.*
- **references/connector-sdk.md** — the boundary case: a task needs a **connector** built or
  changed (not a recipe). This skill can't do that — connectors are authored with the Ruby
  **Workato Connector SDK** (`workato new/exec/push`). *Read this only when no connector
  exists for the app, or you must edit a custom connector's internals; for recipes, stay here.*

## Not the same as Workato's hosted MCP

This skill calls the **Workato REST API** with your own token from local scripts (deterministic,
endpoint-shaped). Workato also offers **Remote MCP servers** — Workato *hosts* an MCP server that
exposes selected recipes as LLM tools at a `https://<instance>.apim.mcp.workato.com/…?wkt_token=…`
URL you'd add as a Claude connector. That's a different, LLM-tool-shaped surface. Don't conflate
them: for "use my token to build/fix/inspect recipes," use this skill.

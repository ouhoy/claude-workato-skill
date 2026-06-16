# Workato Platform (Developer) API — Endpoint Reference

All paths are relative to the regional base URL. Auth header on **every** request:
`Authorization: Bearer <token>`. Responses are JSON. Request timeout is **40s**.

> Use `scripts/wk.py` for everything here — it already encodes the base URL, auth,
> and the create/update body quirks. Raw paths are documented so you can use the
> generic `wk.py get|post|put|delete <path>` passthrough when no convenience subcommand exists.

## Contents
- Base URLs by region · Auth model & token scope (read first) · Rate limits
- Recipes (+ create/update body rules) · Jobs · Versions · Connections / Folders / Projects
- Broader API surface (locked for this token's role) · Error & status model

## Base URLs by region (data center)

| Region | Base URL |
|---|---|
| US (default) | `https://www.workato.com/api` |
| EU | `https://app.eu.workato.com/api` |
| JP | `https://app.jp.workato.com/api` |
| SG | `https://app.sg.workato.com/api` |
| AU | `https://app.au.workato.com/api` |
| IL | `https://app.il.workato.com/api` |
| KR | `https://app.kr.workato.com/api` |
| CN | `https://app.workatoapp.cn/api` |
| Dev sandbox / trial | `https://app.trial.workato.com/api` |

A `wrkaus-…` token prefix → **US**. (`wrkeus-`→EU, etc.) `wk.py --region <us|eu|…>` or `$WORKATO_REGION` selects the host.

**Legacy auth removed:** the old `x-user-token` + `x-user-email` API-key pair was deprecated 2025-07-14 and **fully removed 2025-10-14**. Only Bearer tokens work now.

## Auth model & token scope (READ THIS FIRST)

A token belongs to **one API client**, scoped to **one environment** and a set of **client-role privileges**. An endpoint outside the role's privileges is rejected even though the token is valid. So the realistic capability surface is whatever the client role grants — **probe it, don't assume**:

```
python3 scripts/wk.py scope
```

The token this skill was built against is a **recipe-focused** role. Its observed matrix:

| ✅ 200 (granted) | 🔒 401 (role lacks privilege) |
|---|---|
| `recipes` (R + **W**), `recipes/:id/jobs`, `recipes/:id/versions`, `connections`, `folders`, `projects` | `lookup_tables`, `properties`, `roles`, `members`, `api_collections`/`api_clients`/`api_endpoints`, `activity_logs`, `tags`, `on_prem_groups`, `managed_users`, `custom_oauth_profiles` |

To **widen scope**: Workspace admin → **API clients** → edit the **client role** (check more privilege groups) or broaden the client's project/environment assignment. Changes take effect immediately (no token re-mint). Re-minting (`refresh_secret`) only invalidates the old token.

## Rate limits

- Most endpoints: **60 req/min**.
- **Recipe creation, connection writes, lookup-table writes: 1 req/sec** (throttle creates!).
- High-volume reads (Genies/KB/Skills): 1000 req/min. Package imports: 500/hour/user.
- `429` carries `Retry-After` + `X-Rate-Limit-Remaining` — back off accordingly.

---

## Recipes  — privilege: granted by this token

| Method | Path | Key params / body | Notes |
|---|---|---|---|
| GET | `/recipes` | `folder_id`, `adapter_names_all[]`/`adapter_names_any[]`, `order`, `running`, `since_id`, `page`, `per_page` | List. `wk.py recipes [--folder ID] [--running]` |
| GET | `/recipes/:id` | — | Full recipe. `code` & `config` come back as **JSON strings** — parse them. `wk.py recipe <id> [--code]` |
| POST | `/recipes` | `{"recipe":{name, code, config, folder_id}}` | **Create.** See body rules below. `wk.py create` |
| PUT | `/recipes/:id` | `{"recipe":{name?, code?, config?}}` | **Update.** Recipe must be **stopped**. `wk.py update` |
| POST | `/recipes/:id/copy` | `{folder_id?}` | Duplicate |
| DELETE | `/recipes/:id` | — | Delete |
| PUT | `/recipes/:id/start` | — | Start (go live). `wk.py start` |
| PUT | `/recipes/:id/stop` | — | Stop. `wk.py stop` |

### Create/Update body rules (the gotchas that cost us hours — see recipe-gotchas.md)

- **`code` and `config` MUST be JSON-encoded *strings*, not raw objects.** `wk.py` does `json.dumps()` for you.
- **`folder_id` MUST be a *string*** (`"31457942"`), and **cannot be the root folder** ("can't be assigned to the root folder").
- On success POST returns `{"success":true,"id":<new_id>}`; PUT returns `{"success":true}`. New recipes start **stopped** (`running:false`).
- Validation failures come back as **HTTP 200** with `{"success":false,"errors":{…}}` — *always inspect the body, not just the status.*

## Jobs  — privilege: granted

| Method | Path | Notes |
|---|---|---|
| GET | `/recipes/:id/jobs` | `?per_page=N`. Returns `items[]` with job ids/status/timestamps + counts. `wk.py jobs <id>` |
| GET | `/recipes/:id/jobs/:job_id` | **Goldmine for authoring:** `lines[]` each has `adapter_name`, `adapter_operation`, `input`, **`output`** — the real datapill field names a connector emits. Use `wk.py job <id> <job_id> --outputs` to dump output keys per line. This is how we discovered Gmail's `from_email`/`body_plain` etc. |

## Versions  — privilege: granted

| Method | Path | Notes |
|---|---|---|
| GET | `/recipes/:id/versions` | `{"data":[{id, version_no, comment, created_at, author…}]}`. `wk.py versions <id>` |

## Connections / Folders / Projects — privilege: granted

| Method | Path | Notes |
|---|---|---|
| GET | `/connections` | `[{application, id, name, …}]`. The `id` is the `account_id` you reference in a recipe's `config`. `wk.py connections` |
| GET | `/folders` | `?parent_id=ID` to list children; paginated. `wk.py folders [--parent ID]` |
| POST | `/folders` | `{folder:{name, parent_id}}` (create) |
| GET | `/projects` | `[{id, folder_id, …}]`. `wk.py projects` |

---

## Broader API surface (present in the API, but 🔒 for this token's role)

Each needs its own client-role privilege. Documented here so you know they exist and the exact paths once the role is widened. (Cite docs.workato.com/workato-api/* for details.)

| Resource | Representative endpoints | Privilege |
|---|---|---|
| Lookup tables + rows | `GET/POST /lookup_tables`; `GET/POST /lookup_tables/:id/rows`; `GET /lookup_tables/:id/lookup`; `PUT/DELETE …/rows/:row_id` | Lookup tables |
| Environment properties | `GET /properties?prefix=…`; `POST /properties` (upsert hash; ≤1000/env) | Env properties |
| Members / roles | `GET /members`, `GET /members/:id/privileges`, `POST /member_invitations`, `PUT/DELETE /members/:id` | Collaborators (needs DEV env) |
| API platform | `GET/POST /api_collections`; `GET /api_endpoints`, `PUT /api_endpoints/:id/enable\|disable`; `GET/POST /api/v2/api_clients`; `…/api_keys` | Collections/Clients/etc. |
| Activity audit logs | `GET /activity_logs` (filter by resource/event/user/date) | Audit logs |
| Tags | `GET/POST /tags`, `PUT/DELETE /tags/:handle` | Tags |
| On-prem groups/agents | `GET/POST /on_prem_groups`, `/on_prem_agents`, `…/:id/status` | On-prem |
| Event streams | `GET/POST /event_streams/topics`; `POST /api/v1/topics/:id/publish\|consume` | Event streams |
| Custom OAuth profiles | `GET/POST /custom_oauth_profiles` | Custom OAuth |
| **Recipe lifecycle / packages** | `POST /packages/export/:manifest_id` → poll `GET /packages/:id` → `GET /packages/:id/download`; import `POST /packages/import/:folder_id` (body = `application/octet-stream` zip; params `restart_recipes`, `include_tags`) | Lifecycle/packages |
| Test automation | `POST /test_cases/run_requests` (async) → `GET /test_cases/run_requests/:id`; `GET /recipes/:id/test_cases` | Test automation |

Common data models have a *privilege* but **no dedicated REST resource** — they move between environments via packages.

---

## Error & status model

| Code | Meaning |
|---|---|
| **401** | Missing/invalid/expired token, **or** the client role grants no access to that resource family at all. (Most "denied" cases here.) |
| **403** | Authenticated and resource in scope, but the role lacks the specific privilege for *that action* (e.g., read ok, write denied), or wrong project/environment. |
| **404** | Resource id doesn't exist — or the path isn't a real endpoint in this API version. |
| **400** | Malformed request. Envelope `{"errors":[{"code","title"}]}`. |
| **200 + `{"success":false,"errors":{…}}`** | Semantic/validation failure on write endpoints (recipes, lookup rows, properties). **Inspect the body — status alone lies.** |
| **429** | Rate limited; honor `Retry-After`. |

`x-correlation-id` is returned on responses for support/tracing.

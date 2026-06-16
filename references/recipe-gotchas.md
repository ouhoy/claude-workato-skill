# Recipe API Gotchas & Hard-Won Lessons

These are the things that silently break recipe automation. Most were learned the
painful way — read them before creating/editing recipes.

## Contents
- The #1 rule: API stores `code` verbatim (no validation)
- `start` IS a free validator (API-only probe loop) · Validation ≠ runtime
- Reading a job step-by-step · try/catch hides failure
- Forcing an immediate poll · Editor re-saves rewrite your code
- Discovering correct encodings (build-in-UI-then-read-back)
- Create / update body quirks · Editing a LIVE recipe safely
- Step identity (`as`/`uuid`) · Condition operands · Triggers are polling
- Multi-tenant customers (dev/test + prod) · Misc

## The #1 rule: the API stores recipe `code` verbatim — it does NOT validate it

`POST`/`PUT /recipes` will happily accept and store a recipe whose datapill field
names are wrong, whose condition operand keys are invalid, or whose connector inputs
are malformed. You get `{"success":true}` and a recipe that is **semantically broken**.
Only the **recipe editor** (and runtime) validate pills/operands/fields.

**Consequence:** a "successful" API write is necessary but NOT sufficient. To know a
recipe actually works you must either (a) open it in the editor (it flags bad pills/
operands), or (b) let it run and inspect a job. Plan for a verification step; never
report a created recipe as "working" on the strength of the API 200 alone.

## `start` IS a free validator — the API-only probe loop

`PUT /recipes/:id/start` returns the editor's validation errors as
`{"success":false,"code_errors":[[<step>, [[field, value, message, …]]], …]}` — without
the UI. This enables a fully API-side discovery loop (proven across a whole session):

1. **Create a scratch recipe** (any known-good trigger; it stays stopped) in a real folder.
2. Guess `provider`/`name`/input keys → `update` → `start` → read errors:
   - `["provider","X","is invalid"]` → wrong connector id; try the next candidate.
   - `["name","X","is invalid"]` → connector exists, wrong action name.
   - `["<Label>",null,"can't be blank","<field>"]` → action exists; that field is required.
   - `Unknown data field "…"` → pill/schema problem (see recipe-code-dsl.md).
   - **`success:true` (it started)** → structurally valid. STOP IT immediately if its
     trigger polls a real source (it will race the production recipe for the same bucket).
3. **Runtime discovery** still needs one real job: job line `input` shows the
   post-schema-filter input (unknown keys silently dropped — the surviving keys ARE the
   action's real input schema) and `output` shows the real output shape.
4. Delete the scratch when done: `wk.py delete recipes/<id>`.

Names discovered this way live in connectors-utilities.md and
connectors-orderful-shopify.md — check there before re-probing.

## Validation ≠ runtime (both directions)

`start` succeeding does NOT mean pills resolve: `_dp` paths with `"first"` validate but
resolve empty at runtime; only the dotted `#{_('…first…')}` form (or `=` formulas) does
both. And runtime errors exist that validation can't see: `lookup()` with a wrong table
name, missing intermediate nodes (`no method '[]' for nil`), Shopify "Sold out"/"Record
is invalid". **Full verification = start + one real job whose draft/record you inspect.**

## Reading a job step-by-step

`GET /recipes/:id/jobs/:job_id` → `lines[]`, one per step, each with
`recipe_line_number`, `adapter_name`, `adapter_operation`, **`input` (post-resolution,
post-schema-filter)**, `output`, `error`. This is the single most informative debugging
artifact — it shows exactly what a step received and returned. (`wk.py job <id> <job_id>
--outputs` prints only output keys; fetch the raw endpoint for values.)

Fetch resolved per-line input/output (values, not just keys) with `?include_payloads=true`:
```
wk.py get "recipes/<id>/jobs/<job_handle>?include_payloads=true"
```
Useful fields per line: `output.error`, an insert's `output.keys_count` (rows actually
written), and a `return_response` step's `output.http_status_code` (what the caller received).

## try/catch hides failure — a job shows `succeeded` while a step errored

If a recipe wraps its work in `try`/`catch` and the `catch` returns a response (instead of
re-raising), the **job status is `succeeded` even though the `try` block caught a real
error**. Never trust the top-level status alone:
- The `try` line's `output` carries an **`error`** key — the caught message (e.g. a mapping
  `no method '[]' for nil`). Inspect it.
- The downstream caller sees the catch's response, not a Workato failure. Example: an
  Orderful transaction the recipe was fulfilling shows **`deliveryStatus: FAILED`** while
  Workato reports the job "succeeded". **Cross-check the source system's status**, not just Workato's.

## Forcing an immediate poll

Polling intervals are plan-gated (30 min floor seen on trial), but **stop + start makes
the trigger poll immediately** — the standard test loop is: inject/produce the inbound
event → wait for it to reach the source → stop+start the recipe → watch for the new job.
Restarting does NOT re-deliver already-consumed events (cursor in `trigger_closure` is
kept), so re-tests need a fresh event (e.g. new PO number).

## Editor re-saves rewrite your code

When a user opens and saves the recipe in the UI: dotted formula pills are normalized to
`_dp`+`{"path_element_type":"current_item"}` form (harmless), and **they may introduce
placeholder values** (a real failure came from `"-"` placeholders in address fields →
Shopify "Record is invalid"). After any user edit, re-read the code (`wk.py recipe <id>
--code`) before patching — never push a stale local copy over their changes.

## Discovering correct encodings: build-in-UI-then-read-back

The most reliable way to learn the exact JSON a connector expects (operand keys,
datapill encoding, picklist selections, connector-specific input shapes) is:

1. Build the step once in the Workato editor.
2. `GET /recipes/:id` and parse `code` — copy the exact structure the editor produced.

Corollary for **field names**: a recipe that has already *run* exposes the real
datapill field names a trigger/action emits in its job output:

```
python3 scripts/wk.py job <recipe_id> <job_id> --outputs
```

This is how we learned Gmail's `new_email` exposes `from_email`, `body_plain`,
`subject`, `snippet` (and has **no** bare `from` field — the raw sender lives under
`payload.headers[]`). Never guess connector field names; read them from a real job.

## Create / update body quirks

- **`code` and `config` must be JSON-encoded STRINGS**, not raw JSON objects, inside
  the `{"recipe":{…}}` body. (`wk.py` serializes them for you.)
- **`folder_id` must be a STRING** — `"31457942"`, not `31457942`. Passing an int returns
  `400 Invalid parameter 'folder_id' … Must be a String`.
- **`folder_id` cannot be the account root** — `"can't be assigned to the root folder"`.
  Use a real project/sub-folder id (`wk.py folders`).
- **Updates require the recipe to be STOPPED.** Stop → PUT → (optionally) start.
- **Validation errors arrive as HTTP 200** with `{"success":false,"errors":{…}}`. Inspect
  the body. The `errors` map names exactly what's wrong (e.g. `{"code":["can't be blank"]}`).

## Editing a LIVE (running) recipe safely

Patching a recipe that's running and serving real traffic is a production deploy — do it defensively:

1. **Back up first:** `wk.py get recipes/<id> > backup-<id>-<ts>.json` (full recipe incl. `code`/`config`).
2. **Assert the edit is surgical before mutating:** diff the new `code` tree against the
   backup at the leaf level and confirm **only the intended leaves changed** — a stray edit
   to another formula is how you silently break the working path. Abort if the changed-leaf
   count ≠ what you intended.
3. **stop → update → start.** `start`'s `code_errors` is the syntax gate.
4. **Auto-rollback on failure:** if `start` returns `code_errors` or the recipe isn't
   `running` afterward, immediately re-`update` with the backup and `start`. Never leave a
   live recipe stopped or broken.
5. **Re-test with real data** — `start` validates syntax, not runtime; a formula change only
   proves out on a real job (re-trigger the event, inspect the new job per the try/catch gotcha).

"Backward-compatible" for a shared recipe = previously-working inputs produce **byte-identical**
output; guard so the new branch fires only on the previously-failing case (e.g. `||` fallbacks
that short-circuit when the original path resolves).

## Step identity: `as` and `uuid`

Every step needs a unique **`as`** (the alias datapills reference — an 8-char hex-ish
string like `4a974807`) and a **`uuid`** (a v4 GUID). When hand-authoring `code`, assign
distinct `as` values and generate real uuids. The trigger is always `number: 0`. Datapills
reference a producing step by its `as` (see recipe-code-dsl.md).

## Condition operands

- The positive keys `contains`, `equals`, `present`, `starts_with`, `ends_with` are
  confirmed from real exported recipes.
- **`doesnt_contain` is WRONG** — the editor rejects it (leaves the operator blank →
  "Condition is invalid"). For the verified negation keys, see **recipe-code-dsl.md**.
- If you're ever unsure of an operand key, fall back to build-in-UI-then-read-back.

## Triggers are polling, not instant (and you can't fix that via the API)

Most app triggers (Gmail `new_email` included) are **polling** — they re-query on a
schedule, they are NOT real-time. Signs in the recipe object: `webhook_url: null` and a
`trigger_closure` with a `q`/`after:` cursor.

- The polling interval is **plan-gated** (Community/Base ≈10 min, Professional+ ≈5 min,
  trial/sandbox longer — ~30 min). It is set in the recipe editor's trigger settings and
  **cannot be lowered below the plan floor**.
- There is **no polling-interval field on the recipe API object** — you cannot change it
  programmatically. Tell the user to set it in the editor.
- True real-time requires a **webhook trigger** (apps that support it show "REAL TIME").
  Gmail has none natively; real-time Gmail needs Gmail API `watch` → Google Cloud Pub/Sub
  → a Workato webhook trigger (and the `watch` expires every 7 days).

## Multi-tenant customers: dev/test + prod are SEPARATE Workato tenants

Larger Orderful+Workato customers often run **two separate Workato tenants** (dev/test and
prod), each with its **own API token, own project/folder IDs, and own recipe IDs**. Smaller
ones run a **single tenant** that switches environment via **account properties** (e.g. a
DB-library or an "Orderful Stream" property the recipes read) rather than separate instances.

- **Recipe IDs are NOT stable across tenants** — when promoting or diffing dev→prod, **match
  recipes by NAME, not by id**. The same logical recipe has a different id in each tenant.
- The Orderful connection inside Workato is named **`orderful_connector_<org-digits>_<digits>`**;
  the org digits should correspond to the Orderful org the API key belongs to — a mismatch
  means the recipe is wired to the wrong Orderful environment.
- Record per-tenant key IDs (project, EDI in/out folders, Orderful connection id) up front —
  you need them for every cross-tenant diff.

## Misc

- **Recipe creation is rate-limited to 1 req/sec** — throttle batch creates.
- Region matters: a `wrkaus-` token only works against `https://www.workato.com/api`.
- Account/user endpoints (`users/me`, `account`) and most non-recipe resources are likely
  `401` for a recipe-scoped token — see api-endpoints.md and run `wk.py scope` first.

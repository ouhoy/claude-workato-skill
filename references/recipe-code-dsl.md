# Recipe `code` JSON DSL — Authoring Reference

How to hand-write the `code` a recipe needs (the thing `POST/PUT /recipes` stores).
This is the highest-value reference for **building** recipes. Pair it with
recipe-gotchas.md (the API stores this verbatim and does NOT validate it).

## Contents
- Top-level shape · Step fields
- Control flow — IF / ELSE_IF / ELSE (separate sibling steps); foreach / repeat / try-catch
- Conditions + verified operand keys
- Datapills — array-pill validation-vs-runtime; `=` formula mode (+ allowlisted-Ruby & converters); `.where()` filtering + null-safe guard; DB batch-insert `rows`/`____source`; extended schemas; formula conditions; `stop` step
- Worked example — Gmail "Hello auto-responder"

## Top-level shape

`code` is a **single nested tree**, not a flat list. Step `0` is always the **trigger**;
every other step lives inside its parent's `block` array.

```jsonc
{
  "number": 0, "provider": "gmail", "name": "new_email", "as": "7a000001",
  "keyword": "trigger",
  "dynamicPickListSelection": { "label_ids": "INBOX" },
  "input": { "label_ids": "INBOX" },
  "block": [ /* child steps … */ ],
  "uuid": "…"
}
```

`config` (separate field) lists the connections the recipe uses:
```json
[{"keyword":"application","name":"gmail","provider":"gmail","skip_validation":false,"account_id":12345678}]
```
`account_id` is a connection `id` from `GET /connections`.

## Step fields

| Field | Meaning |
|---|---|
| `number` | integer ordinal, unique, ascending in document order; trigger = `0` |
| `keyword` | step type: `trigger`, `action`, `if`, `else_if`, `else`, `foreach`, `repeat`, `while_condition`, `try`, `catch`, `stop`, `return` |
| `provider` | connector id (`gmail`, `clock`, `logger`, `netsuite`, `workato_variable`, …) — on action/trigger steps |
| `name` | the connector operation id (`new_email`, `send_mail`, `create_record`, …) |
| `as` | **step alias** — datapills reference a step's output by this. 8-char hex-ish (`7a000001`). Must be unique. |
| `uuid` | per-step v4 GUID — generate one per step |
| `input` | object of field→value (values are plain strings or datapill strings, see below) |
| `dynamicPickListSelection` | records picklist label choices (mirror keys of `input` that are picklists) |
| `block` | array of child steps (the sole nesting mechanism) |
| `title` / `description` | optional labels (often `null`) |
| `skip` | `true` disables the step + its block |

Loop/control extras seen on real steps: `source` (list pill a `foreach` iterates),
`repeat_mode` (`simple`/`batch`/`null`), `batch_size` (string), `clear_scope`, and a
per-step `filter` object (same shape as a condition — gates whether the step runs).

## Control flow

### IF / ELSE IF / ELSE are SEPARATE SIBLING steps

There is **no `else` block inside an `if` step**. The `if` step holds its condition in
`input` and its "then" branch in `block`; the `else_if`/`else` steps follow it **as
siblings** in the same parent `block`, evaluated in `number` order, first match wins.

```jsonc
"block": [
  { "number": 1, "keyword": "if",
    "input": { "type":"compound","operand":"and","conditions":[ /* … */ ] },
    "block": [ /* then-steps */ ], "uuid":"…" },
  { "number": 4, "keyword": "else_if",
    "input": { "type":"compound","operand":"and","conditions":[ /* … */ ] },
    "block": [ /* … */ ], "uuid":"…" },
  { "number": 7, "keyword": "else",
    "block": [ /* else-steps */ ], "uuid":"…" }
]
```

Two independent `if` steps as siblings (each re-checking a gate) is also valid and
sometimes clearer — that's the pattern in the Gmail example below.

### foreach / repeat / try-catch

- `foreach`: block-owning; `source` = the list datapill, `repeat_mode`+`batch_size` for batching.
- `repeat`: block-owning; the loop test is a **child `while_condition`** step whose `input`
  is a compound condition (same shape as `if`).
- `try`/`catch`: siblings. `catch.input` has `max_retry_count`/`retry_interval`; `stop` is a
  leaf with `input.stop_with_error` + `stop_reason`.

## Conditions (the `input` of `if`/`else_if`/`while_condition`)

```json
{ "type": "compound", "operand": "and",
  "conditions": [
    { "operand": "contains", "lhs": "<datapill or literal>", "rhs": "<value>" }
  ] }
```
- Outer `operand` joins conditions: `"and"` or `"or"`.
- Each condition is `{operand, lhs, rhs}`. `lhs` is typically a datapill; `rhs` a literal
  (or another pill).

### Verified operand keys (UI label → JSON `operand`)

| UI label | `operand` |
|---|---|
| Contains | `contains` |
| **Doesn't contain** | **`not_contains`** |
| Starts with | `starts_with` |
| Doesn't start with | `not_starts_with` |
| Ends with | `ends_with` |
| Doesn't end with | `not_ends_with` |
| Equals | `equals_to` |
| Doesn't equal / is not | `not_equals_to` |
| Greater than | `greater_than` |
| Less than | `less_than` |
| Is true | `is_true` |
| Is not true | `is_not_true` |
| Is present | `present` |
| Is not present (blank) | `blank` |

Notes:
- `not_contains` is correct; **`doesnt_contain`/`does_not_contain` are WRONG** (editor rejects them).
- Real exports use **`equals_to`** for "Equals" (some recipes show a bare `equals` — treat
  `equals_to` as canonical; `present` not `is_present`).
- **Unary** operators (`is_true`, `is_not_true`, `present`, `blank`) still need an `rhs` key —
  set it to `""`.

## Datapills (referencing another step's output inside `input` values)

A datapill always points at a producing step **by that step's `as`**, then drills into
fields. Two encodings, both work:

**A. Formula form** (human/text/formula inputs) — what we used successfully; binds in the editor:
```
#{_('data.<provider>.<step_as>.<field>')}
e.g.  #{_('data.gmail.7a000001.from_email')}
```

**B. Export form** (`_dp`) — canonical in API exports; use for complex/list pills:
```
#{_dp('{"pill_type":"output","provider":"gmail","line":"7a000001","path":["from_email"]}')}
```
Here **`line` === the source step's `as`**; `path[]` walks into nested objects/list items.

Either form embeds inside a normal string value (e.g. `"body": "Hi #{_('data.gmail.7a000001.from_email')}"`).

### Pills into ARRAYS — validation vs runtime DISAGREE (verified the hard way)

For a path that crosses arrays (e.g. parsed EDI: `transactionSets[0].PO1_loop[0]…`):

| Encoding | Validation (`start`) | Runtime |
|---|---|---|
| `_dp` path with `"first"` tokens: `["document","transactionSets","first","PO1_loop","first",…]` | ✅ passes | ❌ resolves **EMPTY STRING** |
| `_dp` path with integer `0` | ❌ "Invalid path element" | — |
| `_dp`/dotted path with `"0"` string or no index token | ❌ "Unknown data field" | — |
| Dotted formula form `#{_('data.json_parser.<as>.document.transactionSets.first.<…>.first.<field>')}` | ✅ passes | ✅ **RESOLVES** |
| Anything `[1]` / `.last` in text mode | ❌ rejected | — |

So: **first-element access → dotted `#{_('…first…')}` form.** It still hard-errors at
runtime if an intermediate node is missing (`no method '[]' for nil` fails the job).

The editor, on re-save, normalizes dotted pills to `_dp` with
`{"path_element_type":"current_item"}` index tokens — that's the canonical editor
encoding; leave it alone when editing user-touched recipes.

### Formula mode — full-field `=` values (non-first elements, ternaries, lookup())

A field whose **entire value starts with `=`** is a formula: real Ruby-ish chains that
both validate AND resolve:
```
=_dp('{"pill_type":"output","provider":"json_parser","line":"aa000001","path":["document","transactionSets"]}').first['PO1_loop'][1]['baselineItemData'][0]['quantity']
```
Verified working inside `=` formulas: `[1]` integer indexing, `['key']` access, `.first`,
`.present?`, ternary `cond ? a : b`, `+` string concatenation, and
`lookup('table_name', 'col': value)['col']` (see connectors-utilities.md).
A Ruby chain inside `#{…}` instead gets rejected: *"not allowed in text mode. Please use
formula mode for such expressions."* — that error means "make the whole value a `=` formula".

### Formulas are an allowlist of Ruby — not arbitrary Ruby

Workato formulas are a **curated allowlist of Ruby methods**, not the whole language — a method
that exists in Ruby may still be rejected, so don't assume one is available. When unsure, the
`start`-as-validator probe loop (recipe-gotchas.md) settles it. Verified-safe and commonly useful:

- **Guards/presence:** `.present?`, `.blank?`, `.presence` (the nil-guarding above).
- **String:** `.strip`, `.upcase`/`.downcase`, `.capitalize`/`.titleize`, `.gsub`/`.sub`,
  `.split`/`.join`, `.ljust`/`.rjust` (pad fixed-width EDI codes), `.to_i`/`.to_f`/`.to_s`.
- **Workato-specific converters you wouldn't guess** (handy for address/locale mapping):
  `.to_state_code`/`.to_state_name`, `.to_country_alpha2`/`.to_country_alpha3`/`.to_country_name`,
  `.to_currency`/`.to_currency_code`, `.to_phone`, `.ordinalize`, `.parameterize`.

### List `.where(field: 'value')` filtering — and the nil-crash it causes

DB insert/batch steps usually map each column with a `=` formula that filters a list pill:
```
=_dp('{… "path":[…,"baselineItemData"]}').where(productServiceIDQualifier: 'SK')[0]['productServiceID']
```
`.where(key: 'val')` filters a list of hashes; `[0]` takes the first match; `['field']` reads it.

**Trap — `no method '[]' for nil`:** this hard-errors (and fails the job) when the filter
matches nothing (e.g. a different trading partner tags the same datum with a different
qualifier) OR the source segment is absent — `[0]` becomes `nil` and `nil['field']` raises.
A formula authored/tested against ONE partner's payload routinely breaks on another's.

**Backward-compatible null-safe guard** — identical output when the original path resolves
(the `||` short-circuits, so the working case is byte-for-byte unchanged), graceful `nil`
otherwise:
```
=((<DP> || []).where(key: 'val')[0] || (<DP> || [])[0] || {})['field']
```
- `(<DP> || [])` stops `.where` being called on `nil` (absent segment).
- `|| (<DP> || [])[0]` — optional fallback to the first element when the filter misses
  (omit it for pure null-safety with no fallback).
- `|| {}` makes the trailing `['field']` safe → yields `nil` instead of crashing.

`||`, `[]` and `{}` literals are all accepted in `=` formula mode.

### DB batch-insert input shape: `rows` object + `____source`

A batch insert (`insert_rows_batch`) carries `input.rows` as a **single object** — each key
is a destination column, each value a formula — plus a special **`____source`** key holding
the **list pill to iterate**. Each column formula is evaluated once per `____source`
element, referencing the current element via `{"path_element_type":"current_item"}` inside
its `_dp` path. (So one nil-guard on a column formula protects every row in the batch.)
Watch for **two batch-inserts into the same table** — both fire and you get duplicate rows;
check for a stale/leftover second insert before assuming a single mapping owns the table.

### Schemas gate pill validation — `extended_output_schema` / `extended_input_schema`

`start`-time pill validation resolves field names against the **schemas stored in the
recipe code**, not against the live connector:
- A pill into step X validates only if X (or the trigger) carries an
  `extended_output_schema` declaring that field — **every node needs a `label`** or you
  get `Unknown data field "<Humanized name>"`. If you rewrite a step and drop its schema,
  previously-valid pills break.
- Conversely, **action input keys are silently schema-filtered at runtime**: optional
  fields you add to `input` are DROPPED unless declared in the step's
  `extended_input_schema` (discovered with Shopify `create_draft_order`: note/email/
  addresses vanished until the input schema declared them). If a job's line `input`
  shows fewer keys than your code sends, this is why.

### Conditions accept `=`-formula lhs

```json
{"operand":"blank", "lhs":"=_dp('…["products"]').first", "rhs":""}
{"operand":"blank", "lhs":"=lookup('shopify_items', 'upc': <expr>)", "rhs":""}
```
Both validated and ran (used for found-in-Shopify / found-in-lookup-table gates).

### `stop` step — verified encoding

```json
{ "number":6, "keyword":"stop", "as":"ff000001s",
  "input": { "stop_with_error": "true",
             "stop_reason": "='ITEM NOT FOUND. PO=' + <expr> + ' | UPC=' + <expr>" },
  "uuid":"…" }
```
`stop_reason` may be a full `=` formula → dynamic error messages with pill data. The
reason becomes the failed job's top-level `error`.

## Worked example — Gmail "Hello auto-responder" (two sibling IFs)

Trigger on new INBOX email; if from a sender AND body contains "Hello" → reply A; if from
that sender AND body does **not** contain "Hello" → reply B. (Static action text → only the
conditions use pills.)

```jsonc
{
  "number":0,"provider":"gmail","name":"new_email","as":"7a000001","keyword":"trigger",
  "dynamicPickListSelection":{"label_ids":"INBOX"},"input":{"label_ids":"INBOX"},
  "block":[
    { "number":1,"keyword":"if","as":"7a000002",
      "input":{"type":"compound","operand":"and","conditions":[
        {"operand":"contains","lhs":"#{_('data.gmail.7a000001.from_email')}","rhs":"you@example.com"},
        {"operand":"contains","lhs":"#{_('data.gmail.7a000001.body_plain')}","rhs":"Hello"}]},
      "block":[ {"number":2,"provider":"gmail","name":"send_mail","as":"7a000003","keyword":"action",
        "input":{"email_type":"text","to":"you@example.com","subject":"Hello back!","body":"hello back"},
        "uuid":"…"} ], "uuid":"…" },
    { "number":3,"keyword":"if","as":"7a000004",
      "input":{"type":"compound","operand":"and","conditions":[
        {"operand":"contains","lhs":"#{_('data.gmail.7a000001.from_email')}","rhs":"you@example.com"},
        {"operand":"not_contains","lhs":"#{_('data.gmail.7a000001.body_plain')}","rhs":"Hello"}]},
      "block":[ {"number":4,"provider":"gmail","name":"send_mail","as":"7a000005","keyword":"action",
        "input":{"email_type":"text","to":"you@example.com","subject":"Please include Hello","body":"include hello next time on your email"},
        "uuid":"…"} ], "uuid":"…" }
  ], "uuid":"…"
}
```

Connector field names (`from_email`, `body_plain`, …) and `send_mail` inputs are in
connectors-gmail.md. After writing `code`, always verify per recipe-gotchas.md (the API
won't catch a bad operand or field name — only the editor/runtime will).

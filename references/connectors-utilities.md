# Workato utility connectors (json_parser, logger, lookup_table, clock) — verified encodings

All discovered empirically via the start-as-validator loop (see recipe-gotchas.md). These
connectors need a `config` entry like any app, but **no `account_id`**:
`{"keyword":"application","name":"json_parser","provider":"json_parser","skip_validation":false}`

## JSON parser — provider `json_parser`, action `parse_json`

Turns a JSON **string** (e.g. Orderful's `transaction_message`) into pill-addressable data.

```json
{ "number":2, "provider":"json_parser", "name":"parse_json", "as":"aa000001", "keyword":"action",
  "input": {
    "sample_document": "<compact JSON sample of the expected document>",
    "document": "#{_dp('{\"pill_type\":\"output\",\"provider\":\"<upstream>\",\"line\":\"<as>\",\"path\":[\"<string field>\"]}')}"
  },
  "extended_output_schema": [ /* REQUIRED for downstream pill validation — see below */ ] }
```

Three traps, all verified:
1. **`sample_document` is required** (start error: "Sample document can't be blank").
2. **Runtime output is wrapped in a `document` root**: `{"document": {<parsed JSON>}}`.
   Every downstream pill path starts with `document`. The extended_output_schema must
   mirror this (one root object node named `document` containing the real schema).
3. **You must hand-write `extended_output_schema` and every node needs a `label`**
   (any human string). Without the schema — or without labels — downstream pills fail
   validation with `Unknown data field "<Humanized leaf>"`. Generate it from the sample:
   object → `{"name","label","type":"object","optional":true,"properties":[…]}`;
   array of objects → same plus `"type":"array","of":"object"`; scalar →
   `{"control_type":"text","name","label","type":"string","optional":true}`.

Provider-name graveyard (all "is invalid"): `workato_message_parser`, `message_parser`,
`workato_json_parser`, `utilities`, `workato_utilities`.

## Logger — provider `logger`, action `log_message`

```json
{ "provider":"logger", "name":"log_message", "as":"dd000001", "keyword":"action",
  "input": {"message": "A=#{…} | B=#{…}"} }
```
The single best **probe harness**: pack several candidate pill expressions into one
message, run one job, read which resolved (job line input shows the message
post-resolution). Name graveyard: `log`, `create_log_entry`, `log_entry`, `write_log`.

## Lookup tables — two ways in, one that works well

**The `lookup()` FORMULA (recommended, fully verified):** inside any `=`-formula value:
```
=lookup('shopify_items', 'upc': <expr>)['variant_id']
```
- Matches the table by **exact display NAME**, not id. A wrong name passes validation and
  only fails at **runtime**: `Unable to find lookup table <name>`. Confirm the real name
  with the user (the API can't read it — see below).
- Returns the row hash or `nil` → safe to test with a `blank` condition; chain
  `['column']` to extract a value.

**The `lookup_table` CONNECTOR (partially mapped):** provider `lookup_table`; actions
`get_entry` and `search_entries` exist (graveyard: `find_record`, `get_record`, `search`,
`lookup`, `search_records`, `lookup_entry`, `find_entry`, `select_record`, `search_entry`,
`lookup_entries`, `find_entries`, `list_entries`, `query_entries`, `filter_entries`).
`search_entries` accepts `lookup_table_id` but the per-column search-parameter encoding is
NOT discovered — flat keys (`upc`, `col1`, `col_1`) are schema-filtered out and the run
fails with `Empty/missing search parameters`. Until someone builds it in the editor and
reads it back, **prefer the `lookup()` formula**.

**API access:** ALL `lookup_tables` endpoints are `401` for a recipes-scoped token —
no list/read/create/rows. Creating tables and rows is **user-in-UI only**
(https://app.workato.com/lookup_tables). When you need a table, give the user the exact
name + columns + rows to create, then reference it by that name.

## Clock/scheduler trigger — UNRESOLVED

Probed `clock/scheduled_event`, `clock/new_scheduled_event`, `scheduler/scheduled_event`,
`clock/timer` — none accepted before the probe was abandoned. If you need a no-external-
input test recipe, either discover this via build-in-UI-then-read-back or just reuse a
polling trigger and force polls with stop+start.

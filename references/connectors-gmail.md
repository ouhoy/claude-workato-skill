# Gmail Connector Reference

Field names below are the **datapill keys** you put in `code` (e.g.
`#{_('data.gmail.<trigger_as>.from_email')}`), confirmed against a real job output
(`wk.py job <id> <job_id> --outputs`) and the docs.

## Trigger: `new_email`

Polling trigger on a label. Input:
```json
{ "label_ids": "INBOX" }   // mirror in dynamicPickListSelection too
```

**Output datapill fields** (top-level keys observed in a real job):

| Field key | Meaning |
|---|---|
| `from_email` | sender address (e.g. `you@example.com`). **Use this, not `from`.** |
| `to_emails`, `cc_emails` | recipients |
| `subject` | subject line |
| `body_plain` | full plain-text body (best for "contains" checks) |
| `body_html` | HTML body |
| `snippet` | short preview Gmail generates (first ~100 chars; always present) |
| `message_id`, `id`, `threadId` | identifiers |
| `labelIds` | array incl. `INBOX`, `UNREAD`, … |
| `received_time`, `internalDate` | timestamps |
| `attachments` | list |
| `payload.headers[]` | RAW Gmail `{name,value}` header list (From/Subject/etc.) — fallback only; the friendly fields above are easier |

**There is no bare top-level `from`** — that mistake makes a `from contains …` condition
silently never match. Use `from_email`. (This is exactly the bug we hit and fixed.)

**Polling, not real-time:** see recipe-gotchas.md → "Triggers are polling". Interval is
plan-gated and not settable via the API. Real-time Gmail = Gmail API `watch` → Google Cloud
Pub/Sub → a Workato webhook trigger (`watch` expires every 7 days).

## Action: `send_mail`

Input fields:

| Field key | UI label | Notes |
|---|---|---|
| `to` | To | recipient(s) |
| `cc`, `bcc` | Cc / Bcc | optional |
| `subject` | Subject | |
| `email_type` | Email type | `"text"` or `"html"` |
| `body` | Message | plain text or HTML per `email_type` |
| `from` | From | optional |
| `attachments` | Attachments | optional |

Minimal action step:
```json
{ "number":2, "provider":"gmail", "name":"send_mail", "as":"7a000003", "keyword":"action",
  "input": { "email_type":"text", "to":"someone@example.com",
             "subject":"Hi", "body":"Hello #{_('data.gmail.7a000001.from_email')}" },
  "uuid":"…" }
```

The connection: `config` entry `{"keyword":"application","name":"gmail","provider":"gmail","account_id":<connection id from GET /connections>}`.

A full trigger→if→send example recipe is in recipe-code-dsl.md ("Hello auto-responder").

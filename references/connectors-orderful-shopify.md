# Orderful (inbound EDI) → Shopify integration

End-to-end pattern proven in production: an inbound EDI **850 Purchase Order** from a trading
partner (e.g. Walmart) arrives in Orderful → a Workato recipe polls it → creates a **Shopify
draft order**. Recipe shape: **Orderful poller trigger → Orderful "get message" action →
Shopify "create draft order" action.**

This doc is mostly **traps**. The connectors are easy; the routing and field quirks are what
cost hours.

---

## Contents
- #1 trap — route inbound to a POLLER channel (Orderful-UI only)
- Diagnosing "POs exist but recipe didn't run"
- Inject a test inbound EDI transaction
- Orderful connector (poller trigger + `get_record`)
- Shopify connector (`create_draft_order`, `search_product`)
- Proven end-to-end recipe · Aside — Shopify via the Claude dashboard

## ⚠️ #1 trap — Orderful must ROUTE inbound to a POLLER channel (Orderful-UI only, NOT API)

The Workato Orderful trigger polls a **poller bucket**. Orderful only deposits an inbound
transaction into a poller bucket if the org's **inbound delivery** is routed to a **POLLER**-type
**Communication Channel**. If it's routed to an HTTP/SFTP channel (or nowhere), the poller bucket
stays **empty** and the recipe **never fires (0 jobs)** even though the POs clearly exist in
Orderful.

Configure it in the **Orderful app** (there is no API for this):
- Orderful → **Communication Channels** → **Default Inbound Communication Channels** → set the
  **Test** channel (and/or **Live**) to a **POLLER** channel, and toggle that channel **ACTIVE**.
  (Inbound 850s are usually `stream: TEST` during onboarding → the **Test** default is the one
  that matters; check the transaction's `stream`.)
- A relationship may **override** the default with its own channel (e.g. an HTTP
  `850_Wallmart_Channel`). If POs still don't reach the poller after setting the default, repoint
  the **relationship's** inbound channel to the poller too (Relationships → the partner/doc type).
- The channel's **Retrieval URL** shown in its detail pane is
  `https://api.orderful.com/v3/polling-buckets/<bucketId>` — that **`<bucketId>`** is exactly what
  goes in the Workato trigger's **Poller bucket ID**.

**The Orderful API cannot help here.** Probed and all `404`: `/v3/polling-buckets` (list),
`/v3/deliveries`, `/v3/streams`, `/v3/delivery-rules`, `/v3/organizations`,
`/v3/relationships/<id>` (+ `/delivery`), bucket `/subscriptions`. The API only returns a
bucket's *contents* (`GET /v3/polling-buckets/<id>`), never its config or assignment. So bucket
routing is necessarily done in the UI or handed to you by the user.

**Trailing-space trap:** a stray space in the Workato trigger's `bucketId` (`"12345 "`) silently
breaks polling — it polls a non-existent bucket, 0 jobs, no error. **Trim it.**

---

## Diagnosing "POs exist in Orderful but recipe didn't run / nothing in Shopify"

Work top-down:
1. **Is the recipe running?** `wk.py recipe <id>` → `running:true`? A stopped recipe never polls
   (0 jobs, `lifetime_task_count:0`). Start it: `wk.py start <id>`.
2. **Is the right bucket configured & space-free?** `wk.py recipe <id> --code` → trigger
   `input.bucketId` must be the exact numeric id, no trailing space.
3. **Is anything in the bucket?**
   `curl -s "https://api.orderful.com/v3/polling-buckets/<id>?limit=30" -H "orderful-api-key: $K"`
   → empty ⇒ routing problem (trap #1). Has items ⇒ recipe/trigger problem.
4. **Inject a test inbound transaction** (below) and re-check the bucket within ~60–90s (delivery
   is async: status goes `PENDING → SENT`).

## Inject a test inbound EDI transaction (Orderful API — safe, inbound to your own org)

```
POST https://api.orderful.com/v3/transactions      header: orderful-api-key: <key>
{
  "type":     { "name": "850_PURCHASE_ORDER" },
  "stream":   "TEST",
  "sender":   { "isaId": "<partner-isa>" },
  "receiver": { "isaId": "<your-org-isa>" },
  "message":  { "transactionSets": [ … ] }
}
```
- **No top-level `businessNumber`** field → rejected (`"property businessNumber should not exist"`).
- `message` = the **business content** (`transactionSets`), NOT the ISA/GS envelope (Orderful
  builds the envelope from sender/receiver/stream).
- Easiest valid body: `GET /v3/transactions/<a-known-good-id>/message`, take its `.transactionSets`,
  tweak `beginningSegmentForPurchaseOrder[0].purchaseOrderNumber`, re-POST.
- Sender = the partner is **simulated**; it's delivered to *your* org's inbound channel only —
  it never reaches the real partner.

---

## Orderful connector (community connector, app `orderful_connector_<…>`)

Connection: auth via the **Orderful API key**.

**Trigger `new_transaction_from_poller_bucket`** (single) / batch variant:
```json
{ "provider":"orderful_connector_<…>", "name":"new_transaction_from_poller_bucket",
  "as":"052a5527", "keyword":"trigger",
  "toggleCfg":{"___poll_interval":true},
  "input":{ "bucketId":"12345", "___poll_interval":"30" } }
```
- `___poll_interval`: minutes; **"5" is rejected**, **"30" is valid** (plan-gated minimum).
- **Output is transaction METADATA only** — `id`, `sender/receiver.isaId`, `type.name`,
  `businessNumber`, `stream`, `validationStatus`/`deliveryStatus`/`acknowledgmentStatus`, and
  **`message` as a URL (`message.href`) — NOT the parsed EDI**. So the trigger alone can't see
  line items.
- Scope to one partner/doc type with a **trigger condition** (Set trigger condition → e.g.
  `sender.isaId equals_to <ISA>` and `type.name contains 850`).

**Action `get_record`** — fetch the parsed message:
```json
{ "provider":"orderful_connector_<…>", "name":"get_record", "as":"48feef71", "keyword":"action",
  "dynamicPickListSelection":{"object":"Transaction message"},
  "input":{ "object":"message",
            "id":"#{_dp('{\"pill_type\":\"output\",\"provider\":\"orderful_connector_<…>\",\"line\":\"052a5527\",\"path\":[\"id\"]}')}" } }
```
- `object` options: `transaction`, **`message`** (= UI "Transaction message" → the parsed
  canonical EDI: `transactionSets[].beginningSegmentForPurchaseOrder`, `N1_loop`,
  `PO1_loop[].baselineItemData`/`PID_loop`, `CTT_loop`), `attachment`, `organization`,
  `acknowledgment`. **Use `message` to get PO line items.**
- Other actions seen: `create_record`, `convert_data_format` (X12⇄JSON), `list_transactions`
  (general list — basis for a *schedule-poll* design that avoids buckets entirely),
  `list_transactions_from_poller_bucket`, plus a Custom action (HTTP).

---

## Shopify connector (native Workato connector)

Connection: auth type **"Access token"** → a Shopify **custom-app admin token** (`shpat_…`) +
the shop **subdomain** (the part before `.myshopify.com`; use the canonical/permanent
`*.myshopify.com` handle, e.g. `your-shop`, not a vanity alias). (OAuth 2.0 is the other option.)

- **Connection credentials are UI-only.** No API writes them (`GET /api/connections/{id}` → 404).
  If a connection shows `401`/Disconnected (e.g. token was cleared), re-enter the token on its
  connection page and click **Connect**. `wk.py connections` shows `authorization_status`.
- **Action `create_draft_order`** — full verified input (much richer than the minimum):
  ```json
  { "customer_id":"<numeric id>", "use_customer_default_address":"false",
    "email":"…", "note":"…",
    "shipping_address":{ "first_name":"…","last_name":"…","company":"…","address1":"…",
                         "city":"…","province":"FL","zip":"…","country":"US" },
    "billing_address":{ "company":"…" },
    "line_items":[ { "variant_id":"<id or pill/formula>", "quantity":"<pill/formula>" } ] }
  ```
  Hard-won specifics:
  - **Optional fields are silently DROPPED unless declared in the step's
    `extended_input_schema`** — note/email/addresses simply never reached Shopify until the
    schema declared them. Always write the input schema for every optional field you use.
  - **Address fields are `province` and `country`** — `province_code`/`country_code` pass
    validation AND appear in job input but Shopify ignores them (address saved without
    state/country). Values like "FL"/"US" in `province`/`country` work.
  - **"Sold out"** = a line's variant has 0 inventory without oversell. Empty `quantity`
    (a pill that resolved blank) also surfaces as "Sold out". Fix data-side: variant
    `inventoryPolicy: CONTINUE`, and fix the pill.
  - **"Record is invalid"** = bad referenced data: a **deleted/nonexistent `customer_id`**,
    or junk address values (e.g. `"-"` placeholders in zip/city — an editor re-save
    introduced those once). Check the customer exists before suspecting the mapping.
  - **Requires a `customer_id` AND existing `variant_id`s — no custom items.** If the store
    has no customer, create one via Admin GraphQL `customerCreate`.
  - `variant_id`/`quantity` accept pills and `=` formulas (numeric vs string is fine).
- **Action `search_product`** — the only in-connector item lookup:
  ```json
  { "handle": "=<formula extracting UPC>" }
  ```
  - Real input fields (discovered via job-input filtering): **`title`, `handle`, `vendor`,
    `ids`, `product_type` ONLY** — no sku, no barcode, no free query, no limit.
  - Output: `{"products":[{…,"variants":[{"id",…}]}]}`. Give the step a labeled
    `extended_output_schema` (products → variants → id) so downstream pills validate;
    extract with `=_dp('…["products"]').first['variants'][0]['id']`.
  - Since handle is the only unique searchable key, the working convention is
    **product handle = item UPC** for EDI-orderable products.

---

## Proven end-to-end recipe (in the reference account)

Final architecture (every step verified live; pill/formula/schema rules in
recipe-code-dsl.md, json_parser/lookup specifics in connectors-utilities.md):
```
0  orderful    new_transaction_from_poller_bucket  { bucketId, ___poll_interval }
└─1 orderful   get_record (object="message")       → transaction_message JSON STRING
└─2 json_parser parse_json (sample_document + doc) → pills under document.transactionSets…
└─3 shopify    search_product (handle = =UPC-formula, PO line 1)
└─4 shopify    search_product (handle = =UPC-formula, PO line 2)
└─5 if  (line1: products empty AND lookup('shopify_items','upc':…) blank)
   └─6 stop    stop_with_error, stop_reason = "='ITEM NOT FOUND…' + PO + UPC + description"
└─7 if  (line2: same)  └─8 stop
└─9 shopify    create_draft_order  (customer_id, email, note from N9_loop,
               shipping_address from N1_loop, billing company from N1_loop[1] BT party,
               line_items: variant_id = "=products.first.present? ? products.first['variants'][0]['id']
                                          : lookup('shopify_items','upc': <UPC>)['variant_id']",
                           quantity = =PO1_loop[i] formula)
└─10 orderful  approve_delivery (deliveryId from trigger)
```
Key mapping formulas (Walmart 850):
- **UPC per line** (the `UP` qualifier wanders between slots):
  `=…['baselineItemData'][0]['productServiceIDQualifier1'] == 'UP' ? …['productServiceID1'] : …['productServiceID2']`
- **Three-tier item matching**: (1) Shopify `search_product` by handle=UPC →
  (2) Workato lookup table (`lookup('shopify_items','upc':…)`, UI-maintained, columns
  upc/variant_id) → (3) `stop` with PO number + UPC + PID description. All three tiers
  test-verified (tier 2 by renaming a product's handle so Shopify misses it).
- Ship-to: `N1_loop.first` partyLocation/geographicLocation (first-element dotted pills);
  bill-to company: `N1_loop[1]` BT party via `=` formula (second element ⇒ formula mode).
  Walmart's BT segment carries only a name — don't invent a street address.
- Note: PO number + `N9_loop` reference + first text line.
- Recipe assumes exactly **2 PO lines** (per-line steps); variable line counts need a
  loop redesign (foreach + per-line search + list assembly — not yet built).

`config`: one `application` entry per connector — `account_id` for orderful/shopify,
none for json_parser. Edit via API: stop → `wk.py update <id> --code code.json` →
`wk.py start <id>` (start = validity check). **Can't modify a running recipe.**

**Dedup caveat:** after a successful run the Orderful poller bucket did **not** drain (items
remained). Workato dedups inbound via the **trigger cursor** (`trigger_closure`), not by
calling Orderful confirm-retrieval — restarts did NOT duplicate already-processed
transactions across many stop+start test cycles, but each new test needs a fresh PO number.

**Shopify-side prerequisites** (the recipe fails without them): the customer exists
(else "Record is invalid"), each item resolves via handle=UPC or a lookup-table row
(else the ITEM NOT FOUND stop), variants oversellable (`inventoryPolicy: CONTINUE`,
else "Sold out" at 0 stock).

**End-to-end test loop** (also see recipe-gotchas.md "Forcing an immediate poll"):
inject an 850 with a FRESH PO number → poll the bucket until it appears (~60–90 s) →
stop+start the recipe → poll `GET /recipes/:id/jobs` for the new job → inspect its
`lines[]` (resolved inputs/outputs per step) → confirm the draft order in Shopify.

---

## Aside — Shopify via the Claude dashboard (one-click, NOT the Workato connection)

Shopify is also available as a **one-click custom connector from the Claude dashboard** (the
Shopify connector plugin / MCP — OAuth, no token to manage). That is **Claude ↔ Shopify** (lets
Claude read/write the store directly), which is **separate** from the **Workato ↔ Shopify**
connection above that the recipe uses. Don't conflate the two — the Workato recipe needs its own
Shopify connection (access-token) regardless of the Claude-dashboard connector.

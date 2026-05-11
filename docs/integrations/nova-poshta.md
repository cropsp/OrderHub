# Nova Poshta Integration — Technical Reference

> Internal technical reference for developers (human or AI) working
> on the Nova Poshta (NP) shipping integration. Operational manual +
> API gotchas + credentials handling. Not user-facing documentation.

## 1. Overview

OrderHub talks to a single Nova Poshta endpoint —
`https://api.novaposhta.ua/v2.0/json/` — through a thin async HTTP
client (`backend/services/nova_poshta.py`). The integration supports
**TTN (waybill) lifecycle** (create + delete), **counterparty
resolution** for sender and recipient, and **address search** for
the order-detail shipping editor.

**Scope today:**

| Feature | Status | Sprint |
|---|---|---|
| TTN create (`InternetDocument.save`) | working | NP-FIX-1, NP-FIX-3a |
| TTN delete (`InternetDocument.delete`) | working | NP-FIX-4 |
| Sender resolution (counterparty + contact person) | working | NP-FIX-3a |
| Recipient resolution (find existing or create new) | working | NP-FIX-3a |
| City / warehouse search (typeahead) | working | (pre-audit) |
| Stock-counting hook on TTN create / delete | working | PKG-2 |
| Tracking status polling | parked | NP-FIX-5 |
| Server-rendered NP errors with field highlights | parked | NP-FIX-6 |
| TTN print PDF (`getDocumentPrint`) | parked | NP-FIX-7 |
| API v1.0 → v2.0 migration | deferred | NP-FIX-8 |

**Account type constraint:** OrderHub is built around
**PrivatePerson API keys** (personal NP accounts). Several NP API
methods behave differently or are unavailable on PrivatePerson keys
vs Organization keys — see **§3 Gotchas**. The codebase has been
verified against PrivatePerson keys end-to-end.

**Shops:** only Ukrainian shops use NP. The integration is gated in
the UI by `order.shipping_country === 'UA'` (NP-FIX-1 country guard
in `frontend/src/components/orders/detail/DetailLogistics.tsx`), so
US/EU orders don't render the NP block at all.

---

## 2. TTN lifecycle (full flow)

Two endpoints in `backend/routers/shipping.py`:

```
POST   /api/shipping/np-ttn/{order_id}   →  create_np_ttn
DELETE /api/shipping/np-ttn/{order_id}   →  delete_np_ttn
```

Plus two read-only helpers for the shipping editor typeahead:

```
GET    /api/shipping/cities?query=...
GET    /api/shipping/warehouses/{city_ref}?query=...
```

### Create flow (`create_np_ttn`)

```
operator clicks Generate NP Label
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Pre-flight validation                            │
│   • order exists, no existing ttn_number         │
│   • shop has np_api_key_encrypted                │
│   • order has shipping_city + shipping_name +    │
│     shipping_phone + shipping_city_ref +         │
│     shipping_warehouse_ref                       │
│   • shop has np_sender_city_ref AND              │
│     np_sender_warehouse_ref  ← NP-FIX-1 gate     │
│   any miss → HTTP 400 with actionable detail     │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Resolve sender (cached on shop, or live)         │
│   if shop.np_sender_ref + np_sender_contact_ref  │
│     → use cached                                 │
│   else:                                          │
│     getCounterparties("Sender")                  │
│       → sender_ref = senders[0]["Ref"]           │
│     getCounterpartyContactPersons(sender_ref)    │
│       → contact_ref = contacts[0]["Ref"]         │
│     write both back to shop (db.commit)          │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Resolve recipient                                │
│   getCounterparties("Recipient", clean_phone)    │
│   if found → contact_ref = first row's           │
│              ContactPerson.data[0].Ref           │
│   else → create_counterparty(...) →              │
│          response.ContactPerson.data[0].Ref      │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Build payload + InternetDocument.save             │
│   ServiceType: WarehouseWarehouse (hardcoded)    │
│   PayerType: shop.np_default_payer_type          │
│   Weight, Volume, Description, Cost, COD...      │
│ Response: { IntDocNumber, Ref, CostOnSite, ... } │
│   order.ttn_number = IntDocNumber                │
│   status → SHIPPED                               │
└─────────────────────────────────────────────────┘
         │
         ▼ (only if order.packaging_id is not None)
┌─────────────────────────────────────────────────┐
│ PKG-2 stock hook                                  │
│   stock_service.apply_movement(                  │
│     delta=-1, reason='ttn_create',               │
│     order_id, user_id)                           │
│   captures returned warnings (negative stock)    │
└─────────────────────────────────────────────────┘
         │
         ▼
   await db.commit()   ← single commit, all writes atomic
         │
         ▼
   { status: "success", ttn: "...", warnings: [...] }
```

Frontend `useShipping.ts` `onSuccess` loops over `data.warnings`
and emits one warning-style toast per entry, after the standard
"TTN created successfully" toast.

### Delete flow (`delete_np_ttn`)

```
operator clicks × on TTN block (with confirm)
         │
         ▼
   InternetDocument.delete({DocumentBarcodes: order.ttn_number})
         │
         │ (NP success → continue; NP failure → 400, rollback)
         ▼
   order.ttn_number = None
   status → IN_PRODUCTION
         │
         ▼ (only if order.packaging_id is not None)
   stock_service.apply_movement(
     delta=+1, reason='ttn_delete', order_id, user_id)
         │
         ▼
   await db.commit()
         │
         ▼
   { status: "success", message: "TTN ... deleted" }
```

**Critical:** the parameter is `DocumentBarcodes` (accepts our
14-digit `IntDocNumber`), NOT `DocumentRefs` (which expects a UUID
Ref we don't store). See **§3 Gotchas** for the failure mode.

---

## 3. API gotchas — quick reference

Each row here is a real failure mode we hit during development.
When you see one of these errors in `backend/logs/server.log`,
this table tells you what to do.

| Symptom (NP error / log line) | Root cause | Fix |
|---|---|---|
| `Method CounterpartyGeneral_getContactPersons not found` | Called `Counterparty.getContactPersons` on a PrivatePerson key. NP redirects unprefixed name to a non-existent model. | Use `Counterparty.getCounterpartyContactPersons` (with `Counterparty` prefix on the verb). Works for both PrivatePerson and Organization keys. **Sprint:** NP-FIX-3a |
| `There are only invalid DocumentBarcodes and/or DocumentRefs` (on delete) | Passed `IntDocNumber` (14 digits) under the `DocumentRefs` key. NP expects a UUID Ref there. | Pass the same value under `DocumentBarcodes`. **Sprint:** NP-FIX-4 |
| `SendersPhone invalid format` | Sender Phone field on shop config contained non-phone text (e.g. an operator typed a surname). | Frontend currently does **not** validate this field; backend does **not** normalize sender phone (it does for recipient — see `routers/shipping.py:170-178`). For now: fix the shop config manually. Future fix: NP-FIX-3b (parked). |
| `Shop's Nova Poshta sender warehouse is not configured` (HTTP 400) | `Shop.np_sender_warehouse_ref` is NULL. NP-FIX-1 strict gate. | Open Shops → Logistics (NP) → set Sender City + Sender Warehouse. **Sprint:** NP-FIX-1 |
| Delete returns 400 with body like `errors: {"<uuid>": "Document already deleted ...", "0": "..."}` and the error message in logs reads `"<uuid>, 0"` | TTN was already deleted on NP side (e.g. via the NP cabinet manually). NP returns `errors` as a `dict` of `{ref: message}` pairs, but our `_post()` does `', '.join(errors)` which joins **keys** when `errors` is a dict — so the useful message disappears. | Two-part: (a) accept "already deleted" as effective success and clear `Order.ttn_number` anyway → **NP-UX-2** (parked); (b) fix `_post()` to handle `dict`-shape errors by joining values → **NP-UX-4** (parked). Today's workaround: manual `UPDATE orders SET ttn_number = NULL` if the order gets stuck. |

**Where to look for new errors:** `backend/logs/server.log`. Grep
for `SHIPPING`, `nova_poshta`, `NovaPoshtaAPIError`. The full
HTTP request POSTs to `api.novaposhta.ua` are also logged via
`httpx` at DEBUG level — useful for confirming what payload
actually went out.

### Two response-shape quirks worth knowing

1. **`ContactPerson` field on a counterparty can be a `dict`,
   `string`, or `null`** depending on whether the counterparty has
   a contact person configured. Code that reads
   `counterparty["ContactPerson"]["data"][0]["Ref"]` will crash
   with `AttributeError` on the string/null shapes. Currently
   PrivatePerson recipients we create through
   `Counterparty.save` always come back with the dict shape (we
   rely on this), but defensive type-checking is good practice
   when extending this.

2. **`errors` field can be `list` or `dict`** (see the gotcha
   above). Always check shape before joining/parsing.

---

## 4. Credentials & encryption

NP API keys are per-shop, encrypted at rest with **Fernet
(AES-128-CBC + HMAC-SHA256)**.

### Storage

- Column `Shop.np_api_key_encrypted: Text` — Fernet ciphertext.
- Encryption key in env var `ENCRYPTION_KEY` (loaded via
  `backend/config.py`). Required at app startup; missing or
  invalid → boot fails.
- `services/encryption_service.py` exposes
  `encrypt_value(plaintext)` and `decrypt_value(ciphertext)`.
- Helpers also encrypt `shopify_access_token_encrypted` and
  `shopify_webhook_secret_encrypted` — same pattern, same key.

### Operational notes

- **Adding a key:** Shops page → row → Config → Logistics (NP) tab →
  enter API key + sender metadata → Save. Backend `routers/shops.py`
  calls `encrypt_value` before writing. UI never displays the key
  back — `ShopResponse` exposes only `has_np_token: bool`.
- **Rotating `ENCRYPTION_KEY`:** **not safe** without re-encryption
  of every existing encrypted column. Existing tokens become
  unreadable after a key swap; UI starts returning HTTP 500 on every
  NP action. The flow would be (a) decrypt all with old key, (b)
  re-encrypt with new, (c) swap env var, (d) restart. No automated
  rotation script exists — write one before doing this in
  production.
- **Lost `ENCRYPTION_KEY`:** all NP and Shopify tokens become
  unrecoverable. Operator must re-enter every credential through
  the UI.
- **`is_np_ready` derived flag** (`schemas/shop.py`):
  `has_np_token AND np_sender_city_ref AND np_sender_warehouse_ref`.
  Used by the frontend to show the amber "NP not configured" banner
  on the order Logistics panel (NP-FIX-1).

### PrivatePerson vs Organization

- **PrivatePerson** (what we use): one Counterparty = the user
  themselves, one ContactPerson = the user themselves. The
  `getContactPersons` method (no prefix) is restricted; use
  `getCounterpartyContactPersons` (with prefix) instead.
- **Organization:** can manage multiple counterparties and contact
  persons. More NP API surface available (e.g.
  `ContactPerson.save`, `ContactPerson.update`). OrderHub has not
  been tested against Organization keys; the rename to the prefixed
  method works for both shapes per community SDK consensus.
- Public docs: https://developers.novaposhta.ua

---

## 5. Operational playbook + roadmap

### Playbook — common operator tasks

**A. Set up a new Ukrainian shop for NP shipping.**

1. Shops page → New Shop (or edit existing) → General → set platform.
2. Logistics (NP) tab → enter NP API key (PrivatePerson personal
   account).
3. Sender Name, Sender Phone (UA mobile format like `380XXXXXXXXX`
   or `0XXXXXXXXX`).
4. Sender City: typeahead search (calls `getCities`). Pick the city.
5. Sender Warehouse: typeahead search (calls `getWarehouses` for
   the chosen city). Pick a real warehouse — **not** a courier
   pickup point. This is what NP-FIX-1 validates.
6. Save. `is_np_ready` should now be `true`; orders for this shop
   will render the NP Logistics panel.

**B. Debug a failed TTN create.**

1. Reproduce the failure once if needed.
2. `grep -E "SHIPPING|nova_poshta|ERROR" backend/logs/server.log | tail -30`.
3. Find the NP API error message. Match against **§3 Gotchas**.
4. If the error isn't in the table, look at the full request body
   in the log (the line right before the error) — sometimes the
   issue is a malformed payload, not an NP-side problem.

**C. Recover a stuck TTN (UI Delete fails but TTN is already gone
on NP side).**

1. Confirm in NP cabinet that the TTN is deleted.
2. `docker compose exec -T postgres psql -U crm -d crm_db -c "UPDATE orders SET ttn_number = NULL, status = 'IN_PRODUCTION' WHERE id = '<order_uuid>';"`
3. If PKG-2 stock tracking matters for the audit trail: manually
   restore the counter with
   `UPDATE packaging_boxes SET stock_quantity = stock_quantity + 1 WHERE id = '<box_uuid>';` — note that this bypasses the ledger
   and breaks the cached-counter / ledger-sum invariant. NP-UX-2
   will eventually do this properly via the delete flow.

**D. Manually probe NP API with curl (smoke test or hypothesis
verification).**

Substitute your API key and references for placeholders. Useful for
isolating "is this our code or NP" questions.

```bash
# Find sender counterparty (for PrivatePerson key, returns one row)
curl -X POST https://api.novaposhta.ua/v2.0/json/ \
  -H "Content-Type: application/json" \
  -d '{
    "apiKey": "<YOUR_NP_KEY>",
    "modelName": "Counterparty",
    "calledMethod": "getCounterparties",
    "methodProperties": {"CounterpartyProperty": "Sender"}
  }' | python3 -m json.tool

# Get the sender's contact person (uses the correct prefixed method)
curl -X POST https://api.novaposhta.ua/v2.0/json/ \
  -H "Content-Type: application/json" \
  -d '{
    "apiKey": "<YOUR_NP_KEY>",
    "modelName": "Counterparty",
    "calledMethod": "getCounterpartyContactPersons",
    "methodProperties": {"Ref": "<SENDER_REF_UUID>"}
  }' | python3 -m json.tool

# Delete a TTN by its 14-digit IntDocNumber
curl -X POST https://api.novaposhta.ua/v2.0/json/ \
  -H "Content-Type: application/json" \
  -d '{
    "apiKey": "<YOUR_NP_KEY>",
    "modelName": "InternetDocument",
    "calledMethod": "delete",
    "methodProperties": {"DocumentBarcodes": "<14_DIGIT_TTN>"}
  }' | python3 -m json.tool
```

**E. Run the backend test suite against the NP client / shipping
router.**

```bash
cd backend && source venv/bin/activate
python -m pytest tests/test_nova_poshta.py tests/test_shipping_router.py -v
```

These cover the wrapper contract (retry behaviour, error
translation, NP method-name regression guards from NP-FIX-3a /
NP-FIX-4) and the shipping router's validation paths + stock hooks
(NP-FIX-1, PKG-2).

### Roadmap — parked NP work

In execution-priority-ish order (highest leverage first), all
tracked in `implementation_plan.md` under "Explicitly deferred":

| ID | Title | Cost | Why parked |
|---|---|---|---|
| NP-UX-2 | Idempotent TTN delete (clear local state when NP returns "already deleted") | S | Rare in practice (manual NP cabinet deletes are uncommon); SQL workaround exists |
| NP-UX-4 | Fix `_post()` to handle `dict`-shape `errors` (join values, not keys) | XS | One-off cosmetic; affects only edge cases like NP-UX-2's path |
| NP-FIX-3b | Frontend regex/mask + backend normalization for Sender Phone | S | One operator configures NP today; workaround is "type the right thing" |
| NP-FIX-5 | Background tracking poll (4h batch + manual refresh button) | M | No customer-facing tracking UI yet |
| NP-FIX-6 | Surface NP-specific error messages on frontend (field highlights) | M | Generic toast errors work for now |
| NP-FIX-7 | TTN print PDF via `getDocumentPrint` | M | Operator prints via NP cabinet manually |
| NP-FIX-8 | API v1.0 → v2.0 migration | L | We're already on v2.0; this was an audit-era item that turned out unnecessary |

When picking up any of these, start by reading the corresponding
sprint history in `implementation_plan.md` and the related task.md
template that may already exist.

---

## Appendix — Glossary

| Term | Meaning |
|---|---|
| **TTN** | Товаротранспортна накладна. The waybill — what NP returns when you call `InternetDocument.save`. Identified by a 14-digit `IntDocNumber` (e.g. `20451436992002`) and an internal UUID `Ref`. |
| **IntDocNumber** | The 14-digit human-readable TTN number. What customers and operators see. What we store in `Order.ttn_number`. |
| **Ref** | UUID identifier of an NP entity (counterparty, contact person, document, city, warehouse). What `DocumentRefs` expects (and what we don't store for our own TTNs — see NP-FIX-4 gotcha). |
| **Counterparty** | NP's term for a sender or recipient entity. Has `CounterpartyType` (Organization / PrivatePerson) and `CounterpartyProperty` (Sender / Recipient). |
| **ContactPerson** | Nested under a Counterparty. For PrivatePerson, the user themselves. For Organization, named employees. |
| **CityRef / WarehouseRef** | UUIDs from `Address.getCities` and `Address.getWarehouses` — required on every `InternetDocument.save` payload (`CitySender`, `CityRecipient`, `SenderAddress`, `RecipientAddress`). |
| **ServiceType** | NP service type for the TTN. We hardcode `WarehouseWarehouse` today; making this selectable is parked for a future sprint. Other values: `WarehouseDoors`, `DoorsWarehouse`, `DoorsDoors`. |
| **PrivatePerson key** | Personal NP API key. Several methods (notably `Counterparty.getContactPersons`, `ContactPerson.save`) are restricted on this key class. |

---

## Where to find related code

- **NP client wrapper:** `backend/services/nova_poshta.py` — single
  `_post()` helper + 7 wrapper methods (cities, warehouses,
  counterparties, contact persons, create document, delete document,
  create counterparty).
- **TTN flow handlers:** `backend/routers/shipping.py` —
  `create_np_ttn`, `delete_np_ttn`, city/warehouse search endpoints.
- **Stock hooks:** `backend/services/stock_service.py` (PKG-2) —
  `apply_movement()` called inside the create/delete TTN
  transactions.
- **Credentials:** `backend/services/encryption_service.py` (Fernet),
  `backend/config.py` (env loading), `backend/routers/shops.py`
  (encrypt-on-write).
- **Models:** `backend/models/shop.py` (NP fields on Shop),
  `backend/models/order.py` (`ttn_number`, `packaging_id`,
  `computed_packaging_box_id`).
- **Tests:** `backend/tests/test_nova_poshta.py` (client-level,
  including NP-FIX-3a and NP-FIX-4 method-name regression guards),
  `backend/tests/test_shipping_router.py` (TTN happy-paths, NP-FIX-1
  validation gates, PKG-2 stock hooks), `backend/tests/test_stock_service.py`
  (PKG-2 transactional helper).
- **Frontend:** `frontend/src/components/orders/detail/DetailLogistics.tsx`
  (the Logistics panel + Packaging dropdown + TTN block),
  `frontend/src/hooks/useShipping.ts` (TTN mutations + warning toast
  loop), `frontend/src/api/shipping.ts` (REST client).

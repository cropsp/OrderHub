# Nova Poshta Integration Audit — May 2026

**Sprint:** NP-DISC (Nova Poshta Discovery)
**Author:** Planning agent (Cowork-side), reviewed by user
**Status:** Deliverable — pending user approval to proceed to NP-FIX-* sprints

---

## Executive Summary

OrderHub's Nova Poshta integration shipped in sprints **NP-P0…NP-P3** (Apr 2026,
all marked DONE) and covers the basic "create a TTN" path: city/warehouse search,
sender ref caching, Fernet-encrypted API keys, COD support, Kyiv timezone, debounced
recipient lookup. After a real-world incident — a TTN created with no sender warehouse
auto-dispatched a courier the user had to phone-cancel — live work paused. This audit
confirms the **root cause is a single missing backend validation** and lays out a
prioritized fix backlog that lets us safely re-enable NP work, this time tested
against a sandbox.

The integration sits entirely on Nova Poshta's **legacy v2.0 JSON API**
(`api.novaposhta.ua/v2.0/json/`). NP also operates a **modern v1.0 REST API**
(`api.novapost.com/v.1.0`, with JWT auth, webhooks, pickups, and an explicit
Postman-based sandbox). Migration to v1.0 is **not** in scope for the immediate
fix list — too big, and current v2.0 paths work — but it's recorded here as a
strategic option once the immediate fixes ship.

Total backend test coverage of NP code today: **0 tests**. That is a finding in
itself.

---

## 1. Sandbox / Test Environment

### 1.1 v2.0 (what OrderHub uses today)

NP's developer documentation does **not** describe a dedicated sandbox URL or
test credentials for v2.0. The pragmatic workaround used across the v2.0
ecosystem (lis-dev/nova-poshta-api-2 PHP client, smerch88/nova_poshta tutorial,
KeyCRM's integration patterns) is:

- Register a personal NP account (individual, not legal entity).
- Generate an API key from `new.novaposhta.ua → Settings → Security`.
- Use that key against the **production** `api.novaposhta.ua/v2.0/json/`
  endpoint, but on a personal counterparty so any TTN that accidentally
  goes through doesn't trigger a real shipment from the business
  warehouse.

Practically this means: **for TTN-creation tests, treat the production v2.0
endpoint as live**. The "stage" environment commonly mentioned in NP docs
refers to the v1.0 modern API (next section), not v2.0.

### 1.2 v1.0 (modern, NOT used by OrderHub)

The new `api-portal.novapost.com` portal explicitly documents a Stage
environment with an official Postman collection, JWT token flow, and
test API keys "linked to an individual with no connection to any
organizations." See [Generating API keys for Nova Post API][np-keys] and
[Testing][np-testing] (sitemap: `/novaposhta-docs/integration-guide/testing.md`).

### 1.3 What this means for NP-FIX-* work

For every fix that touches the **TTN-creation request path** (the dangerous
one — that's where couriers get dispatched), we will:

1. Use a **separate test NP account** (individual, not the production
   Lamamarka business counterparty).
2. Create the test account's API key via the NP business cabinet, store it
   in a non-production OrderHub shop record (e.g. a new `KoraKlenu Test NP`
   shop or a dev-only entry).
3. Validate the entire TTN flow against this isolated account before
   touching the production NP key.

For **read-only** paths (city search, warehouse search, counterparty lookup),
testing against the production endpoint with any valid key is safe — those
methods don't dispatch anything.

---

## 2. Code Audit — What's Shipped Today

### 2.1 Backend NP service (`backend/services/nova_poshta.py`)

98 lines. Single class `NovaPoshtaClient`. Uses `tenacity` for retry on
`httpx.HTTPError` (3 attempts, exponential backoff 2-10s). Distinguishes
`NovaPoshtaAPIError` (business failure, never retried) from network failures.

Methods exposed:

- `get_cities(query)` → `Address.getCities`
- `get_warehouses(city_ref, query)` → `Address.getWarehouses`
- `get_counterparties(property, find_by_string)` → `Counterparty.getCounterparties`
- `create_counterparty(...)` → `Counterparty.save`
- `get_contact_persons(counterparty_ref)` → `Counterparty.getContactPersons`
- `create_internet_document(props)` → `InternetDocument.save` (TTN create)
- `delete_internet_document(refs)` → `InternetDocument.delete` (TTN cancel)

### 2.2 Backend router (`backend/routers/shipping.py`)

305 lines. Four endpoints:

- `GET  /api/shipping/cities` — debounced city search
- `GET  /api/shipping/warehouses/{city_ref}` — warehouses in a city
- `POST /api/shipping/np-ttn/{order_id}` — create TTN
- `DELETE /api/shipping/np-ttn/{order_id}` — cancel TTN

The `POST /np-ttn/{order_id}` handler builds a payload with `ServiceType`
hardcoded to `"WarehouseWarehouse"`, `PayerType` defaulting to `"Sender"`,
`PaymentMethod` defaulting to `"Cash"`. Pulls weight/volume defaults from
`Shop.np_default_*` columns when the request body omits them.

### 2.3 Shop model (`backend/models/shop.py:42-57`)

Per-shop NP configuration:
`np_api_key_encrypted`, `np_sender_name`, `np_sender_phone`,
`np_sender_city_ref`, `np_sender_warehouse_ref`, `np_sender_ref` (cached
counterparty Ref), `np_sender_contact_ref` (cached contact), `np_default_description`,
`np_default_weight_kg` (default 0.5), `np_default_volume_m3` (default 0.004),
`np_default_payer_type` (default "Sender"), `np_default_payment_method` (default
"Cash").

### 2.4 Order model (`backend/models/order.py:115, 137-139`)

`shipping_np_cost`, `ttn_number`, `ttn_created_at`, `ttn_printed`. The
`ttn_printed` flag exists but no endpoint sets it — see §3 finding.

### 2.5 Frontend (`frontend/src/components/orders/detail/DetailLogistics.tsx`)

Recipient city + warehouse search with click-outside-close, copy-to-clipboard
TTN, parcel-estimate auto-fill, manual override. Disables "Create TTN"
button when `order.shipping_warehouse_ref` is missing
(`DetailLogistics.tsx:561`). **Does not validate the shop-side
`np_sender_warehouse_ref` is set.**

---

## 3. Feature Inventory

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| Encrypt + store NP API key per shop (Fernet) | Done | `services/encryption_service.py`, `Shop.np_api_key_encrypted` | NP-P3 |
| Mask API key in UI | Done | `Shop.has_np_api_key` flag in API response, raw key never returned | NP-P3 |
| Recipient city search (debounced) | Done | `routers/shipping.py:44-66`, `frontend useDebounce.ts` 350ms | NP-P2 |
| Recipient warehouse search | Done | `routers/shipping.py:68-90` | NP-P2 |
| Sender warehouse selection in shop settings | **Partial** | `Shop.np_sender_warehouse_ref` column exists; no Shop-edit UI surfaces it explicitly | UI gap — see §4 |
| Sender warehouse caching | Done | `Shop.np_sender_ref`, `np_sender_contact_ref` populated on first call | NP-P1 |
| TTN create | Done | `routers/shipping.py:93-263` | Has the validation gap in §4 |
| TTN delete / cancel | Done | `routers/shipping.py:266-305` | NP-P3 |
| TTN print / label PDF | **Missing** | `Order.ttn_printed` flag exists but no endpoint sets it; no `getDocumentPrint` call anywhere | Major UX gap |
| TTN tracking / status sync | **Missing** | No periodic poll, no webhook listener, no `TrackingDocument.getStatusDocuments` call | Major UX gap |
| Recipient phone normalization | Done | `routers/shipping.py:169-174` strips + 380-prefixes | Simple, may not handle international |
| COD (cash on delivery) support | Done | `BackwardDeliveryData` payload at `routers/shipping.py:237-243` | NP-P1 |
| Date/timezone handling (Europe/Kiev) | Done | `routers/shipping.py:203, 216` | NP-P1 |
| Error surfacing on the frontend | Partial | Toast on error, but NP-specific error codes are flattened to generic "Failed to communicate" | NP-FIX candidate |
| Retry / timeout handling on backend | Done | `tenacity` 3 attempts, 30s timeout | NP-P0 |
| Webhook for status updates from NP | **Missing** | No `/np-webhook` route, no shipping_status column lifecycle logic | v1.0 has webhooks, v2.0 needs polling |
| Auto-detect Service Type (W2W / W2D / D2W / D2D) | **Missing** | Hardcoded `"WarehouseWarehouse"` at `routers/shipping.py:220` | KeyCRM, Eltrino offer all four |
| Multi-shipment per order (split TTNs) | Missing | Single `Order.ttn_number` column, no list relationship | Lower priority |
| Add TTN to register (batch print) | Missing | No `ScanSheet.insertDocuments` call | Convenience for high-volume sellers |
| **Validate shop has sender warehouse before TTN create** | **MISSING** | No backend or frontend check; root cause of incident | See §4 |
| Backend tests for NP code | **0 tests** | `grep nova_poshta backend/tests/` returns no results | Required before any fix lands |

---

## 4. Courier-Dispatch Incident — Root Cause

**Reproduction.** A TTN is created on an order via
`POST /api/shipping/np-ttn/{order_id}`. The request handler at
`backend/routers/shipping.py:213-234` builds the NP payload with
`"SenderAddress": shop.np_sender_warehouse_ref`. If
`np_sender_warehouse_ref` is `NULL` for the shop (a real possibility
because nothing on the way to TTN creation enforces that it be set),
the request still goes through.

Per the legacy NP v2.0 contract, `InternetDocument.save` accepts the
ServiceType `"WarehouseWarehouse"` together with a missing
`SenderAddress`. NP's internal logic then treats the missing sender
warehouse as "send a courier to the sender's registered counterparty
address to pick up the parcel" — i.e. it **silently downgrades** to a
door-pickup service. From the user's perspective, the TTN looks like a
normal warehouse-to-warehouse parcel, but a courier shows up at their
home.

**Validation gaps:**

1. **Backend.** `routers/shipping.py:117-125` checks
   `order.shipping_city / shipping_name / shipping_phone` and
   `shipping_city_ref / shipping_warehouse_ref` (recipient side). It
   does **not** check `shop.np_sender_city_ref` or
   `shop.np_sender_warehouse_ref`.
2. **Frontend.** `DetailLogistics.tsx:561` disables the create button
   when **the recipient** warehouse is missing. It does **not** look at
   the shop's sender configuration at all (the order detail page has no
   reason to know about shop-level NP setup).

**Fix path** (will become NP-FIX-1):

- Backend: add an explicit pre-flight check in the TTN handler — if
  `shop.np_sender_city_ref` or `shop.np_sender_warehouse_ref` is
  missing, return `400` with a clear error like *"Shop's Nova Poshta
  sender warehouse is not configured. Set it in Shops → Logistics (NP)."*
- Frontend: surface the same error as a toast and link to the shop
  settings page. Optionally pre-flight on order load and show a
  passive warning banner.
- Tests: at least one pytest case asserting 400 when sender warehouse
  is unset, and one asserting 200 when set. This is the **first NP test
  in the codebase**.

---

## 5. Competitive Reference

What other Ukrainian-market CRMs / shipping plugins do that we don't:

| Feature | OrderHub | KeyCRM | Eltrino Shopify | OpenCart NP plugin |
|---|---|---|---|---|
| Selectable Service Type (W2W / W2D / D2W / D2D) | No (W2W only) | Yes | Yes | Yes |
| Auto status sync (tracking) | No | Yes | Yes | Yes |
| Label PDF / print | No | Yes | Yes (multi-format) | Yes |
| Add TTN to register (batch) | No | Yes | Partial | No |
| Multiple sender configs per shop | No | Yes | Yes | Yes |
| Auto-update order status on delivery | No | Yes | Yes | Partial |
| One-click TTN create | Yes | Yes | Yes | Yes |
| TTN delete/cancel | Yes | Yes | Yes | Partial |
| COD with custom amount | Yes | Yes | Yes | Yes |
| Webhook receiver from NP | No | Yes (v1.0) | No (polling) | No |

OrderHub's **unique strength** vs all of the above: server-side
Fernet-encrypted API keys with key masking in UI. Most off-the-shelf
plugins store the key in plain config or per-store-secrets without
masking. Keep this property in any future NP work.

---

## 6. Prioritized Fix List

Each item is sized as **S/M/L** (rough effort: S = single file backend
change + tests, M = backend + frontend, L = multi-sprint with schema
changes). Order is by **safety + value** (the incident-triggering bug
first, then user-visible UX gaps, then nice-to-haves).

| Priority | Fix | Size | Why now |
|---|---|---|---|
| **NP-FIX-1** | Validate sender warehouse before TTN create (backend + frontend) | S | Resolves the courier-dispatch incident. Prerequisite for re-enabling live NP. |
| **NP-FIX-2** | Add backend pytest coverage of NP service + router (mocked HTTP) | S | Right now we have **zero** tests. Every fix below is unsafe to land without this in place first. |
| **NP-FIX-3** | Configure a separate test NP account + dev-only shop entry; document the workflow | S | Lets us run end-to-end tests without risking real shipments. |
| **NP-FIX-4** | Selectable Service Type (W2W default, expose W2D / D2W / D2D in TTN form) | M | Significant operator-facing gap; competitors all support it. |
| **NP-FIX-5** | TTN tracking — periodic poll job that calls `TrackingDocument.getStatusDocuments` and updates `Order.shipping_status` / sets `ttn_printed` etc. | M | High UX value; lets the operator see live status without leaving OrderHub. |
| **NP-FIX-6** | Surface NP-specific error messages on the frontend (don't flatten to "Failed to communicate") | S | Fast win, helps operator self-diagnose. |
| **NP-FIX-7** | TTN print / label PDF generation via `getDocumentPrint` | M | Required for any operator who actually fulfils orders. |
| **NP-FIX-8** | Migrate to NP API v1.0 (new portal) — JWT auth, webhooks, pickups, sandbox | L | Strategic, large scope. Defer until 1-7 are stable. Open question whether v2.0 will eventually be sunset. |

### Out of scope for the immediate NP-FIX round

- Multiple TTNs per order (split shipments).
- Adding TTN to NP register (batch print convenience).
- International shipments (NP is primarily domestic; v1.0 covers more).

---

## 7. Open Questions for the User

1. **Do you have a test NP account ready?** If not, NP-FIX-3 becomes
   the actual first sprint (we need a key before we can write tests
   that exercise the full TTN path).
2. **NP-FIX-1 fix shape — strict or lenient?** Strict: hard block at
   400 when sender warehouse is missing, with a link to shop settings.
   Lenient: 400 with the same error message but also a `?force=true`
   query param to override (for advanced cases). I lean strict — there
   is no legitimate reason to bypass this; the whole problem is
   "I forgot to set it".
3. **Service Type default (NP-FIX-4).** Today: hardcoded
   `"WarehouseWarehouse"`. After we expose it: should the default still
   be W2W, with the operator opting in to other types per-order? Or
   should the default come from a per-shop setting? I lean per-shop
   setting (matches `np_default_payer_type` etc.).
4. **Tracking poll frequency (NP-FIX-5).** NP recommends polling at
   most every 4-6 hours per shipment. For OrderHub: poll every 4
   hours, batched? Or only on-demand when an operator opens the order
   detail page?
5. **API version migration (NP-FIX-8).** Acknowledge that this exists
   and we're aware. Do you want to keep v2.0 indefinitely or set a
   target sprint to evaluate v1.0?

---

## 8. Recommended Next Steps

1. **User reviews this doc**, confirms scope, answers §7 questions.
2. Start **NP-FIX-2** (test infrastructure) — smallest, lets every
   subsequent fix land safely.
3. Then **NP-FIX-1** (sender warehouse validation) — single file
   backend change + small frontend tweak. Closes the original
   incident.
4. Live re-test on the test account to confirm the fix.
5. Iterate through NP-FIX-4 → NP-FIX-7 by user priority.
6. Re-evaluate v1.0 migration (NP-FIX-8) after the legacy fixes are
   stable.

---

## Sources

- [Generating API keys for Nova Post API][np-keys] — confirms test API key flow
- [Nova Post API portal sitemap][np-sitemap] — confirms Testing page, Webhooks, Pickups exist in v1.0
- [Nova Poshta v2.0 docs (lis-dev/nova-poshta-api-2)][np-v2-php] — community PHP client, the ServiceType / SenderAddress contract
- [Nova Poshta Service Shopify App (Eltrino)][np-shopify-app] — competitive reference for Service Type selection + label PDF
- [KeyCRM Nova Poshta integration features][keycrm] — competitive reference for tracking, register, multi-sender

[np-keys]: https://api-portal.novapost.com/en/api-nova-post/start/api-keys/index.html
[np-sitemap]: https://api-portal.novapost.com/sitemap.md
[np-v2-php]: https://github.com/lis-dev/nova-poshta-api-2
[np-shopify-app]: https://apps.shopify.com/nova-poshta-service
[keycrm]: https://doitwell.ua/en/keycrm-2/

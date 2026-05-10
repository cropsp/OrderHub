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
`ttn_printed` flag exists in the model + schemas + frontend types
(`schemas/order.py:88`, `frontend/src/types/common.ts:116`) but **no
automatic flow sets it** — there is no print endpoint, no tracking
sync, no `getDocumentPrint` integration. Technically a `PATCH /orders/{id}`
could set it manually if the frontend exposed the toggle, but no UI
does today. See §3 finding.

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
| Sender warehouse selection in shop settings | Done | `Shop.np_sender_warehouse_ref` column + Shop-edit modal Logistics (NP) tab (`pages/ShopsPage.tsx:407`) with city/warehouse Select dropdowns | NP-P3. Field is exposed for editing but **not required-validated at TTN-create time** — that's the §4 gap. |
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

## 7. Decisions (locked 2026-05-09)

After reviewing this audit, the user confirmed the following positions
on the open questions. Each decision is recorded here as a binding input
to the NP-FIX-* sprints below — re-litigate explicitly only if new
information appears.

### Q1 — Test environment

**Decision: dev shop on the user's personal NP account, set up after
NP-FIX-2 + NP-FIX-1 land.** No formal sandbox is available for UA
clients (the v1.0 stage environment at
`api-stage.novapost.pl/v.1.0/` explicitly rejects UA phone numbers per
the `/test-api-keys` endpoint contract). The user has a personal NP
account separate from Lamamarka's business entity; an API key issued
on that account, paired with a sender warehouse near the user's
personal address, gives the closest practical equivalent of a sandbox.

Implementation note: the dev-shop setup itself does **not** require
any code changes. It's a manual operator workflow:

1. Generate an API key on the personal NP account at
   `new.novaposhta.ua → Settings → Security`.
2. Create a new shop in OrderHub with `platform = MANUAL`.
3. Configure NP credentials on that shop (api_key, sender name +
   phone, sender city, sender warehouse — the warehouse should be a
   nearby NP branch the user controls, not a home address).
4. Use this shop for all real-API smoke tests of NP-FIX-4 onwards.

This task is folded into NP-FIX-3 below as a documented checklist
rather than a code sprint.

### Q2 — NP-FIX-1 fix shape

**Decision: strict.** Backend rejects with `400 Bad Request` when
`shop.np_sender_city_ref` or `shop.np_sender_warehouse_ref` is not
set. No `?force=true` override, no soft warning. The error message
points the operator to Shops → Logistics (NP) settings.

Rationale: the original incident is exactly the
"I-forgot-to-configure-it" pattern. A bypass mechanism re-introduces
the same risk. There is no legitimate use case for creating a TTN
without a sender warehouse — NP itself silently downgrades to courier
pickup, which is what bit us.

### Q3 — Default Service Type (NP-FIX-4)

**Decision: per-shop default, exposed via a new
`Shop.np_default_service_type` column.** Symmetric with the existing
`np_default_payer_type`, `np_default_payment_method`,
`np_default_weight_kg`, `np_default_volume_m3` columns. Default value
on creation: `"WarehouseWarehouse"` (matches today's hardcoded
behaviour, no backwards regression). Operators can override per-order
in the TTN form when needed.

### Q4 — Tracking poll cadence (NP-FIX-5)

**Decision: hybrid — batch poll every 4 hours + manual refresh
button on the order detail panel.** Background batch covers the
default flow without operator action; manual refresh gives the
operator agency when they want a fresher status. This stays well
within NP's recommended polling rate (≥ 4-6h per shipment) even
if the operator hits Refresh aggressively, because the manual path
hits only one TTN at a time.

### Q5 — v2.0 vs v1.0 migration (NP-FIX-8)

**Decision: stay on v2.0 for the foreseeable future.** Migration to
v1.0 is large (different auth flow with JWT, different endpoint
structure, different payload shapes) and the immediate NP-FIX list
fully covers operator pain on v2.0. v1.0 has features v2.0 lacks
(webhooks, pickups, formal sandbox), but those are
nice-to-haves, not blockers. Re-evaluate only if NP announces v2.0
sunset or if a v1.0-only feature becomes a hard requirement.

---

## 8. Recommended Next Steps (updated 2026-05-09)

1. **NP-FIX-2 — pytest infrastructure (CC sprint).** Mocks
   `httpx.AsyncClient` and exercises the `NovaPoshtaClient` + router
   paths without touching any real NP endpoint. This is the very
   first NP test in the codebase and is a hard prerequisite for
   every subsequent NP-FIX sprint. Does **not** require the dev
   shop because all HTTP is mocked.
2. **NP-FIX-1 — sender warehouse validation (CC sprint).** Pure
   server-side guard: rejects the TTN-create request before any NP
   API call when sender warehouse / city is unset. Verified through
   the mocked tests added in NP-FIX-2 plus a manual smoke (temporarily
   `NULL` `np_sender_warehouse_ref` on the Lamamarka shop via
   `psql`, click "Generate TTN" in the UI, expect 400 toast, restore
   the column). **Does not require the dev shop** because validation
   blocks before NP is contacted.
3. **NP-FIX-3 — dev shop setup (user manual step, ~15-20 min).**
   The user creates the dev shop per the checklist in §7 Q1
   above. Output: a new OrderHub shop with personal NP credentials,
   ready to host dummy orders for E2E NP-API tests in subsequent
   sprints. No code changes; the audit doc is the deliverable.
4. **NP-FIX-4 — selectable Service Type (CC sprint).** Adds the
   `Shop.np_default_service_type` column (Alembic migration), the
   shop-edit UI control to set it, and a per-order override on the
   TTN form. First sprint that uses the dev shop for E2E
   verification.
5. **NP-FIX-5 — tracking poll job + manual refresh (CC sprint).**
   Plugs into the existing `backend/scheduler.py` (APScheduler
   `AsyncIOScheduler`, already runs `run_shopify_sync` periodically)
   — adds a parallel `run_np_tracking_poll` job that calls
   `TrackingDocument.getStatusDocuments` for active TTNs and updates
   `Order.shipping_status`. Plus a frontend refresh button on Order
   Detail for on-demand refresh.
6. **NP-FIX-6 — frontend NP error surfacing (CC sprint).**
   Replace generic "Failed to communicate" toasts with NP's specific
   error strings, which the v2.0 API already returns in
   `data.errors[]` (see `services/nova_poshta.py:42-45`). The
   backend currently flattens these into a 400 detail string —
   that's the surface to expand.
7. **NP-FIX-7 — TTN print PDF (CC sprint).** Requires a new
   NP method `getDocumentPrint` plus a frontend download path.
8. **NP-FIX-8 — v1.0 migration (deferred).** Re-evaluate after
   1-7 are stable, only on external trigger (sunset announcement,
   webhook requirement, etc.).

The standard cycle (`task.md` → CC plan review → execute → smoke →
post-fix notes in `implementation_plan.md`) applies to every CC
sprint above.

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

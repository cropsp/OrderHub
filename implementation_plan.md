# Implementation Plan - OrderHub CRM

## Sprint History
- Sprint 1 status: `DONE` (Core Architecture)
- Sprint 2 status: `DONE` (Database & Auth)
- Sprint 3 status: `DONE` (Frontend Scaffolding)
- Sprint 4 status: `DONE` (Core Frontend)
- Sprint 5 status: `DONE` (Dashboard & Management)
- Sprint 6 status: `DONE` (Integrations & MCP)
- Sprint 7 status: `DONE` (Stability & Recovery)
- Sprint 8 status: `DONE` (Full Persistence)
- Sprint 9 status: `DONE` (Attachments & Designer Workflow)
- Sprint 10 status: `DONE` (Shop Management & Manual Entry)
- UI Modernization (Block 11) status: `DONE` (Customers, Users, Imports, Dashboard unified)
- Sprint PC-A status: `DONE` (Foundation: Pricing, Cost & Stock — commit `0bf0583`)
- Sprint PC-B status: `DONE` (Product Detail Page — commit `f99494f`)
- Sprint PC-B.1 status: `DONE` (Shopify-style Inline Product Editing — commit `bf9f8ba`)
- Sprint PC-B.2 status: `DONE` (Column Visibility Picker on ProductsPage — commit `46783bf`)
- Sprint 11 status: `NOT STARTED` (Production & Deployment)
- **Active Roadmap (2026-05-08):** Bug-Hunt & Imports — see Unified Backlog → "Active Roadmap" section.

## Architecture Schematic

```mermaid
graph TD
    subgraph Presentation ["Presentation Layer (UI/UX)"]
        Dashboard["Dashboard & Analytics"]
        OrdersDesk["Orders Table & Kanban"]
        Settings["System Settings & Users"]
    end

    subgraph Modules ["Feature Modules (Pluggable)"]
        NP["Nova Poshta Integration"]
        Shopify["Shopify Auto-Sync"]
        Etsy["Etsy CSV Parser"]
        Attachments["Designer Workflow (Uploads)"]
    end

    subgraph Core ["Core Domain (Business Logic)"]
        OrderService["Order Service (Status, Audit)"]
        ShopService["Shop & Currency Management"]
        MCP["MCP Server (AI Interaction)"]
    end

    subgraph Foundation ["Foundation (Stability & Security)"]
        Auth["Auth Service (JWT, Rotation)"]
        DB["Database (SQLAlchemy, Migrations)"]
        API["API Client (Interceptors, Intercept)"]
        Resilience["API Resilience (Retries, Timeouts)"]
    end

    Presentation --> Modules
    Modules --> Core
    Core --> Foundation
    Foundation -.-> SEC["Security Guards"]
```

## Actual Repository Snapshot

Verified against the current tree (See [Audit Report 2026-04-21](docs/audit/REPORT_2026_04_21.md) for details):

**Backend:**
- Fully implemented routers for all modules (Orders, Shops, Dashboard, Imports, Users, Auth, Shipping, MCP).
- Services for Shopify Sync, Nova Poshta, Encryption, and Etsy parsing are active.
- **NEW**: Persistent rotating file logging system implemented (backend/logs/server.log).

**Frontend:**
- **NEW**: Full-page `CreateOrderPage.tsx` replaces restrictive modal dialog.
- **NEW**: Modernized directory pages (`CustomersPage`, `UsersPage`) with deterministic avatars.
- **NEW**: Strategic `DashboardPage` with high-contrast intelligence widgets.
- **NEW**: Extraction-focused `ImportsPage` with step-based sync workflow.

### Component Hierarchy (Frontend)
```
frontend/src/
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx — modern zinc-950 shell
│   │   └── Topbar.tsx — premium header with user context
│   ├── ui/
│   │   ├── StatusBadge.tsx — multi-color status pill
│   │   ├── EmptyState.tsx — standardized feedback
│   │   └── Toast.tsx — custom notification system
│   └── orders/
│       ├── OrdersLayout.tsx — search, filter, and view orchestration
│       ├── OrdersTable.tsx — redesigned data-dense table
│       ├── PipelineBoard.tsx — updated kanban cards
│       ├── StatusTabs.tsx — grouped status navigation
│       ├── OrderDetailPanel.tsx — modular console
│       └── detail/ — 8 intelligence sub-components
├── utils/
│   ├── avatar.ts — initials & color generation
│   └── shopTheme.ts — deterministic shop branding
├── store/
│   └── authStore.ts — single-purpose auth state
└── api/
    └── ...
```

## Unified Backlog (Pending Tasks & Fixes)

### Active Roadmap — Bug-Hunt & Imports (2026-05-08)

Source-of-truth for current focus. Sprints below are sequenced from most-critical
to least-critical based on the 2026-05-08 planning conversation. Sprints land in
`task.md` one at a time, get reviewed with the planning agent, then executed by
Claude Code. As each closes, its `Status` flips to `DONE` and post-fix notes are
captured here. The "Explicitly deferred" table at the bottom is exhaustive — if
a backlog item isn't in either an active sprint or that table, surface it before
starting work on it.

---

**Round 1 — UX micro-fix**

**Sprint UX-1 — Products page remembers last selected shop** (Status: `DONE` — commit `eb32eb6`)

Goal: When the user navigates to `/products`, default the active shop to the last
one they viewed there. Persist via `localStorage` under
`orderhub:productsPage:lastShopId` (mirrors the `orderhub:productsTable:columnVisibility`
pattern from PC-B.2).

| ID | Task | Scope | Status |
|---|---|---|---|
| UX-1-1 | Read+write `orderhub:productsPage:lastShopId` in `ProductsPage.tsx` | frontend | DONE |
| UX-1-2 | On mount: if stored `shop_id` resolves against `useShops()`, restore as initial selection; else fall back to current default | frontend | DONE |
| UX-1-3 | Archived/deleted shop in localStorage gracefully ignored — no error, no console noise | frontend | DONE |

**Post-fix notes (UX-1):**
- **Design pivot from `useEffect` to `useMemo`.** The original plan called for a
  `useRef` + `useEffect([shops])` pair to apply the stored preference once
  `useShops()` resolved. The repo's ESLint configuration flags `setState`
  inside effect bodies via `react-hooks/set-state-in-effect`, so the
  implementation pivoted to a **`useMemo`-derived `effectiveShopId`**. No
  effect, no extra render cycle — validation happens inline.
- Two-state split: `selectedShopId` (lazy-init from `localStorage`) drives
  the `ShopSelector` dropdown and the write effect. `effectiveShopId`
  (`null` until shops load and the stored UUID resolves) drives **all
  product-related logic** — query, actions, conditional rendering. The
  divergence between the two values is intentional and only observable
  in the transient invalid-UUID case (see follow-up below).
- **Storage key:** `orderhub:productsPage:lastShopId`, single string UUID,
  reusing the `orderhub:` namespace established in PC-B.2.
- **Write effect skips `null` transitions** to preserve the stored shop_id
  when the user returns to a placeholder state. There is no explicit
  "Clear shop" gesture today, so this is a one-way ratchet — once a shop
  is picked, the preference sticks until a different shop is chosen.
- **`useShops()` deduped by React Query** — the new validation hook does
  not add a network call beyond what `ShopSelector` already makes
  internally on mount.

**Verified by smoke test:**
- Switch to KoraKlenu → /dashboard → /products → KoraKlenu still active. ✓
- Hard reload (F5) → KoraKlenu sticks. ✓
- DevTools → `localStorage` → `orderhub:productsPage:lastShopId` =
  `c2bb2b4e-60d1-40eb-b221-4b2eabcd96fd`. ✓
- Manually set the key to `00000000-0000-0000-0000-000000000000` → reload →
  graceful fallback to "No shop selected" placeholder, no console error,
  no toast. ✓
- Recovery: pick KoraKlenu after invalid state → `localStorage` overwrites
  with the correct UUID via the write effect. ✓

**Found during UX-1 smoke test, kept out of scope:**
- **Cosmetic only:** after a reload with an invalid stored UUID, the
  `ShopSelector` dropdown renders **empty** rather than falling back to
  the "Select a manual shop" placeholder. Cause: `selectedShopId` retains
  the stale UUID while `effectiveShopId` is `null` — the two state vars
  diverge in this transient case. Triggers only when `localStorage` is
  manipulated directly (DevTools, browser-extension, manual deletion of
  a shop, etc.); invisible in normal usage. Possible follow-up: clear
  `selectedShopId` to `null` when the validation in `useMemo` fails. Not
  filed as a bug; revisit only if a user actually hits this path.
- **Test 5 from the original verification list (multi-shop persistence)
  was not exercised** — current seed data has exactly one MANUAL shop
  (KoraKlenu). The fix logic is shop-agnostic, so it should hold for
  additional manual shops once they exist. Re-test when a second one
  appears (or after IMP-1/IMP-2 when imports start landing real data).

---

**Round 2 — Imports auto-populate catalog**

**Sprint IMP-1 — Etsy CSV importer auto-creates Products** (Status: `DONE` — commit `2d4b2f1`)

Goal: During Etsy CSV import, also INSERT into `products` and `product_variants`
for SKUs not already in catalog. Pull every catalog-relevant field the CSV
offers; the user adjusts visibility / cost / dimensions later in the catalog
UI. **Skip-on-existing** by `(shop_id, sku)` — full skip, no field updates
(preserves local edits). Empty SKU is generated as `etsy-{listing_id}` for the
first blank variant, `etsy-{listing_id}-{n}` for subsequent. `external_ref =
listing_id` on Product. **No retroactive linking** of existing `order_items` to
newly-created variants (parked).

| ID | Task | Scope | Status |
|---|---|---|---|
| IMP-1-1 | Extend `services/etsy_parser.py` `parse_etsy_csv` to emit Product/Variant inserts alongside Order/OrderItem inserts | backend | DONE |
| IMP-1-2 | Skip-on-existing-SKU logic keyed by `(shop_id, sku)` — full skip, no field updates | backend | DONE |
| IMP-1-3 | Empty-SKU fallback: generate `etsy-{listing_id}[-{n}]` | backend | DONE |
| IMP-1-4 | Set `external_ref = listing_id` on Product; Variant `external_ref` left null (CSV carries no per-variation external id) | backend | DONE |
| IMP-1-5 | `ImportResult` extended with `products_created` and `variants_created` counters (default 0 — backwards-compatible with non-Etsy imports) | backend | DONE |
| IMP-1-6 | Tests: 15 new vitest cases covering skip-on-existing, empty-SKU fallback, lazy Product insert, in-import idempotency, blank Listing ID skip, FK linking, etc. | backend tests | DONE |

**Post-sprint notes:**
- **Plan deviation: no preview step exists for Etsy CSV.** The original
  `task.md` framed the change as "extend the existing two-step CSV
  preview/confirm flow" — that two-step flow is for **bulk product CSV
  import** (different code path). Etsy CSV for **orders** is
  single-step (`POST /api/imports/etsy` parses + commits in one request).
  Adopted: extend `ImportResult` with two counters; the response surfaces
  the catalog-side numbers without needing a new preview UI. Frontend
  toast surface deferred — backend correctness verified via DevTools
  Network response and direct API calls.
- **Mapping rule (Q1 from planning):** `Product = unique Listing ID per
  shop` (identity = `(shop_id, external_ref=listing_id)`). `Variant =
  unique (Listing ID, effective_sku) within that listing` where
  `effective_sku = csv.SKU` if non-blank, otherwise the generated
  fallback. `Variations` text does **not** participate in identity — it
  is informational only and goes into `ProductVariant.variant_name`
  verbatim, truncated to 255. Two CSV rows of the same listing with
  matching SKU but different Variations collapse to one variant; first
  writer wins on `variant_name`. **This rule has a known gap on
  blank-SKU rows — see BUG-5 below.**
- **Hook placement (Q3):** inline single-pass. New helper
  `_ensure_catalog_row(db, shop, row, catalog_cache)` runs before each
  `db.add(OrderItem)` in `parse_etsy_csv`. Per-import in-memory cache
  `dict[listing_id, dict]` survives across rows of one CSV (avoids
  duplicate Product inserts within a single import).
- **Backend gate option (Q6):** Option (B) — kept
  `require_platform(MANUAL)` on the LIST endpoint as well as POST +
  bulk-CSV. Catalog rows landed in DB but were unreachable through any
  UI; resolved separately by **CAT-VIS-1** (see Bug Fixes 2026-05-08).
- **Lazy Product insert (Q7):** Product row is appended to the session
  only after **at least one variant** clears the
  `is_sku_taken(shop_id, effective_sku)` check. A listing whose every
  variant SKU collides with existing shop-wide SKUs leaves zero new
  rows behind — no orphan Products.
- **Optional Q5 — FK link to OrderItem accepted.** Freshly-inserted
  `OrderItem` rows now set `product_variant_id` to the just-created
  variant's id, so the "Unlinked" badge is gone for new imports
  going forward. Snapshot fields (`snapshot_weight_g`, etc.) left
  `None` to avoid polluting parcel calculation with the IMP-1 zero
  sentinel; user backfills physical dimensions later, then existing
  service flows refresh snapshots.
- **Pydantic schema gotcha caught at planning time:** the existing
  `CatalogService.create_product()` is unusable from the importer
  because `ProductVariantCreate` enforces `gt=0` on the four physical
  dimension fields, conflicting with the IMP-1 sentinel-`0` rule. The
  importer instantiates `Product` and `ProductVariant` ORM models
  directly with `db.add(...)` and a single `db.flush()` to get
  `product_id` before inserting variants. (This same `gt=0` constraint
  caused **BUG-6** when CAT-VIS-1 later opened the Read path —
  resolved by splitting the validators Create-only.)
- Smoke verified: a real Etsy CSV imported to LeatherCraft UA produced
  7 unique Products (one per Listing ID), 11 Variants (incl. 5
  spurious for listing 4343151753 — see BUG-5), FK link working on
  every freshly-imported `OrderItem` ("Personalized Bat ID Card
  Holder" order shows no "Unlinked" badge after import).

---

**Sprint BUG-5 — Blank-SKU dedup by Variations** (Status: `DONE` — commit `28440f7`)

Goal: Surfaced during IMP-1 smoke test against a real Etsy CSV. The original
`_compute_effective_sku` helper incremented a per-listing positional counter on
**every** blank-SKU row, regardless of whether that row represented a logically
distinct variant. Real-world Etsy data has many rows with the same listing +
same blank SKU + same Variations (just different buyers); listing 4343151753
in LeatherCraft UA produced **5 catalog variants** where only **2 distinct
Variations** existed in the source CSV.

Fix: content-keyed SKU generation. New `_normalize_variations(raw)` helper
strips all whitespace and lowercases the Variations text; the result is
md5-hashed, truncated to 8 hex chars, and appended as
`etsy-{listing_id}-{hash}`. Empty Variations → `etsy-{listing_id}` (no suffix).
Same Variations → same generated SKU → `is_sku_taken` short-circuits on
re-import; variant_name preserves the **original untouched** Variations text
(first-writer-wins).

**Post-sprint notes:**
- **Plan deviation accepted: strip-all-whitespace, not collapse-to-single-space.**
  The original task.md spec said "collapse internal runs of whitespace into
  single spaces", but CC noticed that didn't satisfy the verification test
  demanding `"Color:Red, Pakning:Single"` and `"Color:Red,Pakning:Single"`
  (one space after comma vs none) collapse to the same SKU. Switched to
  `re.sub(r"\s+", "", raw.strip()).lower()` — strip all whitespace before
  hashing. Trade-off: word boundaries inside a single value (e.g. `"Bat ID"`
  → `"BatID"` for hashing only) lose meaning. **`variant_name` preserves
  the human form** so the catalog UI is unaffected. False-positive risk
  (two truly distinct variations differing only by whitespace) is
  vanishingly rare in real Etsy data — sellers don't author variants like
  `"Sky Blue"` vs `"SkyBlue"`. Acceptable trade-off; documented here so
  future readers don't think it's a bug.
- **Hash collision is impossible by construction within a shop**: full SKU
  always includes the `listing_id` prefix. Even if two distinct listings
  happen to share Variations text and therefore share an 8-char suffix
  (observed: `Color:Black` → `4da64648` for listings 4346731923, 4349699409,
  4359285143 in this test data), the full SKUs `etsy-4346731923-4da64648`
  / `etsy-4349699409-4da64648` / `etsy-4359285143-4da64648` are pairwise
  unique. `is_sku_taken` checks the full string — no collision.
- **`cache["skus_in_listing"]` removed.** Helper signature changed from
  `_compute_effective_sku(listing_id, raw_sku, used_in_listing: Set[str])`
  to `_compute_effective_sku(listing_id, raw_sku, variations)`. The set
  is no longer needed because generation is content-deterministic.
  In-import idempotency is still covered by the existing
  `cache["variants_by_sku"]` map (same SKU appearing twice in a single
  import returns the cached variant).
- 7 new pytest cases covering BUG-5 regression + new edge cases (empty,
  whitespace-only, case differences, distinct variations, mixed
  empty/non-empty within a listing); 2 obsolete tests
  (`subsequent_blanks_get_numeric_suffix`,
  `skips_already_taken_numeric_suffixes`) removed; 4 existing tests
  updated for the new helper signature. Total: **19/19 catalog tests +
  43/43 backend suite green**.
- **Smoke test confirmed (wipe + reimport ritual):**
  - LeatherCraft UA wiped: 24 orders + 7 products deleted via
    SQL `DELETE` (FK cascade on `orders.id` and `products.id` did the rest
    — order_items, status_history, attachments, product_variants all
    cleaned in two `DELETE` statements).
  - Same Etsy CSV re-imported via `/imports`. Listing 4343151753
    produced **2 variants** (collapse 5 → 2 confirmed). Total
    LeatherCraft UA dropped from 11 → **8 variants** (7 products × correct
    variant counts).
  - SKUs of the auto-imported variants: `etsy-4343151753-dbaa9d00`
    (`Color:Red,Pakning:Bat ID with Gift Box`) and
    `etsy-4343151753-ab0def3e` (`Color:Red,Pakning:Single Bat ID`).
  - `variant_name` on each preserves the **first-writer-wins original**
    Variations text — untouched case, untouched whitespace, untouched
    punctuation.
  - **Idempotency check**: same CSV re-uploaded a second time →
    response shows `products_created=0, variants_created=0`; catalog
    unchanged. Hash-deterministic generation working as designed.

---

**Sprint IMP-2 — Shopify sync auto-creates Products + line items** (Status: `DONE` — commit `afbfd6c`)

Goal: Initially scoped as "mirror IMP-1 for Shopify" — but the existing Shopify
sync turned out **not** to ingest line items at all (the GraphQL query never
fetched `lineItems`, so OrderHub-side `OrderItem` rows were empty for every
synced order). IMP-2 therefore became three coupled changes in one sprint:
extend the GraphQL query to pull line items, map them into `OrderItemCreate`
payloads, and add catalog auto-create with the same skip-on-existing semantics
as IMP-1. Skip-if-exists by `(shop_id, sku)`; Shopify `variant.id` numeric
tail → `Variant.external_ref`; empty SKU →
`shopify-{shopify_product_id}-{shopify_variant_id}`.

| ID | Task | Scope | Status |
|---|---|---|---|
| IMP-2-1 | Extract IMP-1's catalog ensure logic to a shared helper `services/catalog_import.py` (`ensure_catalog_row` + `_weight_to_grams`) | backend | DONE |
| IMP-2-2 | Etsy parser refactor: `_ensure_catalog_row` becomes a thin wrapper that resolves the BUG-5 effective SKU then delegates to the shared helper | backend | DONE |
| IMP-2-3 | Extend Shopify `ORDERS_QUERY` to fetch `lineItems(first: 50)` with `variant { id, sku, title, product { id title }, inventoryItem.measurement.weight { value, unit } }` | backend | DONE |
| IMP-2-4 | Rewrite `sync_shop_orders`: build `OrderItemCreate` per line item, call `ensure_catalog_row` per item, explicit `db.flush()` before `create_order`, return `ImportResult` (counters + errors), per-order error isolation | backend | DONE |
| IMP-2-5 | Router `POST /shops/{id}/sync` response shape: merge `synced_count` (back-compat) with full `ImportResult` payload | backend | DONE |
| IMP-2-6 | 28 new pytest cases (`test_shopify_sync_catalog.py`): GID parsing, weight-unit conversion (parametrized G/KG/OZ/LB), fresh sync, re-sync (zero), blank-SKU fallback, blocked-SKU lazy insert, in-sync dedup, flush ordering, null variant/product, "Default Title" sentinel, error isolation, router response | backend tests | DONE |

**Post-sprint notes:**
- **Q1 — Catalog helper extracted.** New `backend/services/catalog_import.py`
  hosts `ensure_catalog_row(...)` with a platform-agnostic signature
  (already-resolved SKU + product / variant fields + cache + counters).
  Etsy parser keeps `_compute_effective_sku` (BUG-5 hash logic) locally and
  delegates the rest. Confirmed second-consumer pattern: the abstraction
  earns its keep when there are two real callers, not one. **Helper does
  no `db.flush()`** — caller controls the unit-of-work boundary. **Cache
  key is `external_product_id` only** — each invocation is per-shop scope,
  so collision is impossible within a call (documented in helper's
  docstring).
- **Q2 — Real weight pulled from Shopify.** New `_weight_to_grams(weight)`
  helper accepts the raw `{value, unit}` GraphQL subobject and converts to
  grams: GRAMS×1, KILOGRAMS×1000, OUNCES×28.3495, POUNDS×453.592, rounded
  to int. Falls back to `0` when the field is null/missing or unit is
  unknown. Length / width / height stay `0` because Shopify doesn't
  expose those via the standard Admin API query.
- **Q3 — `ImportResult` reused, not duplicated.** The schema already had
  the right shape (`imported, skipped, errors, products_created,
  variants_created`) after IMP-1 extended it; reuse avoids a parallel
  `SyncResult` schema with the same semantics. `errors` for Shopify
  carries per-order failures (catch-and-continue) instead of CSV's
  per-row, but the structural meaning is the same. Router preserves
  back-compat by returning
  `{"status": "success", "synced_count": result.imported, **result.model_dump()}` —
  any frontend consumer of `synced_count` still works, new counters are
  present.
- **Critical implementation insight: explicit `await db.flush()` before
  `create_order`.** `_apply_variant_snapshot` (`order_service.py:158-163`)
  runs `select(ProductVariant).join(Product)` to fetch the variant before
  copying its weight/dims/title onto the OrderItem. SQLAlchemy's default
  autoflush *would* surface our pending `db.add(...)` catalog inserts —
  but relying on autoflush is fragile. CC added an explicit flush after
  the catalog loop, before `create_order`, so the unit-of-work boundary
  is defensive and obvious. Without it,
  `_apply_variant_snapshot` raises `HTTPException(400, "Product variant
  not found...")` and aborts the order. Caught by **test #7
  (`test_snapshot_fields_copied`)** which would have failed otherwise.
- **"Default Title" sentinel.** Shopify products without variations get a
  single variant with `title = "Default Title"`. Mapping that verbatim to
  `variant_name` would make the catalog UI noisy. The sync stores
  `variant_name = None` when the variant title is `"Default Title"` or
  empty.
- **Per-order error isolation.** A single bad order (e.g. malformed line
  item, missing variant data) is caught, logged via `logger.exception`,
  and appended to `errors`. The sync continues on the remaining orders.
  Test #15 covers this.
- **Live-Shopify E2E smoke (post-commit):** the user pointed
  `MyShopify Store` (renamed to **Lamamarka Shopify**) at a real
  Shopify dev store URL `08f330-ef.myshopify.com` and pasted a real
  Admin API token. `POST /shops/{id}/sync` returned 200 with
  `imported=50, skipped=0, products_created=11, variants_created=14,
  errors=[]`. Verified through the API and the browser:
  - **Line items pulled.** Each synced order has the right number of
    `OrderItem` rows (e.g. order `7148183421084` → 1 item: "Heavy
    Mushroom Keychain", qty 1, unit_price $14.99).
  - **Real weights from Shopify.** All 14 variants got non-zero
    `weight_g` (distribution: 100g × 10, 200g × 2, 300g × 2). Q2 unit
    conversion verified end-to-end against real `inventoryItem.measurement.weight`
    payloads.
  - **FK link populated.** `OrderItem.product_variant_id` set on
    every imported item; the catalog detail page shows no "Unlinked"
    badge.
  - **Snapshot fields copied.** `OrderItem.snapshot_weight_g`,
    `snapshot_title` populated correctly via `_apply_variant_snapshot`
    — the explicit `db.flush()` ordering is observably correct in
    production data.
  - **Lazy Product insert + dedup verified.** "Heavy Mushroom
    Keychain" appears in multiple orders → 1 Product, 1 Variant in
    catalog, all order items FK-linked to the same row.
  - **All variants got fallback SKUs** (`shopify-{product_id}-{variant_id}`).
    Lamamarka's Shopify variants have no SKU values assigned —
    legitimate for a small handmade catalog. Real-SKU code path
    works (covered by tests #3, #6) but had no real data to exercise
    on this shop.
  - **Idempotency verified.** Second sync on the same data:
    `imported=0, skipped=50, products_created=0, variants_created=0,
    errors=[]`. Hash + `(shop_id, sku)` shop-wide dedup short-circuits
    every path.
- **Cosmetic notes from the live smoke (not filed as bugs):**
  - **"Unknown Shopify Customer".** Shopify returned `null` for
    `customer.firstName/lastName` on every imported order — likely
    a missing app permission scope (`read_customers`) on the dev
    store's private app. The sync handles this gracefully via the
    existing `or "Unknown Shopify Customer"` fallback at
    `shopify_sync.py:157`. If the user wants real customer names,
    grant the missing scope on the Shopify side; no OrderHub code
    change required.
  - **Order title = Shopify `name` (`91890_1580`)** rather than the
    line-item title. The original sync code (pre-IMP-2) used
    `node.get("name")` for the order title and IMP-2 preserved that
    behaviour; the Etsy parser uses the first item title instead.
    Different by design — flag if the operator finds it confusing,
    but not in scope for IMP-2.
- **Known limitations** (called out, not blocking):
  - `lineItems(first: 50)` cap per order — orders with >50 line items
    will silently truncate. Realistic Etsy/Shopify orders are 1–5 items,
    so this is purely defensive. Add Shopify-side pagination as a
    follow-up if it ever surfaces.
  - GraphQL query cost increased ~500–800 points (within Shopify's
    1000-point default budget). Watch production logs if cost warnings
    appear; throttle `first: 50` orders if needed.

---

**Sprint BUG-8 — Shopify order title from first line item, not order code** (Status: `DONE` — commit `c91e321`)

Goal: Surfaced during IMP-2 live smoke against the real Lamamarka Shopify
store. The orders list PRODUCT column showed Shopify's order code (e.g.
`91890_1580`) instead of the line-item product title — Etsy-imported orders
already showed real product names because `etsy_parser.py:146-147` overrides
the synthetic placeholder with the first item's title. Shopify sync at
`shopify_sync.py:282` set `title = node.get("name") or f"Order #{external_id}"`
and never overrode, so the Shopify `order.name` (sequence code) leaked into
the OrderHub `Order.title` field.

Fix: single-expression change. When IMP-2 finishes building `items_payload`
inside the per-order try-block, prefer the first item's title; fall back to
`node.name` only when zero line items are present.

| ID | Task | Scope | Status |
|---|---|---|---|
| BUG-8-1 | Replace `title=node.get("name") or f"Order #{external_id}"` at `shopify_sync.py:282` with conditional that prefers `items_payload[0].title` when non-empty | backend | DONE |
| BUG-8-2 | 3 new pytest cases in `test_shopify_sync_catalog.py`: single-item regression, multi-item first-wins, empty-line-items fallback | backend tests | DONE |

**Post-sprint notes:**
- Final expression:
  ```python
  title=(items_payload[0].title if items_payload
         else node.get("name") or f"Order #{external_id}"),
  ```
  `items_payload` is built ~24 lines above the call site in the same try
  block, so it's already populated when `OrderCreate(...)` is constructed.
- **`"Unknown Item"` fallback inherited.** `OrderItemCreate.title` is set
  from `li.get("title") or "Unknown Item"` at line 259 — so a malformed
  Shopify line item with empty title becomes `"Unknown Item"` in the
  OrderItem AND propagates that same value to `Order.title`. No extra
  defensive code needed at the title site; the safety net is upstream.
- **Q3 verified concretely.** CC ran
  `grep -n "order\.title\|\.title ==" backend/tests/test_shopify_sync_catalog.py`
  in plan mode and found one match at line 451
  (`assert items[0].title == "Custom Engraving"`) which is a line-item
  assertion, not `order.title`. **Zero existing tests needed
  rewriting.** The 28 IMP-2 tests + 71-test suite stay green.
- 3 new tests added; total backend suite **74/74 green**.
- **Smoke verified end-to-end (post wipe+resync):**
  - Lamamarka Shopify wiped (50 orders + 11 products via two `DELETE`
    statements, FK CASCADE handled the rest).
  - Same Shopify sync re-triggered → identical counts (50 orders, 11
    products, 14 variants — sync is deterministic).
  - All 50 order titles in DB now match line-item product names
    (verified via API); **0 orders carry the `91890_*` code format**
    that was characteristic of the bug.
  - Browser smoke: `/orders` filtered by Lamamarka Shopify → PRODUCT
    column shows real names ("Heavy Mushroom Keychain",
    "Heavy-Duty Belt Carabiner", "Heavy-Duty Carabiner with Two",
    "Belt with Face", "Compact Commander Carabiner", …). Order detail
    page top title also reflects the line item.

---

---

**Sprint BUG-9 — Scheduler regression: consume `ImportResult` from `sync_shop_orders`** (Status: `DONE` — commit `de1112b`)

Goal: Latent regression discovered during NP-DISC code audit. IMP-2 (commit
`afbfd6c`) changed `sync_shop_orders` return type from `int` to
`ImportResult`, but `backend/scheduler.py:42-44` still did `if count > 0`
on the return value. `ImportResult > 0` raises `TypeError`; the
scheduler's `try / except Exception` block silently caught it and rolled
back. **Result:** every periodic 15-minute Shopify sync had been a silent
no-op since IMP-2 landed. Manual sync via the UI was unaffected (different
code path through `routers/shops.py`).

| ID | Task | Scope | Status |
|---|---|---|---|
| BUG-9-1 | `scheduler.py:42-49` — replace `count > 0` with `result.imported > 0`, conditional `(+N product[s], +N variant[s])` suffix on the success log when catalog counters non-zero, separate WARNING when `result.errors` non-empty | backend | DONE |
| BUG-9-2 | New `tests/test_scheduler.py` — 3 cases: success+catalog suffix, partial-success warning, silent-on-zero | backend tests | DONE |

**Post-sprint notes:**
- **Q1 — Idle silence preserved.** Periodic ticks against shops with
  zero new Shopify orders log nothing. Rationale: 96 lines/shop/day
  of "0 new orders" noise was rejected. The absence of a "Failed to
  sync …" line is the signal that the tick succeeded.
- **Q2 — Conditional catalog suffix on the success log.** Format:
  `Synced 3 orders for shop X` when only orders touched;
  `Synced 3 orders for shop X (+1 product, +2 variants)` when
  catalog also grew. Pluralization handled (`product` vs `products`,
  `variant` vs `variants`). Symmetric for variants-only or
  products-only edge cases.
- **Q3 — Per-shop WARNING when `result.errors` is non-empty.** IMP-2
  added per-order error isolation inside `sync_shop_orders` —
  malformed line items are caught and appended to `result.errors`
  rather than aborting the batch. The scheduler now surfaces the
  count of those per-order failures as a `WARNING` per shop, so
  ops watching `server.log` actually see partial failures instead
  of them being invisible. The catastrophic `try / except` outside
  the loop still catches network / GraphQL / DB-level failures and
  rolls back the per-shop transaction.
- **Net behavioural improvement** (caught by Opus during planning):
  before the fix, every periodic tick logged a `Failed to sync
  shop X: '>' not supported between instances of 'ImportResult'
  and 'int'` line per Shopify shop. After the fix, idle shops
  produce **zero** lines per tick — a strict reduction in log
  noise compared to even the original int-returning version
  (which at least worked but logged `Synced 0 orders` … wait, no,
  the original also gated on `count > 0`, so silent. So we're at
  parity with pre-IMP-2 behaviour.)
- **`db.commit()` boundary unchanged.** Inside the `try` block,
  unconditional commit on success path; rollback only inside the
  `except`. Per-order failures from `result.errors` are intentionally
  **not** rollback triggers — `sync_shop_orders` already isolated
  them, partial progress is real progress.
- **No new imports needed.** `ImportResult` is duck-typed via
  attribute access; the scheduler doesn't import the schema class
  itself.
- 3 new pytest cases added; total backend suite **77/77 green**.
- **Smoke test:** restart backend → wait one 15-minute scheduler tick
  → tail `backend/logs/server.log` → confirm no `'>' not supported
  between instances of 'ImportResult' and 'int'` errors. (Verified
  passively by the human reviewer; unit tests already cover all three
  behaviour paths so this is a sanity sweep, not a primary gate.)

---

**Round 3 — Nova Poshta initiative (separate cadence, no CC)**

**Sprint NP-DISC — Research, audit, and sandbox confirmation** (Status: `DONE` — deliverable `docs/integrations/nova-poshta-audit-2026-05.md`)

Goal: Produce `docs/integrations/nova-poshta-audit-2026-05.md`. **No code changes** —
discovery only. The planning agent drives the research and writes the doc;
the user observes and approves the deliverable. Claude Code is **not** involved
at this stage.

The doc will contain:
1. Competitive research — how 2-3 other CRM systems handle NP integration
   (TTN creation, label printing, tracking, sender warehouse handling).
2. Feature-by-feature audit of current OrderHub NP code
   (`backend/services/nova_poshta_service.py`, `backend/routers/shipping.py`,
   frontend NP forms) against the typical CRM feature set from #1.
3. Confirmation of NP sandbox/test API existence + auth requirements.
4. Prioritized fix list to drive subsequent NP-FIX-* sprints.

Triggering context: a previous live test produced an unintended courier
dispatch because no sender warehouse was selected on the TTN form. Rather
than add a defensive validation immediately, the user wants to research the
broader integration first, surface every related issue at once, and then
test fixes against the sandbox API instead of risking live calls.

| ID | Task | Scope | Status |
|---|---|---|---|
| NP-DISC-1 | Code audit OrderHub vs typical NP feature set | docs | DONE |
| NP-DISC-2 | NP sandbox/test API verification (existence, entrypoint, auth) | docs + small spike | DONE |
| NP-DISC-3 | Competitive research: 2-3 CRM systems' approach to NP | docs | DONE |
| NP-DISC-4 | Deliverable: `docs/integrations/nova-poshta-audit-2026-05.md` with findings + prioritized fix list | docs | DONE |

**Post-sprint notes:**
- **Deliverable:** `docs/integrations/nova-poshta-audit-2026-05.md` — full
  audit doc with 19-row feature inventory, root-cause analysis of the
  courier-dispatch incident, competitive reference against KeyCRM /
  Eltrino / OpenCart NP plugins, and a prioritized fix list (NP-FIX-1
  through NP-FIX-8 with S/M/L sizing).
- **Key audit findings:**
  - **Root cause of incident** is a single missing backend validation
    in `routers/shipping.py:213-234`. `SenderAddress` is passed
    verbatim from `shop.np_sender_warehouse_ref`; if that column is
    `NULL`, NP silently downgrades the request to courier pickup.
    Fix scope is one file, one validation block — that's NP-FIX-1.
  - **Zero NP-related backend tests today.** Regardless of any other
    fix, basic pytest coverage is a hard prerequisite — that's
    NP-FIX-2.
  - **No formal sandbox available for UA clients.** The new v1.0
    Stage environment at `api-stage.novapost.pl/v.1.0/` explicitly
    rejects UA phone numbers per the `/test-api-keys` contract.
    Workaround: dev shop on a personal NP account (separate from
    Lamamarka legal entity), captured in NP-FIX-3 as a manual
    operator checklist.
  - **OrderHub uses NP API v2.0**; v1.0 with JWT, webhooks, pickups
    exists but migration is deferred (NP-FIX-8) — current v2.0 covers
    operator pain on its own.
- **5 open questions answered and locked in §7 of the audit doc:**
  Q1 → dev shop on personal NP account, set up after NP-FIX-2 + 1
  land. Q2 → strict sender-warehouse validation, no `?force=true`
  override. Q3 → per-shop default Service Type (new
  `Shop.np_default_service_type` column). Q4 → hybrid tracking poll:
  4-hour batch + manual refresh button. Q5 → stay on v2.0; revisit
  v1.0 only on external trigger.
- **Latent regression caught during the audit:** while reading
  `scheduler.py` to confirm NP-FIX-5 could plug into the existing
  APScheduler infrastructure, surfaced **BUG-9** —
  `sync_shop_orders` return type changed by IMP-2 but the scheduler
  was still doing `count > 0` on a Pydantic model. Filed and fixed
  before NP-FIX-* work began (commit `de1112b`). See BUG-9 entry
  above.
- **Updated 2026-05-09:** §7 fixes applied to the audit doc after
  cross-referencing the live code:
  - §2.4 — softened the `ttn_printed` claim to "no automatic flow
    sets it; technically writable via generic `PATCH /orders/{id}`"
    (the field is exposed in schemas / frontend types, just not
    surfaced through any deliberate UI).
  - §3 feature inventory — corrected "Sender warehouse selection
    in shop settings" from **Partial** to **Done** (the Logistics
    (NP) tab in `pages/ShopsPage.tsx:407` does expose the
    field — the gap is at TTN-create time, not at shop-edit time).
  - §8 NP-FIX-5 description — removed the "verify scheduler exists"
    hedge after confirming `backend/scheduler.py` already runs
    `AsyncIOScheduler` periodically.

**Sprint NP-FIX-*** — defined and locked in `docs/integrations/nova-poshta-audit-2026-05.md`
§6 + §8. Execution order: NP-FIX-2 → NP-FIX-1 → (user does NP-FIX-3 dev
shop setup manually, ~20 min) → NP-FIX-4 → NP-FIX-5 → NP-FIX-6 →
NP-FIX-7. NP-FIX-8 (v1.0 migration) deferred. Each follows the standard
cycle (`task.md` → CC plan review → execute → smoke test → post-fix
notes).

---

**Sprint NP-FIX-2 — Baseline pytest coverage for NP service + router** (Status: `DONE` — commit `898fa20`)

Goal: Per the NP-DISC audit, the entire Nova Poshta integration shipped
with **zero backend tests**. NP-FIX-1 (sender-warehouse validation) and
NP-FIX-4 onwards (real-API smoke tests on the dev shop) needed a
regression net first. This sprint added that net: 20 new pytest cases
across two new files, with **zero changes to production code**.

| ID | Task | Scope | Status |
|---|---|---|---|
| NP-FIX-2-1 | New `backend/tests/test_nova_poshta.py` — 8 service tests for `NovaPoshtaClient` + `_post` (retry contract, `success: false` → `NovaPoshtaAPIError` translation, wrapper-method call shape) | backend tests | DONE |
| NP-FIX-2-2 | New `backend/tests/test_shipping_router.py` — 12 router tests across all 4 endpoints: validation branches (404/400 paths) + happy paths for TTN create + TTN delete | backend tests | DONE |

**Post-sprint notes:**
- **Q1 — Tenacity wait disabled cleanly via monkeypatch.** Test #4 in
  `test_nova_poshta.py` proves `httpx.HTTPError` triggers exactly 3
  retries while `NovaPoshtaAPIError` triggers exactly 1 attempt
  (no retry, the NP-P0 invariant). Implementation:
  `monkeypatch.setattr(NovaPoshtaClient._post.retry, "wait", wait_none())`.
  `.retry.wait` is a public tenacity attribute on the `Retrying`
  instance the decorator attaches to the function — mutating it is the
  supported runtime-override pattern, and `monkeypatch` auto-restores
  it after the test. Retry test runs in <100ms (vs. ~6s wall-clock if
  we'd accepted the real exponential backoff). If a future tenacity
  upgrade breaks `.retry.wait`, the fallback `c` from the spec — a
  6-second test — still proves the right thing.
- **Q3 — Direct-coroutine test style locked.** CC grepped
  `backend/tests/` and found that all 7 pre-existing test files call
  endpoint or service functions directly (no `TestClient`, no
  `httpx.AsyncClient` against the FastAPI app). NP-FIX-2 mirrors this
  precedent — `await create_np_ttn(order_id=..., body=...,
  current_user=mock_user, db=mock_db)`, `pytest.raises(HTTPException)
  as exc_info; assert exc_info.value.status_code == 400`. No
  `app.dependency_overrides`, no client fixture, no auth-bypass
  plumbing. Tighter and more consistent with the rest of the suite.
- **Q4 — `routers.shipping.get_order_detail` patched at the
  module-level binding.** Patching `services.order_service.get_order_detail`
  would not take effect because `routers/shipping.py:20` does
  `from services.order_service import get_order_detail` (binds at
  import time). All TTN-related tests use
  `@patch("routers.shipping.get_order_detail", AsyncMock(...))` and
  similarly for `change_order_status`, `decrypt_value`, and
  `NovaPoshtaClient`.
- **Mock helper pattern.** `_mock_async_client(json_payload, *, raises=None)`
  in `test_nova_poshta.py` returns a singleton mock honouring the
  `async with httpx.AsyncClient() as client: await client.post(...)`
  contract — `__aenter__`/`__aexit__` set up correctly so the
  service code's `async with` block yields the same `client_instance`
  on every retry. `client_instance.post.side_effect = [err, err,
  success_response]` consumes one item per retry attempt across all
  three `_post` invocations.
- **Sanity grep clean** (per task.md verification): zero
  `api.novaposhta.ua` references in `backend/tests/`; every
  `NovaPoshtaClient` / `decrypt_value` reference in
  `test_shipping_router.py` sits inside a `patch(...)` context.
- **Test count:** 77 → **97 passing** (+20 new). Suite runtime stayed
  at 1.97s — well within the +5-10s budget the task.md set as
  acceptable.
- **No production behaviour change.** This sprint is pure additive
  test coverage; the existing 77 tests stay green untouched, and
  no code under `backend/services/` or `backend/routers/` was
  modified. The next NP-FIX sprint (NP-FIX-1, sender-warehouse
  validation) lands behavioural changes that this baseline now
  protects.

---

**Sprint NP-FIX-1 — Sender-warehouse validation + passive warning banner** (Status: `DONE` — commit `193f74a`)

Goal: Close the courier-dispatch incident documented in
`docs/integrations/nova-poshta-audit-2026-05.md` §4. A TTN was created
against a shop with `np_sender_warehouse_ref = NULL`; the backend
forwarded the missing field to NP's `InternetDocument.save`, NP silently
downgraded the request to courier pickup, and a courier showed up at
the customer's address. NP-FIX-1 added strict backend rejection before
any NP API call, plus a passive amber banner on the order Logistics
panel so the operator sees the misconfig ahead of click-time, not at
click-time.

| ID | Task | Scope | Status |
|---|---|---|---|
| NP-FIX-1-1 | Backend pre-flight check in `routers/shipping.py:create_np_ttn` — `HTTPException(400)` when `shop.np_sender_city_ref` or `shop.np_sender_warehouse_ref` is null/empty | backend | DONE |
| NP-FIX-1-2 | Add `is_np_ready: bool` to `ShopResponse` schema (combined flag = `has_np_token AND np_sender_city_ref AND np_sender_warehouse_ref`) and populate it at every `ShopResponse` build site in `routers/shops.py` | backend | DONE |
| NP-FIX-1-3 | Frontend amber banner in `DetailLogistics.tsx`, rendered when `orderShop.has_np_token && !orderShop.is_np_ready`, placed inside the pre-TTN block (hidden after a TTN exists) | frontend | DONE |
| NP-FIX-1-4 | Extend `frontend/src/types/shop.ts` `ShopListItem` with `is_np_ready: boolean` | frontend | DONE |
| NP-FIX-1-5 | 3 new pytest cases in `tests/test_shipping_router.py` covering city-ref-missing, warehouse-ref-missing, and a happy-path regression with both refs populated | backend tests | DONE |

**Post-sprint notes:**
- **Q1 → combined `is_np_ready`.** The two granular fields
  (`np_sender_city_ref`, `np_sender_warehouse_ref`) move together in
  practice — the shop-edit form sets them in the same dialog tab — and
  the combined flag answers "is this shop ready to ship via NP?" 1:1.
  Implementation at `schemas/shop.py:73` (`is_np_ready: bool = False`)
  with population at the three `ShopResponse`-building sites in
  `routers/shops.py` (list, get-by-id, create/update). Frontend banner
  trivially renders on `has_np_token && !is_np_ready`.
- **Q2 → banner above Create TTN, hidden when TTN exists.** Lifecycle
  match: the misconfig only matters pre-TTN. Once a TTN exists the
  shop was either configured correctly or the bad TTN already shipped.
  Banner JSX lives inside the pre-TTN render block (`!isEditing &&
  !order.ttn_number && order.shipping_country === 'UA' &&
  canManageShipping`); no separate banner component, inline
  amber-on-zinc styling matches the existing two warnings in this
  panel (parcel-partial / no-packaging).
- **Q3 → toast surfaces backend `detail` verbatim.** No special-case
  mapping for the sender-warehouse error. The same red-error toast
  path that today surfaces every other NP-related 400 carries this
  string too. Operator sees the actionable copy
  *"Shop's Nova Poshta sender warehouse is not configured. Set it in
  Shops → Logistics (NP)."* with no extra wiring.
- **CC deviation: `frontend/src/types/shop.ts` instead of `common.ts`.**
  task.md called for `types/common.ts`, but CC discovered `Shop` type
  already lived in `types/shop.ts` (along with `ShopListItem`,
  `ShopCreate`, `ShopUpdate`) and added `is_np_ready` there to keep
  Shop-related fields colocated. Same shape, more accurate file. No
  consumer side-effects.
- **Order of checks (locked in task.md spec).** Validation block lives
  at `shipping.py:127-132`, **after** the existing recipient-field
  checks (lines 117-125) and **before** any NP API call. Operator
  can't be surprised by "configure sender warehouse" before they've
  noticed they don't even have an NP key — the existing
  `np_api_key_encrypted` check at line 109 still fires first.
- **No `?force=true` override.** Per audit-doc §7 Q2 — strict-only.
  An operator who clicks Create TTN despite the banner gets a 400; no
  bypass exists in the codebase.
- **Test count:** 97 → **100 passing** (+3 new cases). New cases:
  `test_create_ttn_returns_400_when_sender_city_ref_missing`,
  `test_create_ttn_returns_400_when_sender_warehouse_ref_missing`,
  `test_create_ttn_happy_path_with_cached_sender_refs` (regression
  guard). Each missing-ref case also asserts `NovaPoshtaClient` was
  never instantiated — proving the validation gate runs **before** any
  NP API contact.
- **Manual smoke (verified 2026-05-10).** Smoke shop = KoraKlenu
  (`c2bb2b4e-60d1-40eb-b221-4b2eabcd96fd`), `np_sender_warehouse_ref`
  temporarily nulled via `docker compose exec postgres psql` (backup
  ref `61ff74ac-3dee-11e6-a9f2-005056887b8d`, restored after).
  Confirmed: (1) amber banner visible above Create TTN button with the
  spec-mandated copy, (2) toast on click matched the backend `detail`
  verbatim, (3) `POST /api/shipping/np-ttn/{id}` returned `400`,
  (4) **zero requests to `api.novaposhta.ua`** — validation gated the
  call, (5) banner disappeared after the warehouse ref was restored.
  All five criteria green.
- **Closes:** the courier-dispatch incident root cause from
  `docs/integrations/nova-poshta-audit-2026-05.md` §4. Lamamarka
  Shopify, KoraKlenu manual, and any future NP-using shop are now
  protected from the silent-downgrade behaviour at TTN-create time.

---

**Explicitly deferred (parked, no work this round)**

Tracked here so the roadmap is exhaustive — none of these is forgotten,
none is being worked on now. Each links to its existing detail elsewhere
in this document where applicable, to avoid duplication.

| ID | Task | Why deferred (2026-05-08) |
|---|---|---|
| BUG-4 | Orders list TOTAL + Dashboard widgets read stale `order.total_price` | Pending more user interaction with the system before deciding if it's a bug or by-design |
| LINK-BACKFILL | Retroactively link historical `order_items` to catalog variants when their SKU appears in catalog | Decision blocked on observing IMP-1/IMP-2 behavior in practice |
| PC-C | Sales Analytics per Product (see Section A) | Pure feature; revisit after current round closes |
| Sprint 11 | Production & Deployment (see Section B) | System still local; prod is too early |
| PERF-1 | Route-level chunk splitting (see Section B) | No measured perf issue yet |
| TEST-1 | Vitest + Playwright smoke coverage (see Section B) | Out of current bug-hunting focus; revisit after IMP-2 |
| PC-F-1 | Product photos (see Section A) | Requires new file-upload infrastructure |
| Unlinked backfill (carried over from BUG-2/BUG-3 smoke tests) | UI gesture or migration to link historical Unlinked items in existing orders | Pre-existing constraint; no operational need yet |

---

### A. Product Catalog — Enhancement Sprints

**Sprint PC-A — Foundation: Pricing, Cost & Stock** (Status: `DONE` — commit `0bf0583`)

Goal: Add price, cost_price, and stock_quantity to ProductVariant. Update form and list view.

| ID | Task | Scope | Status |
|---|---|---|---|
| PC-A-1 | Alembic migration: add `price`, `cost_price`, `stock_quantity` to `product_variants` | backend/DB | DONE |
| PC-A-2 | Update `ProductVariant` model + Pydantic schemas (Create/Read/Update) | backend | DONE |
| PC-A-3 | Add price, cost_price, stock_quantity fields to `ProductForm.tsx` per variant | frontend | DONE |
| PC-A-4 | Update products list: add Price Range, Stock, Status badge columns | frontend | DONE |
| PC-A-5 | Update `ProductsPage.tsx`: show archived filter tab | frontend | DONE |

**Post-sprint notes:**
- Migration `d72589d_add_variant_pricing_and_stock_fields.py` added the three numeric columns to `product_variants`.
- `catalog_service.update_product` now applies **per-variant patches by id** (previously rewrote the whole list); the create path persists the new fields too.
- `ProductForm.tsx` gained a Price / Cost Price / Stock Qty row with a **live Margin % badge** (green ≥30, amber 10–29, red <10) — the threshold logic is now the source of truth for stock/margin coloring downstream.
- `ProductsPage.tsx` gained Active/Archived tabs (filter by `is_active`), Price Range, Stock (color-coded by qty), and Status columns. The archived view reuses the same query hook with a flag.

**Sprint PC-B — Product Detail Page** (Status: `DONE` — commit `f99494f`; PC-B.1 inline-edit follow-up `bf9f8ba`; PC-B.2 column picker `46783bf`)

Goal: Replace modal-only flow with a full-page product view at `/products/:id`.

| ID | Task | Scope | Status |
|---|---|---|---|
| PC-B-1 | New route `/products/:id` + `ProductDetailPage.tsx` | frontend | DONE |
| PC-B-2 | Detail page header: title, shop badge, status, Archive/Restore + Edit buttons | frontend | DONE |
| PC-B-3 | Variants table: all fields incl. price, cost, stock, volume, margin % per variant | frontend | DONE |
| PC-B-4 | Row click in `ProductsPage.tsx` navigates to detail page (replaces modal trigger) | frontend | DONE |
| PC-B-5 | Archive/Restore backend endpoint (PATCH `is_active`) if not already exposed | backend | DONE |

**Post-sprint notes:**
- Route is wrapped in `RequireAuth` only (**not `RequireRole`**) so designers with shop access can view — backend `GET /products/{id}` uses `get_current_user`, so role-gating in the frontend would have over-restricted.
- New `useProduct(id)` hook keyed on `['product', id]`. `useUpdateProduct` invocations on the detail page pass `shopId: product.shop_id` explicitly and the mutation **invalidates both `['products', shopId]` and `['product', id]`** — without the second key the detail view goes stale after Save.
- Row Edit/Delete buttons in `ProductsPage` use `e.stopPropagation()` so the row's `onClick → navigate(...)` doesn't fire alongside the inline action.
- Backend was unchanged — `PATCH /products/{id}` already supported `is_active` and per-variant patches from PC-A.
- Type aliases `ProductRead / ProductCreate / ProductUpdate / ProductVariantCreate / ProductVariantPatch` were added to `types/inventory.ts`; they had been imported by `productsApi` and `useProducts` since LOG-2 but never actually defined (compile passed because the consumers were `any`-typed).

**Sprint PC-B.1 — Shopify-style Inline Product Editing** (Status: `DONE` — commit `bf9f8ba`)

Goal: Convert `/products/:id` from a read-only view with an Edit modal into an always-editable inline form, Shopify-style. Make "Add Variant" persist end-to-end.

| ID | Task | Scope | Status |
|---|---|---|---|
| PC-B.1-1 | Convert `ProductDetailPage.tsx` to always-editable inline form (title/description as inputs, variant rows as input rows; Volume/Margin % stay computed) | frontend | DONE |
| PC-B.1-2 | Show Save Changes / Cancel only when the draft diverges from the loaded product | frontend | DONE |
| PC-B.1-3 | "Add Variant" appends a new row that persists on save — variant patches without an `id` now create new `ProductVariant` rows | backend + frontend | DONE |
| PC-B.1-4 | Trash icon on a variant row does local-only removal (DB-level deletion deferred) | frontend | DONE |
| PC-B.1-5 | Pencil icon on `ProductsPage` navigates to detail page; modal retained only for "Add Product" | frontend | DONE |

**Post-sprint notes:**
- `catalog_service.update_product` previously expected every variant patch to carry an `id`; it now treats **id-less patches as creates**, so `Add Variant` no longer requires a separate POST round-trip.
- "DB-level deletion deferred" is intentional — trash icon mutates client-side draft state only. A future sprint will need a soft-delete or hard-delete endpoint plus reconciliation against `order_items` snapshots before this can persist.
- Save/Cancel visibility is gated on a **deep diff between `draft` and the React-Query cached product**; do not switch to a shallow `dirty` boolean — variant arrays need element-by-element comparison.
- "Add Product" still uses the modal (`ProductForm`) — only edit flows moved inline.

**Sprint PC-B.2 — Column Visibility Picker** (Status: `DONE` — commit `46783bf`)

Goal: Let users toggle which columns are visible on the `ProductsPage` table, persisting the choice per browser via `localStorage`.

| ID | Task | Scope | Status |
|---|---|---|---|
| PC-B.2-1 | Add a **Columns** dropdown (right of search bar) using `DropdownMenuCheckboxItem` for Variants, SKUs, Weight Range, Price Range, Stock, Status | frontend | DONE |
| PC-B.2-2 | Persist visibility map to `localStorage` under `orderhub:productsTable:columnVisibility`, hydrated via merge-over-defaults | frontend | DONE |
| PC-B.2-3 | Wrap toggleable `<TableHead>` / `<TableCell>` in `{visibility.X && ...}`; keep Title and Actions always-on | frontend | DONE |
| PC-B.2-4 | Derive empty-state `colSpan` from live visible-column count | frontend | DONE |

**Post-sprint notes:**
- Storage key: **`orderhub:productsTable:columnVisibility`** (namespaced; reuse the `orderhub:` prefix for any future per-browser preferences).
- **Merge-over-defaults** on hydration (`{ ...DEFAULT_VISIBILITY, ...parsed }`) is the forward-compatibility hook: when a future column is added to `TOGGLEABLE_COLUMNS`, existing users' stored objects don't override its default-visible state — the new column simply appears.
- The persist `useEffect` depends on `[visibility]` only — do **not** add other deps; an unrelated dep would re-write `localStorage` on every render.
- No shared `useLocalStorage` hook was extracted (single call site). If a second consumer appears, hoist the inline `useState(() => ...)` + `useEffect` pair into `frontend/src/hooks/useLocalStorageState.ts` rather than reaching for a Zustand persist middleware — Zustand's persist middleware is currently unused in this repo (see `authStore.ts`).
- Title and Actions are intentionally **not** in `TOGGLEABLE_COLUMNS`; the visible-count formula is `2 + Object.values(visibility).filter(Boolean).length` and would need updating if either becomes toggleable.

**Sprint PC-C — Sales Analytics per Product** (Status: `NOT STARTED`)

Goal: Show order history and sales stats per product variant on the detail page.

| ID | Task | Scope | Status |
|---|---|---|---|
| PC-C-1 | Backend: extend GET `/products/{id}` response with per-variant stats (orders_count, units_sold, last_order_date) | backend | TODO |
| PC-C-2 | Frontend: Sales Analytics section on `ProductDetailPage.tsx` | frontend | TODO |
| PC-C-3 | Show: total orders, units sold, revenue, last sale date per variant | frontend | TODO |

**Future (not scheduled)**

| ID | Task | Notes |
|---|---|---|
| PC-F-1 | Product photos | Requires new file upload infrastructure per product. Deferred. |

---

### B. Production & Deployment

**Sprint 11 — Production & Deployment** (Status: `NOT STARTED`)

| ID | Task | Scope | Status |
|---|---|---|---|
| S11-1 | SSL & Domain Configuration | nginx | TODO |
| S11-2 | Database Backup Jobs | cron | TODO |
| S11-3 | Performance Monitoring | prometheus/grafana | TODO |

**Performance & Testing**

| ID | Task | Scope | Status |
|---|---|---|---|
| PERF-1 | Route-level chunk splitting | frontend bundler | TODO |
| TEST-1 | Smoke test coverage | vitest + playwright | TODO |

### B. Post-Audit Achievements

**Frontend & Architecture (Completed 2026-04-22)**

| ID | Task | Scope | Status |
|---|---|---|---|
| FE-1 | Refactor `OrderDetailPanel.tsx` | Extracted 8 sub-components to `detail/` | DONE |
| FE-2 | Modernize `CreateOrderPage.tsx` | Replaced modal with spacious full-page form | DONE |
| FE-3 | Advanced Dashboard Analytics | Shop filtering & premium telemetry widgets | DONE |
| FE-4 | Unified CRM Visuals | Modernized Customers, Users, and Imports pages | DONE |
| SEC-1 | MCP Security Guards | Added auth protection to /sse and /messages | DONE |
| INFRA-1 | Backend Logging System | Rotating logs with 25MB safety cap | DONE |

**Backend Resilience & Business Logic (Completed 2026-04-22)**

| ID | Task | Scope | Status |
|---|---|---|---|
| BE-1 | Nova Poshta Resilience | Timeouts/retries implemented | DONE |
| BE-2 | Shopify Sync Resilience | Timeouts/retries implemented | DONE |
| BE-3 | Enhanced Etsy Parser | Detailed error reporting thresholds | DONE |
| AUDIT-1 | Order Audit History | Log all status mutations | DONE |
| BUG-1 | Order Status Persistence | Fixed frontend-backend sync in OrderDetailView | DONE |
| BE-4 | Manual Shop Creation | Fixed Enum conflict in DB and backend (MANUAL) | DONE |
| FE-5 | Navigation & Dropdowns | Fixed Back button history and Status dropdown UX | DONE |
| FE-6 | Shops UI Polish | Fixed null checks and ID display in ShopsPage | DONE |

**Bug Fixes (2026-05-07)**

| ID | Task | Scope | Status |
|---|---|---|---|
| BUG-2 | Catalog search in OrderItemsEditor returned no matches (auth-bypassed fetch) | frontend | DONE — commit `46cb8d9` |
| BUG-3 | Product inventory Subtotal didn't reflect items[] (read mode used stale `order.total_price`) | frontend | DONE — commit `4f45979`, housekeeping `d4c3ab4` |

**Post-fix notes (BUG-2):**
- `frontend/src/components/orders/ProductVariantSelector.tsx` was calling raw
  `axios.get(...)` directly (its own `import axios from 'axios'`), bypassing the
  shared `frontend/src/api/client.ts` and its Bearer-token request interceptor.
  Every catalog fetch returned **403** and the silent `catch → console.error`
  made the failure look identical to a genuinely empty catalog
  ("No matches found. Using manual entry."). The bug had been latent since
  `ProductVariantSelector` was introduced in LOG-3.
- Fix replaces the local `useState<Product[]>` + fetch effect with the existing
  `useProducts(shopId)` hook (React Query) from `frontend/src/hooks/useProducts.ts`.
  Two structural side-effects worth knowing:
  1. The cache key on `shopId` removes the brittle `products.length === 0` gate
     that would otherwise leak a stale list across shops.
  2. `DetailItems.tsx` mounts **two** selector instances (existing edited rows +
     new rows) — they now share one fetch via React Query dedupe instead of two
     parallel calls.
- Local `Variant.price` widened to `number | string | null` to match the actual
  `ProductRead` shape (backend serialises `Decimal` as a string like `"130.00"`).
  `handleSelect` does a safe `Number(price)` coercion before invoking `onChange`,
  so the parent's numeric `unit_price` input never receives a string. **Smoke
  test confirmed**: selecting a variant populates `130` (numeric), Subtotal
  recomputes correctly inside the editor, no `NaN`, no `"$130.00"` string leak.
- Distinct error branch added to the dropdown ("Failed to load catalog — try
  again", rose tone) — fetch failures no longer masquerade as empty results.
- **Bonus discovered during smoke test:** catalog linking now feeds the
  `parcel-estimate` service correctly. Adding a linked variant immediately
  populates Weight/Volume in Shipping & Logistics from the variant's
  `weight_g` / `length_mm` / `width_mm` / `height_mm`. No code change in the
  parcel service — the data path was simply being correctly fed for the
  first time. The "N item(s) have no dimensions linked" warning from LOG-4
  remains accurate: it now refers only to historically unlinked items.

**Post-fix notes (BUG-3):**
- Read-mode Subtotal cell at `frontend/src/components/orders/detail/DetailItems.tsx:271`
  was bound to `order.total_price` — a backend snapshot field that is not
  recomputed when items are mutated. Edit-mode in the same file already inlined
  `items.reduce((acc, it) => acc + it.quantity * it.unit_price, 0)`; the two
  branches diverged. Fix converges read-mode on the same expression — one-line
  change, no helper extraction (CLAUDE.md "three similar lines beats premature
  abstraction"; we have only two call sites in one file).
- No `Number()` coercion added — line 260 already calls `item.unit_price.toFixed(2)`
  directly on the same data path, proving runtime type is already number. Adding
  coercion only at the new site would diverge from edit-mode and the per-row render.
- `?? 0` guard for missing `order.items` matches existing patterns at lines 218
  and 281.
- **Backend `order.total_price` field intentionally NOT modified** — the snapshot
  still drives the Orders list TOTAL column and Dashboard NET PROFIT / revenue
  widgets, all of which read aggregated values via a separate code path. Fixing
  those would be a separate decision (recompute server-side on item mutation,
  affecting audit and migrations) — out of scope for this UI fix.
- Smoke test confirmed: 130.00 → 240.00 after adding Black variant; Orders list
  TOTAL unchanged (0 UAH); Dashboard widgets unchanged.

**Pre-task housekeeping (commit `d4c3ab4`):** `docs(plan): close BUG-2, queue BUG-3` —
landed before the code commit so git history reads as discrete docs vs. fix changes.

**Known limitation, no task (carried over from BUG-2 smoke test):**
- Items saved before the catalog existed (or
  before BUG-2 was fixed) carry `product_variant_id = null` permanently —
  there is no backfill path or UI gesture to retroactively link them. They
  display the orange "Unlinked" badge forever and contribute nothing to
  parcel-estimate. This is a pre-existing constraint from LOG-1…6, **not**
  introduced by BUG-2; the fix simply makes the contrast visible (linked and
  unlinked rows now sit side-by-side in the same order). Revisit only if a
  concrete operational need surfaces (e.g. bulk-link migration for ≥N
  historical orders) — at that point it becomes a UX/migration design
  decision, not a technical debt item.

**Bug Fixes (2026-05-08)**

| ID | Task | Scope | Status |
|---|---|---|---|
| CAT-VIS-1 | Expose Etsy/Shopify shop catalogs in Products UI (read/edit-only) | backend + frontend | DONE — commit `a5d713d` |
| BUG-6 | `ProductVariantRead` 500s on zero-dimension rows; split `gt=0` validators Create-only | backend | DONE — commit `71c75b2` |
| BUG-7 | Frontend blocked edit of zero-dimension variants; switched to diff-based variant patch | frontend | DONE — commit `0ef1f6d` |

**Post-fix notes (CAT-VIS-1):**
- `backend/routers/products.py` line 25 swapped
  `require_platform(MANUAL)` → `get_shop_for_user` on the LIST endpoint
  only. POST + bulk-CSV preview/confirm endpoints retain the MANUAL gate
  (verified: 4 routes share the gate at lines 25/37/103/139; only the
  GET list relaxed). Decision rationale documented as Option B in
  `task.md` at planning time.
- `frontend/src/components/inventory/ShopSelector.tsx` gained a
  `manualOnly?: boolean` prop, defaulting to `true` so existing call
  sites (`PackagingPage.tsx:58-61`) keep manual-only behaviour without
  edits. `ProductsPage.tsx` opts out via `manualOnly={false}`.
- `frontend/src/pages/ProductsPage.tsx` derives `isManual` via a new
  `useMemo` against the loaded shops list, then **hides** Add Product /
  Bulk Import buttons when active shop is non-MANUAL (preferred over
  disabling — fewer noise, the user already understands platform-driven
  imports from the Imports tab). Header copy and empty-state copy moved
  from MANUAL-specific to platform-neutral
  ("Manage product catalog and physical specifications.").
- 6 new pytest cases (`tests/test_products_platform_gate.py`):
  list endpoint accepts etsy/shopify/manual; `require_platform("manual")`
  still blocks etsy/shopify and allows manual.
- Smoke test confirmed: dropdown lists all four shops; KoraKlenu shows
  buttons + manual catalog; LeatherCraft UA shows IMP-1 catalog with
  buttons hidden (after BUG-6 unblocked the Read serialization);
  MyShopify Store shows empty state cleanly; `/packaging` unchanged.

**Post-fix notes (BUG-6):**
- After CAT-VIS-1 opened the read path, `GET /api/shops/{etsy_shop_id}/products`
  returned **500** for any shop with IMP-1-imported variants.
  `ProductVariantBase` (`backend/schemas/product.py:12-15`) declared
  `weight_g/length_mm/width_mm/height_mm` with `gt=0`, and
  `ProductVariantRead` inherited from it (line 40). FastAPI's response-
  model serialization re-validated those fields on every read and raised
  `ValidationError` against IMP-1's deliberate `0` sentinel. KoraKlenu
  (manual, real dimensions) returned 200 fine; only IMP-1-touched shops
  surfaced the bug.
- Fix: relaxed `ProductVariantBase` to `ge=0` on the four dimension
  fields; re-tightened to `gt=0` only on `ProductVariantCreate` by
  overriding those fields. `ProductVariantRead` inherits the relaxed
  Base and serializes zero-dimension rows cleanly. `ProductVariantUpdate`
  was deliberately **not** relaxed — its `gt=0` is correct and is
  separately addressed by BUG-7's diff semantics on the frontend (so a
  PATCH never sends an explicit `0` for an unchanged field).
- 10 new pytest cases (`tests/test_product_variant_schema.py`): Read
  accepts zero dimensions (regression guard), Create accepts positive +
  rejects zero per-field (parametrized), Update rejects zero per-field
  (parametrized — guards against future drift on the strict Update path).
- Smoke confirmed: LeatherCraft UA catalog renders 7 products / 11
  variants with `0g` weights visible (post BUG-7, the user can edit them
  in place); KoraKlenu unchanged.

**Post-fix notes (BUG-7):**
- BUG-6 unblocked the Read path but the Write path was still broken:
  `frontend/src/pages/ProductDetailPage.tsx`'s `handleSave` (lines
  196-204 client guard) demanded all four dimensions `> 0` on **every**
  variant in the draft, regardless of whether the user touched them.
  The patch builder (lines 219-233) also serialized every field
  verbatim — even with the client guard relaxed, the backend's
  `ProductVariantUpdate.gt=0` would 422 on untouched zero-dimension
  fields.
- Fix: extracted module-level `diffVariant(draft, original)` helper
  that compares per-field with mode-aware semantics:
  - **Numeric** (weight/dims/stock) — coerce draft to `Number(...)`,
    compare via `===`. NaN → omitted from patch.
  - **Decimal-string** (price/cost_price) — normalize both sides via
    `Number(...)` so `'130.00' === '130'` reads as no change. Empty
    draft + non-null original → emit `field: null` (clear-to-null).
  - **String-or-null** (sku/variant_name) — normalize empty string
    ↔ null to a single canonical "empty"; emit `null` when the user
    cleared a previously-populated field.
  Returns either a partial `ProductVariantPatch` of changed fields
  (always including `id`) or `null` if nothing changed (caller skips
  the variant entirely → free win on no-op patches).
- `handleSave` now validates **only** the fields present in the diff
  for existing variants. New variants (no `id`) keep today's full-payload
  + strict validation, extracted into a sibling `validateNewVariant`
  helper. Toast wording unchanged.
- 9 new vitest cases (`__tests__/ProductDetailPage.diffVariant.test.ts`):
  zero-sentinel guard (the BUG-7 regression), weight 0 → 120 isolation,
  cost_price clear-to-null, Decimal `'130.00' === '130'` normalization
  (KoraKlenu regression guard), sku empty↔null normalization,
  KoraKlenu price-only diff, plus `validateNewVariant` accept/reject
  cases.
- Smoke test confirmed all 5 task.md verification steps:
  weight 0→120 saves with dims staying 0, weight→0 rejects, new
  variant with 0 dims rejects, cost_price clear→null persists,
  KoraKlenu Brown price 130→135 doesn't touch Black variant.

**End-of-day rollup (2026-05-08):**
The catalog read+edit path is now end-to-end functional for Etsy/Shopify
auto-imported rows. The user can finally see what IMP-1 imported and
fill in physical dimensions / cost prices one at a time. The **only
remaining data-correctness issue from this batch** is **BUG-5**
(blank-SKU dedup-by-Variations) — visible right now as listing
4343151753 ("Personalized Spidey ID Card Holder") having 5 catalog
variants where it should have 2 ("Single Bat ID" × 3 rows + "Bat ID
with Gift Box" × 2 rows in the source CSV, all with empty SKU,
collapsed today by per-row counter instead of per-Variations key).
Wipe-and-reimport of LeatherCraft UA is queued right after BUG-5 lands.

### C. Nova Poshta Full Audit Fixes (Completed 2026-04-23)

Comprehensive overhaul based on the [NP Audit Report](file:///home/serhii/projects/OrderHub/agents/skills/np-audit/SKILL.md).

| ID | Category | Task | Status |
|---|---|---|---|
| NP-P0 | Backend | Implementation of basic stability (timeouts, retries) | DONE |
| NP-P1 | Backend | NovaPoshtaAPIError, COD support, sender caching, timezone fix | DONE |
| NP-P2 | Frontend | Debouncing, dropdown positioning, click-to-copy | DONE |
| NP-P3 | Cleanup | Encryption decoupling (ENCRYPTION_KEY), dead code removal, delete TTN | DONE |

**Key Outcomes:**
- **Zero Redundant Calls**: Sender references are cached in the DB.
- **Data Integrity**: Refs are auto-cleared on manual input; dates are Kiev-compliant.
- **Security**: All API keys are Fernet-encrypted and masked in the UI.

### D. Logistics Automation & Product Catalog Foundation (Phases 1-6)

Implementation of automated parcel estimation and a robust Product Catalog which serves as the foundation for future Warehouse Management.
See [Nova Poshta Details](docs/integrations/nova-poshta.md) and [Product Catalog Foundation](docs/inventory/product-catalog.md).

| ID | Phase | Milestone | Status |
|---|---|---|---|
| LOG-1 | Phase 1 | Database Schema (Products, Variants, Packaging) | DONE |
| LOG-2 | Phase 2 | Backend API (CRUD, Two-step CSV Import Preview/Confirm) | DONE |
| LOG-3 | Phase 3 | Order Item Linking & Snapshots (Atomic SKU matching) | DONE |
| LOG-4 | Phase 4 | Parcel Calculation Service (Packaging selection & Vol. Weight) | DONE |
| LOG-5 | Phase 5 | Frontend Logistics Panel (Calculated pre-fills & Badges) | DONE |
| LOG-6 | Phase 6 | Catalog & Packaging Administration UI (Products/Packaging Admin) | DONE |

**Key Outcomes:**
- **Inventory Foundation**: Established a source-of-truth for products and variants, prepared for full Warehouse management.
- **Automated Logistics**: Parcel dimensions and weights are pre-filled based on the product catalog.
- **Data Safety**: Atomic snapshots preserve historical order data even if catalog specs change.
- **Administrative Control**: Full UI for managing physical specs and safe bulk CSV importing.

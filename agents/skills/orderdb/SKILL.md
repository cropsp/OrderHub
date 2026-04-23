---
name: orderdb
description: Implementation plan for the product catalog feature and Nova Poshta parcel-dimension calculation in the multi-shop CRM. Use this skill when executing any phase of the product catalog rollout, when reviewing PRs related to `products`, `product_variants`, `packaging_boxes`, or when adding logic that depends on OrderItem physical dimensions. Contains sprint-ready phases with priority labels (P0/P1/P2), acceptance criteria, and a progress log.
---

# orderdb — Product Catalog & NP Parcel Calculation

## How to use this skill

This plan is designed to be executed in **short sprints**, one phase at a time, with explicit Plan mode approval before any code changes. A typical sprint prompt looks like:

```
Read .agents/skills/orderdb/SKILL.md. Enter Plan mode.
Implement Phase <N> only (scope = P<priority>).
Generate a plan artifact before making any changes.
Do not touch items marked "Out of Scope" or any other phase.
```

After a sprint lands:
1. Update the **Progress Log** at the bottom of this file.
2. Check off the phase's acceptance items inline.
3. Do not start the next phase without explicit approval.

---

## 1. Context

The CRM manages orders across three shop types. Each has a distinct inbound flow:

| Shop type  | Order source        | Product source        | NP integration required |
| ---------- | ------------------- | --------------------- | ----------------------- |
| `ETSY`     | CSV import          | (future iteration)    | no                      |
| `SHOPIFY`  | API sync            | (future iteration)    | no                      |
| `MANUAL`   | created in CRM      | created in CRM        | **yes, UA region only** |

**Business driver for this iteration:** when generating a Nova Poshta TTN for a `MANUAL`-shop order whose region is `UA`, parcel weight and dimensions must be derived automatically from the items in the order, rather than from static shop-wide defaults. A product catalog is a prerequisite for that derivation. No catalog exists today; it is being built from scratch with future Etsy/Shopify compatibility in mind.

**Stack reminder:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 (prod) / SQLite (dev)
- Frontend: React 19, TypeScript, Vite, Vanilla CSS
- Infra: Docker, Docker Compose
- Existing: `ShopPlatform` enum already exists in `backend/models/shop.py` (values: `ETSY`, `SHOPIFY`, `MANUAL`). Use as-is.
- Existing: `NovaPoshtaClient` already exists in `backend/services/nova_poshta.py`. Do not modify its internal structure.

---

## 2. Out of Scope (do NOT implement in this iteration)

- Automatic product pull from Etsy
- Shopify Admin API product sync
- Inventory / stock level tracking (quantity on hand)
- Product categories, tags, collections
- Volumetric weight logic for non-MANUAL shops
- Retroactive parcel recalculation for already-shipped orders
- Multi-parcel splitting (assume one order → one parcel for now)

---

## 3. DO NOT (behavioral guardrails for the agent)

- Do **not** alter the existing `shops`, `orders`, or NP-integration modules beyond adding columns. Existing behavior for ETSY/SHOPIFY order flows must remain untouched.
- Do **not** make schema changes without a matching Alembic migration verified on both PostgreSQL and SQLite.
- Do **not** hardcode unit conversions outside the service/serializer layer. Base units in the DB are **grams** and **millimeters**.
- Do **not** seed any default packaging data in migrations. The box/envelope catalog is populated by the user via CRUD/CSV only.
- Do **not** introduce new third-party libraries without calling them out in the plan artifact first.
- Do **not** skip the Plan-mode artifact step, even for phases that look trivial.

---

## 4. Key architectural decisions (locked in)

### 4.1 Two-level model: `Product` + `ProductVariant`
Even MANUAL shops use the two-level structure. Single-variant products automatically get one default variant. This avoids a painful migration when Etsy/Shopify variants are added later.

### 4.2 Snapshot pattern on `OrderItem`
Physical characteristics are **copied** from `ProductVariant` to `OrderItem` at the time the item is added to the order. Later edits to the variant do not affect historical orders. This is non-negotiable — without snapshots, editing a product weight rewrites every past TTN's basis.

### 4.3 Base units are integers
- Weight: `INTEGER` grams (`weight_g`)
- Dimensions: `INTEGER` millimeters (`length_mm`, `width_mm`, `height_mm`)
- Volume: **not stored**, computed via SQLAlchemy `hybrid_property`

UI converts to kg / cm at the serializer layer only.

### 4.4 Per-shop scoping
All new tables carry `shop_id FK`. API endpoints derive `shop_id` from the authenticated context and validate ownership on every read/write (IDOR guard).

### 4.5 Two packaging types: BOX and ENVELOPE
The shop owns a catalog of packaging options with two distinct types and different selection logic:

**BOX** — rigid container. Selection checks:
- `inner_volume_cm3 >= total_items_volume_cm3 * packing_factor`
- `max_weight_g >= total_items_weight_g`

**ENVELOPE** — soft/flexible mailer, no meaningful height constraint. Selection checks:
- `max_weight_g >= total_items_weight_g`
- If `max_thickness_mm` is set: `sum(item.height_mm * qty) <= max_thickness_mm`
- If `max_thickness_mm` is NULL: weight check only

**Selection order:** envelopes evaluated before boxes (cheaper shipping). Within each group: smallest first. First match wins.

### 4.6 No seed data for packaging
The merchant has dozens of custom boxes and envelopes. Migrations create the table structure only. The parcel calculator handles the empty-catalog case gracefully with a distinct warning.

### 4.7 PackagingBox CRUD is in Phase 2
The parcel calculator (Phase 4) depends on packaging data being present. CRUD for `PackagingBox` is delivered in Phase 2 alongside Product CRUD so the user can populate the catalog before Phase 4 runs.

### 4.8 Separate service: `parcel_calculator.py`
`NovaPoshtaClient` owns NP API communication only. `parcel_calculator.py` owns business logic: envelope vs box selection, packing factor, volumetric weight, warnings. It returns `ParcelEstimate`. The NP panel reads the estimate and passes `chargeable_weight_g` to `NovaPoshtaClient`.

### 4.9 Volumetric weight for NP
NP bills `max(actual_weight_kg, L_cm × W_cm × H_cm / 4000)`. The service computes `chargeable_weight_g = max(total_weight_g, volumetric_weight_g)` and this value is what gets sent to the NP API.

---

## 5. Database schema

### 5.1 `products` (new)
```
id                UUID PK
shop_id           UUID FK → shops.id ON DELETE CASCADE
title             VARCHAR(500) NOT NULL
description       TEXT NULL
external_ref      VARCHAR(255) NULL     -- reserved for etsy_listing_id / shopify_product_id
is_active         BOOLEAN NOT NULL DEFAULT TRUE
archived_at       TIMESTAMP NULL
created_at        TIMESTAMP NOT NULL
updated_at        TIMESTAMP NOT NULL

UNIQUE (shop_id, external_ref) WHERE external_ref IS NOT NULL
INDEX (shop_id, is_active)
```

### 5.2 `product_variants` (new)
```
id                UUID PK
product_id        UUID FK → products.id ON DELETE CASCADE
sku               VARCHAR(100) NULL
variant_name      VARCHAR(255) NULL
attributes        JSONB NULL                    -- e.g. {"size":"M","color":"brown"}
external_ref      VARCHAR(255) NULL             -- reserved for etsy_product_id / shopify_variant_id
weight_g          INTEGER NOT NULL CHECK (weight_g > 0)
length_mm         INTEGER NOT NULL CHECK (length_mm > 0)
width_mm          INTEGER NOT NULL CHECK (width_mm > 0)
height_mm         INTEGER NOT NULL CHECK (height_mm > 0)
is_active         BOOLEAN NOT NULL DEFAULT TRUE
created_at        TIMESTAMP NOT NULL
updated_at        TIMESTAMP NOT NULL

UNIQUE (product_id, sku) WHERE sku IS NOT NULL
INDEX (product_id)
```
`hybrid_property volume_cm3` returns `length_mm * width_mm * height_mm / 1_000_000` (result in cm³).

SKU uniqueness across a shop is enforced at the API layer via a JOIN on `products.shop_id`.

### 5.3 `packaging_boxes` (new)
```
id                  UUID PK
shop_id             UUID FK → shops.id ON DELETE CASCADE
name                VARCHAR(100) NOT NULL
packaging_type      ENUM('BOX', 'ENVELOPE') NOT NULL DEFAULT 'BOX'
inner_length_mm     INTEGER NOT NULL
inner_width_mm      INTEGER NOT NULL
inner_height_mm     INTEGER NOT NULL
max_thickness_mm    INTEGER NULL         -- ENVELOPE only: max sum of item heights; NULL = weight-only check
max_weight_g        INTEGER NOT NULL
tare_weight_g       INTEGER NOT NULL DEFAULT 0
sort_order          INTEGER NOT NULL DEFAULT 0
created_at          TIMESTAMP NOT NULL
updated_at          TIMESTAMP NOT NULL

INDEX (shop_id, packaging_type, sort_order)
```
**No seed data.** Table is empty after migration.

### 5.4 `order_items` (alter)
Add columns (all nullable — existing rows untouched):
```
product_variant_id     UUID FK → product_variants.id ON DELETE SET NULL
snapshot_weight_g      INTEGER NULL
snapshot_length_mm     INTEGER NULL
snapshot_width_mm      INTEGER NULL
snapshot_height_mm     INTEGER NULL
snapshot_title         VARCHAR(500) NULL
```

### 5.5 `orders` (alter)
Add columns:
```
computed_parcel_weight_g        INTEGER NULL
computed_parcel_length_mm       INTEGER NULL
computed_parcel_width_mm        INTEGER NULL
computed_parcel_height_mm       INTEGER NULL
computed_packaging_box_id       UUID FK → packaging_boxes.id ON DELETE SET NULL
parcel_override                 BOOLEAN NOT NULL DEFAULT FALSE
```

---

## 6. Phases

Execute sequentially. Do not start phase N+1 before phase N is merged and accepted by a human.

---

### Phase 1 — Schema & models `[P0]`
**Goal:** All new tables and columns exist; models defined; migration reversible on both databases. No data seeded.

- [ ] SQLAlchemy models: `Product`, `ProductVariant`, `PackagingBox` in `app/models/`
- [ ] `PackagingType` Python enum: `BOX | ENVELOPE`
- [ ] `hybrid_property volume_cm3` on `ProductVariant`
- [ ] Relationships: `Shop.products`, `Shop.packaging_boxes`, `Product.variants`, `ProductVariant.order_items`
- [ ] Alter `OrderItem`: FK + snapshot fields (all nullable)
- [ ] Alter `Order`: `computed_parcel_*` + `parcel_override`
- [ ] Single Alembic revision with all constraints and indexes; **zero seed data**
- [ ] Verify `alembic upgrade head` and `alembic downgrade -1 && alembic upgrade head` on PostgreSQL and SQLite

Acceptance:
- [ ] Migrations run clean on fresh DB and existing dev DB
- [ ] `packaging_boxes` is empty after migration
- [ ] Existing `order_items` rows unmodified; new columns are NULL
- [ ] `pytest` existing suite passes, zero regressions

---

### Phase 2 — Product & PackagingBox API (MANUAL only) `[P0]`
**Goal:** Full CRUD for products, variants, and packaging (boxes + envelopes). All endpoints gated to `ShopPlatform.MANUAL`.

#### Product endpoints
- [ ] Schemas: `ProductCreate`, `ProductRead`, `ProductUpdate`, `ProductVariantCreate`, `ProductVariantRead`
- [ ] `GET    /api/shops/{shop_id}/products` — paginated, filter `is_active`
- [ ] `POST   /api/shops/{shop_id}/products` — product + one or more variants in one request
- [ ] `GET    /api/products/{id}` — detail with variants
- [ ] `PATCH  /api/products/{id}` — upsert-style variant update
- [ ] `DELETE /api/products/{id}` — soft delete
- [ ] `POST   /api/shops/{shop_id}/products/bulk-csv` — required columns: `title, sku, weight_g, length_mm, width_mm, height_mm`

#### PackagingBox endpoints
- [ ] Schemas: `PackagingBoxCreate`, `PackagingBoxRead`, `PackagingBoxUpdate`
- [ ] `GET    /api/shops/{shop_id}/packaging-boxes` — ordered by `packaging_type, sort_order`
- [ ] `POST   /api/shops/{shop_id}/packaging-boxes`
- [ ] `PATCH  /api/packaging-boxes/{id}`
- [ ] `DELETE /api/packaging-boxes/{id}` — hard delete
- [ ] `POST   /api/shops/{shop_id}/packaging-boxes/bulk-csv` — required: `name, packaging_type, inner_length_mm, inner_width_mm, inner_height_mm, max_weight_g`; optional: `tare_weight_g, max_thickness_mm, sort_order`

#### Guards (all endpoints)
- [ ] `shop.shop_platform != MANUAL` → HTTP 403: `"Catalog for this shop type is managed automatically"`
- [ ] Variant SKU uniqueness within shop (service-layer query check)
- [ ] Authenticated user has access to the shop

Acceptance:
- [ ] pytest: product with 2 variants → read → update weight → soft-delete
- [ ] pytest: create BOX and ENVELOPE entries → list → update → delete
- [ ] pytest: ETSY/SHOPIFY shop → 403 on all endpoints
- [ ] pytest: duplicate SKU in same shop → 400
- [ ] pytest: CSV import with `packaging_type=ENVELOPE` and `max_thickness_mm` → parsed correctly

---

### Phase 3 — OrderItem linking & snapshot `[P0]`
**Goal:** Adding an item to a MANUAL order auto-populates immutable snapshot fields from the selected variant.

- [ ] Order-item create/update (MANUAL path): accept `product_variant_id`, copy snapshot fields atomically
- [ ] Reject `product_variant_id` from a different shop → 400
- [ ] `OrderItemRead` returns snapshot fields alongside FK
- [ ] Frontend: type-ahead variant selector (search by title/SKU, scoped to order's shop)
- [ ] Frontend: inline badge on items without `product_variant_id`: "⚠️ dimensions not linked"

Acceptance:
- [ ] pytest: add item with variant → snapshot matches variant at that moment
- [ ] pytest: update variant weight → OrderItem snapshot unchanged
- [ ] pytest: soft-delete variant → OrderItem still readable (SET NULL)
- [ ] Manual smoke: variant selector returns correct results

---

### Phase 4 — Parcel calculation service `[P0]`
**Goal:** Single service call returns packaging selection and all values needed for the NP TTN form.

- [ ] `app/services/parcel_calculator.py`:
  ```python
  class ParcelEstimate(BaseModel):
      total_weight_g: int               # items + tare
      total_volume_cm3: int             # raw sum, no packing factor
      selected_packaging: PackagingBoxRead | None
      packaging_type: Literal["BOX", "ENVELOPE"] | None
      parcel_length_mm: int
      parcel_width_mm: int
      parcel_height_mm: int
      volumetric_weight_g: int          # (L_cm * W_cm * H_cm) / 4  [grams]
      chargeable_weight_g: int          # max(total_weight_g, volumetric_weight_g)
      unlinked_items_count: int
      warnings: list[str]
  ```
- [ ] Selection algorithm:
  1. Collect items with snapshots; count `unlinked_items_count` for those without
  2. `unlinked_items_count > 0` → warning: `"N item(s) have no dimensions linked — calculation is partial"`
  3. Compute totals from snapshots only
  4. **Envelopes first** (sorted by `sort_order`): weight fits AND thickness fits (or no `max_thickness_mm`)
  5. **Boxes fallback** (sorted by smallest inner volume): volume × 1.25 fits AND weight fits
  6. No match → warning: `"Order does not fit any available packaging"`
  7. No packaging rows for shop → warning: `"No packaging configured for this shop — add boxes or envelopes in Inventory → Packaging"`
  8. Add `tare_weight_g` of selected packaging to `total_weight_g`
- [ ] Cache result into `orders.computed_parcel_*` when `parcel_override = False`
- [ ] `GET /api/orders/{order_id}/parcel-estimate`

Acceptance:
- [ ] Unit test: fits in envelope (weight + thickness) → envelope selected, not box
- [ ] Unit test: too thick for envelope → falls through to box
- [ ] Unit test: fits nowhere → `selected_packaging=None` + correct warning
- [ ] Unit test: shop has no packaging → "No packaging configured" warning
- [ ] Unit test: partial unlinked items → warning present, partial calculation proceeds
- [ ] Integration test: endpoint returns 200, populates `computed_parcel_*` in DB

---

### Phase 5 — NP TTN integration update `[P0]`
**Goal:** The NP panel uses calculated values, surfaces packaging context, and sends `chargeable_weight` to NP.

- [ ] On panel open: call `/api/orders/{id}/parcel-estimate`
- [ ] Pre-fill `weight`, `length`, `width`, `height` from estimate
- [ ] Badge: `Calculated from N items · <name> (BOX|ENVELOPE)` with tooltip: actual / volumetric / chargeable weight
- [ ] Each `warnings[]` entry rendered as separate inline alert (yellow for partial, red for no packaging / unlinked items)
- [ ] Red alert for `unlinked_items_count > 0`: link to catalog
- [ ] Red alert for "No packaging configured": link to packaging page
- [ ] Manual edit of any field → `parcel_override = true` on save
- [ ] "↻ Recalculate" button → clears override, re-fetches, re-fills
- [ ] TTN submit: pass `chargeable_weight_g` (converted to kg) to `NovaPoshtaClient`
- [ ] Regression: non-UA orders still cannot reach TTN generator

Acceptance:
- [ ] Manual: 2 linked items → inputs pre-filled, badge shows packaging name + type
- [ ] Manual: envelope selected → badge shows `ENVELOPE`
- [ ] Manual: edit weight → save → reopen → value persists + override indicator
- [ ] Manual: "↻ Recalculate" → calculated values restored
- [ ] Manual: no packaging configured → red alert with link

---

### Phase 6 — Catalog & Packaging UI `[P1]`
**Goal:** Polished admin pages for products and packaging management.

- [ ] New route `/products` under sidebar "Inventory"
- [ ] New route `/packaging` under sidebar "Inventory"
- [ ] Both pages: shop dropdown showing MANUAL shops only
- [ ] **Products page:** table (Title | Variants | SKUs | Weight range | Status), inline variant form, live `volume_cm3`, CSV import modal with 5-row preview
- [ ] **Packaging page:** table (Name | Type | Dimensions | Max weight | Tare), `packaging_type` toggle in form, `max_thickness_mm` field shown only for ENVELOPE, CSV import modal with 5-row preview
- [ ] Sidebar: **Inventory → Products**, **Inventory → Packaging**

Acceptance:
- [ ] Manual: create 3 boxes + 2 envelopes; edit one; delete one
- [ ] Manual: CSV import with mixed BOX/ENVELOPE rows → all correct
- [ ] Manual: ETSY/SHOPIFY shops absent from dropdown
- [ ] Manual: live volume updates as dimensions are typed

---

## 7. Testing strategy

Required before any merge:

1. **Scope isolation** — product/box in shop A not accessible from shop B context
2. **Snapshot immutability** — variant edit never mutates existing OrderItem snapshots
3. **Parcel calculation** — all six scenarios: envelope fits / too thick → box / fits nowhere / no packaging / partial unlinked / fully unlinked
4. **Shop-type guard** — all new endpoints return 403 for ETSY and SHOPIFY shops
5. **Migration roundtrip** — `upgrade → downgrade → upgrade` on PostgreSQL and SQLite; `packaging_boxes` empty after
6. **NP regression** — non-UA orders still blocked from TTN generator

---

## 8. Open questions (all resolved)

1. ✅ `ShopPlatform` enum exists in `backend/models/shop.py`. Use as-is.
2. ✅ No default packaging seeded. User populates catalog via CRUD/CSV.
3. ✅ Packing factor: `1.25`.
4. ✅ No `price` on `ProductVariant` in this iteration.
5. ✅ Separate `parcel_calculator.py`. `NovaPoshtaClient` stays focused on NP API only.

---

## 9. Progress log

Agent appends one entry per sprint after merge:

```
### 2026-04-23 — Phase 3 — OrderItem linking & snapshot
- Commit: f6f7970
- Summary: Implemented variant linking with atomic snapshot population and cross-shop security guards.
- Acceptance checked by: self, pending review
- Deviations from plan: none
- Follow-ups: none

### 2026-04-23 — Phase 4 — Parcel calculation service
- Commit: 4e18a63
- Summary: Implemented `parcel_calculator` service with envelope/box selection logic and volumetric weight calculation. Added `GET /parcel-estimate` endpoint with caching.
- Acceptance checked by: self
- Deviations from plan: Fixed volume math in `ProductVariant` (from /1M to /1k for cm3).
- Follow-ups: none

### 2026-04-23 — Phase 5 — NP TTN integration update
- Commit: pending
- Summary: Integrated automated parcel calculation into Nova Poshta TTN panel. Added pre-filling, packaging badges, volumetric weight tooltips, and manual override tracking.
- Acceptance checked by: self
- Deviations from plan: Corrected VolumeGeneral divisor for mm3 to m3 conversion.
- Follow-ups: none
```

_(empty — first entry goes here after Phase 1 lands)_
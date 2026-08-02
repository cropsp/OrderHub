# Materials Warehouse + BOM — Design Document

**Status:** Draft 1.1 — 2026-05-14
**Phase:** Finance epic, Phase 3 (after FIN-1, before Partners which is parked)
**Authors:** Sergii (operator) + Cowork (planning)
**Review state:** Post-review-round-1. All major design questions resolved. **Not yet broken into sprints; no code touched.**

**Changelog:**
- **v1.1 (2026-05-14):** Incorporated review-round-1 feedback. Added `currency` on Material/Receipt entities (v1 expects UAH only). Added `shop_id` (nullable) on `OverheadMaterialReceipt` for optional per-shop tagging. Unified initial-stock flow with regular receipts (single code path). Soft-delete via `is_active=False` clarified (no physical delete, no cascade). Dropped `Material.color` (redundant with name) and `Order.production_cost_source` ENUM (deriveable from NULL checks). Tightened `BomItem.qty_per_unit` precision to `Decimal(8,2)`. Added §10 Known Limitations.
- **v1.0 (2026-05-14):** Initial draft from discovery conversation.

---

## 1. Context

OrderHub Phase 1 of the Finance epic (FIN-1, commit `b4fca1c`) shipped a per-shop financial overview that computes Net Profit from existing `Order.*` fields:

```
Net Profit = SUM(total_price) − SUM(production_cost) − SUM(platform_fee + shipping_np_cost)
```

The page works, but during FIN-1 smoke it surfaced an obvious data-quality gap: **most orders have `production_cost = NULL` or `0`** (the FIN-1 diagnostic badge fires regularly: *"2 of 2 orders without cost — Net Profit may be inflated"*). When `production_cost` is missing, Net Profit reads as the entire Revenue minus fees — a useless number for operational decisions or partner payout math.

Why is `production_cost` missing? Because today **the operator enters it manually**, computing it offline from Excel tables that:

- Multiply leather/plywood area by purchase price per unit;
- Don't include transportation/shipping cost on raw material purchases;
- Treat threads, glue, and other consumables as untracked "general overhead";
- Use no cost method at all (FIFO/LIFO/Weighted Average) — just whatever the most recent invoice said;
- Skip waste/breakage in calculations.

This is a real-world workshop accounting setup, not a bug. But it doesn't scale: as soon as multiple shops, multiple suppliers with different prices over time, and partner payout calculations enter the picture (Phase 2 of the Finance epic, parked), the manual approach becomes a constant source of arithmetic anxiety.

**Phase 3 fixes this at the root:**

1. Catalog the raw materials the workshop actually uses (Direct: leather, plywood, straps, locks, hardware) with per-purchase-batch cost tracking.
2. Maintain a separate catalog for consumables that shouldn't bind to specific products (Overhead: threads, glue, etc.) — those flow into P&L as a flat category, not as per-product COGS.
3. Author Bills of Materials (BOM) per Product so the system knows what goes into each finished good.
4. On order shipment, automatically consume materials from the warehouse at the current weighted-average unit cost — and write that cost back to `Order.production_cost` (or its computed twin during transition).
5. Surface material stock levels, low-stock warnings, and consumption history alongside the Packaging warehouse pattern established in PKG-1b/PKG-2.

After Phase 3 ships, manual `production_cost` becomes a graceful fallback for products that don't yet have a defined BOM. As BOM coverage approaches 100%, the manual field is retired.

## 2. Settled decisions (from 2026-05-14 discovery with Sergii)

These are not subject to relitigation during implementation sprints. If a sprint needs to revisit a decision, that's a planning-level conversation, not an implementation question.

| # | Decision | Rationale |
|---|---|---|
| 1 | **Two parallel entities — `Material` (Direct) and `OverheadMaterial` (Indirect).** Direct materials bind to product BOMs and decrement on shipment. Overhead materials are tracked as flat purchase expenses, no per-product allocation. | Matches Sergii's mental model: *"нитки можна рахувати як загальний витратний матеріал, немає сенсу в кожний виріб вностить"*. Also matches the **"Витратні матеріали" category** already present in the 2025-01-06 salesdrive YML export — Sergii had this split in his catalog years before this design discussion. Indirect materials would be expensive (in UX time) to track per-unit and the resulting precision wouldn't change Net Profit by a material amount. |
| 2 | **Cost method: Weighted Average.** On each `MaterialReceipt`, `current_unit_cost` recomputes as `(current_stock × current_unit_cost + receipt_qty × receipt_effective_cost) / (current_stock + receipt_qty)`. | Simpler than FIFO (no per-batch consumption tracking), more accurate than "last invoice wins" (which is volatile under bulk discounts or rush orders). Sergii has no prior preference; Weighted Average is industry-standard for small workshops. FIFO can be added later as a per-Material opt-in if a real need emerges. |
| 3 | **Shipping cost on receipts.** Optional `shipping_cost` field on `MaterialReceipt`. If present, `effective_unit_cost = (qty × unit_cost + shipping_cost) / qty` — i.e. transportation is amortised pro-rata across the units in the receipt. | Sergii explicitly named this as a gap in his current Excel approach: *"не враховую доставку, але це не правильно"*. One column, one line of computation, closes the gap. |
| 4 | **Material granularity per color/grade.** "Italian leather grade A — Black" and "Italian leather grade A — Red" are **two separate `Material` rows** with independent `current_unit_cost` and `stock_quantity`. BOMs reference the specific colored row. | Sergii: *"ціна на кольорову шкіру вище, я беру по вищому прайсу розрахунок"*. Without separate rows, the system can't reflect that price differential, which directly distorts COGS. Trade-off: catalog grows from ~50 generic types to maybe 80–120 color-specific rows. Acceptable; catalog UI supports search/filter. |
| 5 | **`waste_percent` on Material (default 0%).** Optional field. When consumption fires, `actual_consumed = recipe_qty × (1 + waste_percent/100)`. | Sergii doesn't currently track waste, but agreed to include it if the cost is low. Two-line implementation, zero impact when left at 0. Avoids the trap of designing for "perfect" waste tracking via separate events (which would require operator to log every scrap). |
| 6 | **Transition migration for `Order.production_cost`.** Three-phase migration: (Pre-cutover) manual entry preserved, BOM computation runs in parallel as `Order.computed_production_cost` for diagnostic; (Coexistence) UI shows both numbers side-by-side on order detail; (Post-cutover) BOM computation is authoritative when Product has a BOM, manual is fallback only when no BOM exists. | Sergii's preference for incremental migration over big-bang switch. Lets him fill BOMs gradually for high-volume products first, observe the discrepancy with manual values, build confidence, then flip the switch product-by-product or globally. |
| 7 | **BOM at the `Product` level, not `ProductVariant`.** One recipe per Product, applies to all Variants (sizes/colors). | Sergii: *"розмір/колір зазвичай не впливає [на consumption]"*. The cost differential between, say, black-leather and red-leather wallets is captured by Material granularity (decision #4) — the recipe stays the same, only the referenced colored Material changes. **If** in the future Sergii needs Large vs Small to consume different quantities, we add an optional per-Variant override layer; deferred until proven need. |
| 8 | **Units.** Leather → `dm²`; plywood → `m²`; everything else uses descriptive strings (`pcs`, `m`, `kg`, `spool`, `liter`) without enforced conversion. | Mixed-unit warehouses are normal in workshop accounting. Sergii: *"шкіру рахуємо в дм² фанеру в м² бо часто буває так що різний формат навіть у одного постачальника"* — confirms the per-Material unit choice; system doesn't try to convert between dm² and m² automatically. |
| 9 | **Initial inventory: manual UI, unified with regular receipt flow.** No CSV import in v1. Initial stock = a `MaterialReceipt` with `is_initial=true` flag — same code path as a normal purchase, same weighted-average recompute, no special bypass. | Sergii agreed to enter ~50 starter materials by hand. Single code path avoids fragmentation and reduces bug surface in MAT-2. CSV import is a documented follow-up (see §10). |
| 10 | **Soft-delete via `is_active=False`, never physical delete, never cascade.** When operator "deletes" a Material, the row stays in DB with `is_active=False`. BomItem rows referencing it stay intact. BOM editor renders a warning badge `⚠ Material discontinued` for inactive materials. | Sergii's choice. Preserves historical recipes: if you authored a Wallet recipe in 2024 with leather you no longer stock, you can still inspect/duplicate that recipe in 2026. No silent cascade-deactivation of BomItems either — recipes that reference inactive materials remain visible as a flag. |
| 11 | **`OverheadMaterialReceipt.shop_id: UUID \| None`.** If tagged → expense surfaces on `/shops/{id}/finance`. If NULL → expense surfaces on a global "Workshop overhead (unallocated)" card on `/dashboard`. | Sergii's choice. Flexible: tag when allocation is clear (e.g. "this batch of black thread was bought specifically for Lamamarka leather work"), leave NULL otherwise (e.g. "general workshop glue"). Avoids forcing pro-rata allocation logic that no one trusts. |
| 12 | **`Material.currency`** (NOT NULL) determines the currency of all its receipts. Mismatched currency on receipt → 422 validation error. | Sergii's reality today: 100% of material purchases are in UAH. Schema supports future EUR/USD purchases per-material but does not attempt cross-currency aggregation. If "Italian Black UAH" and "Italian Black USD" become real, they're two separate Material rows with the same display name (operator can disambiguate in notes). |

## 3. Domain model

Six new entities. None of them touches existing schema except for two additive columns on `Order` (`computed_production_cost` and possibly a feature flag).

### 3.1 Entity map

```
                  ┌─────────────────┐
                  │    Product      │  (existing)
                  └────────┬────────┘
                           │ 1:N (per-Product BOM)
                           ▼
                  ┌─────────────────┐                  ┌─────────────────────────┐
                  │     BomItem     │   ───references──▶│       Material          │
                  │ (recipe row)    │                  │ (Direct, Color/Grade)   │
                  └─────────────────┘                  └────────┬────────────────┘
                                                                │ 1:N
                                                                ▼
                                                       ┌─────────────────────────┐
                                                       │   MaterialReceipt       │
                                                       │ (purchase batch)        │
                                                       └─────────────────────────┘
                                                                │ writes to
                                                                ▼
                                                       ┌─────────────────────────┐
                                                       │   MaterialMovement      │
                                                       │ (ledger, PKG-2 pattern) │
                                                       └─────────────────────────┘
                                                                ▲ writes to
                                                                │ N:1
                  ┌─────────────────┐    on SHIPPED              │
                  │     Order       │ ───────────────────────────┘
                  └─────────────────┘                  (consumption rows)


                  ┌─────────────────┐       1:N      ┌──────────────────────────────┐
                  │ OverheadMaterial│ ──────────────▶│ OverheadMaterialReceipt      │
                  │ (Indirect)      │                │ (= expense event, P&L only)  │
                  └─────────────────┘                └──────────────────────────────┘
```

### 3.2 Entity details

#### 3.2.1 `Material` (Direct material)

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | str | NOT NULL | e.g. "Italian leather grade A — Black" |
| `unit` | str | NOT NULL | `dm2` \| `m2` \| `pcs` \| `m` \| `kg` (informational) |
| `currency` | str(3) | NOT NULL | ISO 4217 code: `UAH` / `USD` / `EUR`. All receipts for this Material must use this currency. |
| `current_unit_cost` | Decimal(12,4) | NOT NULL, default 0 | Weighted-average. Recomputed on each receipt. In `Material.currency`. |
| `stock_quantity` | Decimal(12,2) | NOT NULL, default 0 | Materialized from ledger sum (PKG-2 pattern). |
| `low_stock_threshold` | Decimal(12,2) | NOT NULL, default 0 | UI warning trigger. |
| `waste_percent` | Decimal(5,2) | NOT NULL, default 0 | E.g. 5.00 = 5%. Applied automatically on consumption. |
| `supplier_name` | str | NULL | Informational. |
| `notes` | text | NULL | Free text — include color/grade descriptors here if needed beyond `name`. |
| `is_active` | bool | NOT NULL, default true | Soft-delete flag. Never set to False via cascade; only via explicit user action. |
| `created_at`, `updated_at` | datetime | NOT NULL | |

Indexes: `(is_active, name)` for catalog browsing.

**Currency rule:** Material's currency is locked at creation. If Sergii buys "Italian Black" in UAH today and later starts buying it in USD, that's a second Material entry (`Italian Black (USD-batch)` or similar). Cross-currency aggregation is explicitly out of scope (see §10).

#### 3.2.2 `OverheadMaterial` (Indirect material)

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | str | NOT NULL | e.g. "Sewing thread (black)" |
| `unit` | str | NOT NULL | Informational only. `spool` / `liter` / etc. |
| `notes` | text | NULL | |
| `is_active` | bool | NOT NULL, default true | |
| `created_at`, `updated_at` | datetime | NOT NULL | |

**No `current_unit_cost`, no `stock_quantity`, no `waste_percent`** — overhead materials don't carry a running cost concept. Each purchase is a discrete expense, recorded in `OverheadMaterialReceipt` and surfaced in P&L as a category-level total.

#### 3.2.3 `MaterialReceipt` (Direct purchase batch)

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `material_id` | UUID | FK → Material, NOT NULL | |
| `qty` | Decimal(12,2) | NOT NULL, > 0 | Quantity received. |
| `unit_cost` | Decimal(12,4) | NOT NULL, ≥ 0 | Supplier's price per unit. |
| `currency` | str(3) | NOT NULL | Must match `Material.currency` of the referenced material (422 on mismatch). Persisted for audit even though redundant. |
| `shipping_cost` | Decimal(12,2) | NULL | Optional. Adds pro-rata to effective unit cost. Same currency as `unit_cost`. |
| `is_initial` | bool | NOT NULL, default false | True only for the receipt created when seeding initial inventory during Material creation. Used to distinguish in audit views. **No behavioral difference** — weighted-average recompute runs the same way. |
| `supplier` | str | NULL | |
| `invoice_no` | str | NULL | For audit reference. |
| `received_at` | datetime(tz) | NOT NULL | Defaults to "now" but operator can backdate. |
| `notes` | text | NULL | |
| `user_id` | UUID | FK → User, NOT NULL | Who recorded the receipt. |
| `created_at` | datetime(tz) | NOT NULL | |

**Effective unit cost computation** (Python-side, not stored — computed on the fly when needed):

```python
effective_unit_cost = (qty * unit_cost + (shipping_cost or 0)) / qty
```

**Weighted average recompute** on receipt insert (transactional, same DB session as receipt write):

```python
new_avg = ((material.stock_quantity * material.current_unit_cost) + (qty * effective_unit_cost))
          / (material.stock_quantity + qty)
material.current_unit_cost = new_avg
material.stock_quantity   += qty
```

Also writes a `MaterialMovement` row with `reason='receipt'`, `delta=+qty`, `receipt_id=…`.

#### 3.2.4 `OverheadMaterialReceipt` (Indirect purchase = expense event)

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `overhead_material_id` | UUID | FK → OverheadMaterial, NOT NULL | |
| `shop_id` | UUID | FK → Shop, NULL | **Optional tagging.** If set → expense attributes to that shop's finance page. If NULL → expense surfaces on global dashboard's "Workshop overhead (unallocated)" card. |
| `qty` | Decimal(12,2) | NULL | Informational (e.g. "5 spools"). |
| `total_cost` | Decimal(12,2) | NOT NULL, ≥ 0 | Total amount paid for this purchase. **Used directly as expense.** |
| `currency` | str(3) | NOT NULL | ISO 4217 code. Today expects UAH only. |
| `supplier` | str | NULL | |
| `invoice_no` | str | NULL | |
| `received_at` | datetime(tz) | NOT NULL | |
| `notes` | text | NULL | |
| `user_id` | UUID | FK → User, NOT NULL | |
| `created_at` | datetime(tz) | NOT NULL | |

Note the asymmetry vs MaterialReceipt: overhead receipts store `total_cost` directly, not `qty × unit_cost`. The reasoning is that overhead purchases often come in mixed-unit, mixed-content packages where unit cost is meaningless (e.g. "shop run, 850 UAH for assorted glue, thread, sandpaper") — Sergii enters a total figure, and that flows into P&L as overhead expense.

Indexes: `(shop_id, received_at)` partial on `WHERE shop_id IS NOT NULL` to speed up per-shop finance aggregation; `(received_at)` for the global card query.

#### 3.2.5 `MaterialMovement` (Direct material ledger)

Same shape as `PackagingStockMovement` from PKG-2. Append-only audit log of every stock change.

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `material_id` | UUID | FK → Material, NOT NULL | |
| `delta` | Decimal(12,2) | NOT NULL | + for receipts; − for consumption/waste; ± for adjustments. |
| `reason` | ENUM | NOT NULL | `receipt` \| `consumption` \| `waste` \| `adjustment`. (Initial stock uses `receipt` with the source receipt's `is_initial=true` flag — no separate enum value needed since unification.) |
| `order_id` | UUID | FK → Order, NULL | Set on `reason='consumption'`. |
| `receipt_id` | UUID | FK → MaterialReceipt, NULL | Set on `reason='receipt'`. |
| `unit_cost_at_movement` | Decimal(12,4) | NULL | **Locked-in cost** for consumption rows. NULL for receipts/adjustments. |
| `notes` | text | NULL | |
| `user_id` | UUID | FK → User, NOT NULL | |
| `created_at` | datetime(tz) | NOT NULL | |

`stock_quantity` on `Material` is the running sum of all `delta` for that material. Updated transactionally on every ledger write (PKG-2 pattern — `stock_service.apply_movement` style helper).

`unit_cost_at_movement` is critical for cost integrity: it snapshots the unit cost **at the moment of consumption**, so later receipts (which change `current_unit_cost`) don't retroactively alter the cost of orders already shipped. Receipts don't need this snapshot because their cost goes into the weighted average directly.

**DB-level CHECK constraint:** `(reason = 'consumption' AND unit_cost_at_movement IS NOT NULL) OR (reason != 'consumption' AND unit_cost_at_movement IS NULL)`. Prevents partial writes where a consumption row is missing its cost snapshot (which would corrupt COGS aggregations downstream). The Postgres syntax for this lives in the Alembic migration; service-layer code can rely on the constraint.

#### 3.2.6 `BomItem` (Bill of Materials line)

One row per (Product, Material) pair. Multiple rows per Product compose a recipe.

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `product_id` | UUID | FK → Product, NOT NULL | |
| `material_id` | UUID | FK → Material, NOT NULL | |
| `qty_per_unit` | Decimal(8,2) | NOT NULL, > 0 | Material units per 1 finished product unit. 0.01 precision (e.g. 5.50 dm² leather) is plenty for hand-crafted goods. |
| `notes` | str | NULL | E.g. "for back panel" — informational. |
| `created_at`, `updated_at` | datetime(tz) | NOT NULL | |

Unique constraint: `(product_id, material_id)`. To use the same material twice in a recipe (e.g. two different leather pieces), the design assumes you'd sum them into one row — if a real use case for separate lines emerges, drop the unique constraint and add a `position` column.

### 3.3 Additive changes to existing entities

#### `Order`

One new column:

- `computed_production_cost: Decimal(10,2) | None` — populated by the consumption hook on SHIPPED if the product(s) have BOM. NULL otherwise. **Independent of the existing `production_cost` field** — both can coexist during transition. Which one is authoritative for FIN-1's COGS card is determined by the migration phase (see §6.2) plus NULL checks at query time; no explicit source-tracking ENUM needed.

Existing `production_cost` field stays as-is. **No data is rewritten on migration.**

#### `Product`

No new columns. `has_bom` is exposed as a **computed property** in the API response (one cheap LEFT JOIN to check if any BomItem exists). Avoids the maintenance burden of a stored flag that would need triggers / service-layer updates on every BomItem insert/delete.

## 4. Workflows

### 4.1 Material purchase (Direct)

Operator opens `/inventory/materials/{id}`. Clicks **"+ Receipt"**. Modal:

```
Material:        Italian leather grade A — Black   (read-only, prefilled)
Currency:        UAH                               (read-only, from Material.currency)
Quantity:        [____] dm²
Unit cost:       [____] UAH per dm²
Shipping cost:   [____] UAH (optional)
Supplier:        [____] (optional)
Invoice #:       [____] (optional)
Received:        [datetime picker, default now]
Notes:           [____]

[Cancel]                                            [Save Receipt]
```

The currency field is **display-only** in the modal — taken from `Material.currency` automatically. Backend validates 422 if a request payload were to specify a different currency than the Material's (defensive against API-direct callers; UI can't trigger this).

On save (single transaction):

1. Compute `effective_unit_cost = (qty × unit_cost + shipping_cost) / qty`.
2. Compute `new_avg = ((stock × current_cost) + (qty × effective_unit_cost)) / (stock + qty)`.
3. Insert `MaterialReceipt` row (with `is_initial=false` for normal purchases).
4. Insert `MaterialMovement` row (`delta=+qty, reason='receipt', receipt_id=...`, `unit_cost_at_movement=NULL` per CHECK constraint).
5. Update `Material.stock_quantity += qty`, `Material.current_unit_cost = new_avg`.
6. Commit.

Toast: *"Прийнято 25 dm² Italian leather grade A — Black за 575 грн/dm² (з доставкою). Поточний середній: 580 грн/dm²."*

**Initial stock variant:** when creating a new Material with non-zero initial quantity, the same flow fires automatically with `is_initial=true` on the resulting receipt. From the code's perspective it's the same path; from the audit log's perspective the user can tell "this was the seed entry, not a real purchase" by the `is_initial` flag on `MaterialReceipt`.

### 4.2 BOM authoring

Operator opens `/products/{id}/bom` (new tab on existing product detail page, or new page — UX decision in MAT-3). Sees:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Recipe for: Wallet Premium Black                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Material                                | Qty per unit | Current cost | Sub │
│  Italian leather grade A — Black         | 5.00 dm²     | 580 UAH      | 2900│
│  Brass zipper 18cm                       | 1 pcs        | 45 UAH       | 45  │
│  Cotton thread (overhead, not counted)   |              |              |     │
│                                                                              │
│                                  Total computed cost: 2945 UAH               │
│                                  Manual production_cost: 3100 UAH (current)  │
│                                  Variance: −155 UAH (computed lower)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                            [+ Add Material]  [Save Changes]  │
└─────────────────────────────────────────────────────────────────────────────┘
```

Operator can add/remove/edit BomItem rows. On save, replace-all semantics: backend receives full list, deletes existing rows that aren't in the payload, upserts the rest. (Simpler than diff-patch; BOM size is small, typically 3-10 items.)

After save, `Product.has_bom` flips to true if it wasn't already.

### 4.3 Production consumption (automated, on SHIPPED transition)

Hooks into `services/order_service.transition_status(order, SHIPPED)`, immediately before the existing `order.shipped_at = now` line.

Pseudo-code:

```python
total_computed_cost = Decimal(0)
for item in order.items:
    product = item.product_variant.product
    bom_items = bom_repository.for_product(product.id)
    if not bom_items:
        continue  # Product has no BOM; manual production_cost remains authoritative
    for bom in bom_items:
        material = material_repository.get(bom.material_id)
        actual_consumed = bom.qty_per_unit * item.qty * (1 + material.waste_percent / 100)
        movement_service.apply(
            material_id=bom.material_id,
            delta=-actual_consumed,
            reason='consumption',
            order_id=order.id,
            unit_cost_at_movement=material.current_unit_cost,
            user_id=current_user.id,
        )
        total_computed_cost += actual_consumed * material.current_unit_cost

order.computed_production_cost = total_computed_cost
# Optionally: order.production_cost = total_computed_cost  (if cutover flag set, see §6.2)
```

**Permissive race policy** (PKG-2 pattern): no `SELECT FOR UPDATE`. If two shipments concurrently consume the same material's last few units and the counter goes negative, a warning toast surfaces and operator restocks. Workshop scale doesn't justify pessimistic locking.

**Transactional integrity:** the entire loop runs in the same DB transaction as the order status update. If anything fails — DB constraint, missing material, etc. — the whole transition rolls back, no partial state.

**Idempotency:** if SHIPPED → IN_PROGRESS → SHIPPED happens (status flip), do we double-consume? **No.** Consumption fires only on first SHIPPED transition. The `MaterialMovement` ledger is the source of truth: if a `consumption` row already exists for this `order_id`, skip the loop. This is the same idempotency guard as PKG-2's TTN-create.

### 4.4 Manual stock adjustments

Operator opens material detail, clicks **"Adjust Stock"**. Modal:

```
Current quantity:  120 dm²
Adjust by:         [____] dm²   (negative for reduction)
Reason:            [Dropdown: Stock count / Loss / Damage / Other]
Notes:             [____]

[Cancel]                                                              [Save]
```

Inserts `MaterialMovement` with `reason='adjustment'`, no order/receipt linkage. Used for stock-take reconciliation and operational corrections.

### 4.5 Overhead material purchase

Simpler than Direct. Operator opens `/inventory/overhead-materials/{id}`, clicks **"+ Receipt"**:

```
Overhead material:  Cotton thread (black)
Allocate to shop:   [Dropdown: — Unallocated — / KoraKlenu / Lamamarka / ...]
Quantity:           [____] spool  (optional, informational)
Total cost:         [____] UAH
Currency:           UAH                          (default, future-flexible)
Supplier:           [____] (optional)
Invoice #:          [____] (optional)
Received:           [datetime picker]
Notes:              [____]

[Cancel]                                                       [Save Expense]
```

The "Allocate to shop" dropdown is optional — defaults to **"— Unallocated —"** (sets `shop_id = NULL`). If the operator knows the expense was specifically for one shop's work, they pick that shop and the expense will surface on that shop's finance page. If left unallocated, it surfaces on the global dashboard as a workshop-wide overhead figure.

Inserts `OverheadMaterialReceipt`. No ledger, no stock counter, no current_cost update.

## 5. API endpoints (draft)

All routes role-gated `OWNER, MANAGER` unless noted otherwise.

### 5.1 Materials (Direct)

| Verb | Route | Purpose |
|---|---|---|
| `GET` | `/api/materials` | List active Direct materials. Filters: `search`, `is_active`. |
| `POST` | `/api/materials` | Create new Direct material. |
| `GET` | `/api/materials/{id}` | Detail incl. recent receipts and movements summary. |
| `PATCH` | `/api/materials/{id}` | Update name/threshold/waste_percent/notes/etc. |
| `DELETE` | `/api/materials/{id}` | Soft-delete (sets `is_active=False`); 409 if material referenced by any BomItem. |
| `POST` | `/api/materials/{id}/receipts` | Register a `MaterialReceipt` and recompute weighted-average. |
| `GET` | `/api/materials/{id}/receipts` | Paginated history. |
| `GET` | `/api/materials/{id}/movements` | Paginated ledger view. |
| `POST` | `/api/materials/{id}/adjust` | Manual stock adjustment. |

### 5.2 Overhead Materials

| Verb | Route | Purpose |
|---|---|---|
| `GET` | `/api/overhead-materials` | List. |
| `POST` | `/api/overhead-materials` | Create. |
| `GET` | `/api/overhead-materials/{id}` | Detail. |
| `PATCH` | `/api/overhead-materials/{id}` | Update. |
| `DELETE` | `/api/overhead-materials/{id}` | Soft-delete. |
| `POST` | `/api/overhead-materials/{id}/receipts` | Register expense receipt. |
| `GET` | `/api/overhead-materials/{id}/receipts` | History. |

### 5.3 Bill of Materials

| Verb | Route | Purpose |
|---|---|---|
| `GET` | `/api/products/{id}/bom` | Fetch full recipe (list of BomItems with material details + computed unit cost). |
| `PUT` | `/api/products/{id}/bom` | Replace recipe (full payload, server diffs internally). |
| `GET` | `/api/products/{id}/bom/cost` | Compute current unit cost for 1 finished product using live `current_unit_cost` values. |

### 5.4 Shop Finance integration

Extend the FIN-1 endpoint `/api/shops/{shop_id}/finance` response with one new card:

- **"Overhead expenses (allocated)"** — `SUM(OverheadMaterialReceipt.total_cost)` filtered by **`shop_id = :shop_id`** AND `received_at BETWEEN :start AND :end`. Per-currency breakdown if mixed currencies appear (today expects UAH only).

Net Profit calculation gets a new subtractive term:

```
Net Profit (per shop) = Revenue − COGS − Fees − Allocated Overhead Expenses
```

**Global overhead** (rows with `shop_id IS NULL`) does NOT subtract from any single shop's Net Profit. It surfaces on the global `/dashboard` as a separate card "Workshop overhead (unallocated)" — Sergii reads it as "operating cost that doesn't belong to any one shop". When calculating partner payouts end-of-month, he decides manually how to apportion it.

This is a **non-breaking** schema extension for `ShopFinanceResponse` — the new field is added; existing fields untouched. Dashboard endpoint (`/api/dashboard`) gets a similar additive `unallocated_overhead` field.

## 6. Migration strategy

### 6.1 Schema migrations

Three Alembic migrations, sequenced:

1. **`add_material_and_overhead_catalogs`** — `Material`, `OverheadMaterial` tables. No FK dependencies on Product yet.
2. **`add_material_receipts_and_movements`** — `MaterialReceipt`, `OverheadMaterialReceipt`, `MaterialMovement` tables + indexes + ENUM type for `MaterialMovement.reason`.
3. **`add_bom_and_order_computed_cost`** — `BomItem` table + `Order.computed_production_cost` column + (optional) `Order.production_cost_source` column.

Each migration must pass the `upgrade → downgrade → upgrade` round-trip (AI_ONBOARDING.md §9 invariant). Downgrade safety: dropping `MaterialMovement` rows on rollback is acceptable (it's a ledger but pre-launch); preserving `Order.production_cost` as untouched is critical (we never overwrite it during the additive phase).

### 6.2 `Order.production_cost` transition (three-phase)

**Phase A (MAT-4 ships):** Both fields live side-by-side.
- `production_cost` — manual, operator-entered, no behaviour change.
- `computed_production_cost` — auto-populated on SHIPPED if the product has a BOM. NULL otherwise.
- Order detail UI shows both, with a small diff badge if they differ by more than ±5%.
- FIN-1 page continues to use `production_cost` for the COGS card.

**Phase B (MAT-5 ships):** Computed becomes preferred where available.
- FIN-1 COGS card switches to `COALESCE(computed_production_cost, production_cost)`.
- Manual field still editable for products without a BOM (and for backfill on legacy orders).
- Order detail UI surfaces explicitly which value is being used.

**Phase C (eventual, after BOM coverage ≥ 90% in catalog):** Manual field is deprecated.
- `production_cost` column kept for legacy reads.
- New orders without a BOM display a banner: *"Create a BOM for this product or enter manual production_cost — Net Profit will be inaccurate otherwise."*
- Eventually rename `computed_production_cost` → `production_cost` (and rename the legacy field to `manual_production_cost_legacy`) — but only after Sergii is comfortable.

### 6.3 Seed / initial inventory

No automated import in v1. Two paths:

1. **Materials catalog seed (one-time, before initial use):** Sergii enters ~50 Direct materials and ~10–20 Overhead materials via the new catalog UI (MAT-1). Estimated time: 1–2 hours one-evening session. The 2025-01-06 salesdrive YML export *(loaded into this design as reference)* gives a partial reference list for Overhead materials but **no Direct materials** — salesdrive didn't track them as catalog entries.

2. **Initial stock entry (one-time, during Material creation):** The "Create Material" form has optional **"Initial quantity"** + **"Initial unit cost"** fields (same UX pattern as PKG-2's `PackagingBox.initial_quantity`). If `initial_quantity > 0` on form submit, a `MaterialReceipt` row is inserted with `is_initial=true`, `qty=initial_quantity`, `unit_cost=initial_unit_cost`, `shipping_cost=NULL`, with a corresponding `MaterialMovement` (`reason='receipt'`, `delta=+qty`). **Single code path** — no special bypass, no parallel `reason='initial'` ledger row. Weighted-average kicks in from this seed receipt forward.

   The `is_initial=true` flag on the receipt distinguishes "seed entry" from "real purchase" in audit views without changing any behaviour. Operator enters a starting average cost based on their Excel records.

CSV bulk import is a **post-MAT-1 follow-up** if and only if the manual entry experience proves painful. Filed in §10.

## 7. Implementation sprint breakdown

Five sequential sprints. Each acceptance gate is a manual smoke + automated tests; closure requires Sergii's sign-off.

### MAT-1 — Foundation (catalogs, no stock yet)

**Scope:**
- Backend: `Material`, `OverheadMaterial` models + Alembic migration 1 + CRUD endpoints (no receipts, no movements, no BOM yet). Soft-delete with 409 guard for materials referenced by BomItem (forward compatibility; check is no-op until MAT-3).
- Frontend: `/inventory/materials` list page + create/edit modals (same pattern as `/packaging`). `/inventory/overhead-materials` list page + modals.
- Sidebar: add **"Inventory" group** with sub-links `Packaging`, `Materials`, `Overhead`. Restructure existing `Packaging` link into this group.

**Acceptance:**
- Sergii creates 5+ Materials and 3+ OverheadMaterials. Soft-delete works. Catalog browse + search works.
- pytest passes.

**Effort estimate:** 1 sprint (~3-5 work sessions).

### MAT-2 — Receipts (stock tracking comes alive)

**Scope:**
- Backend: `MaterialReceipt`, `OverheadMaterialReceipt`, `MaterialMovement` models + Alembic migration 2 (incl. CHECK constraint on `unit_cost_at_movement`) + receipt endpoints + ledger endpoint + adjustment endpoint + currency-match validation (422 on mismatch). Weighted-average recompute logic. Standalone `material_stock_service.apply_movement` helper modelled on PKG-2's `stock_service.apply_movement` (do NOT refactor PKG-2's helper into a shared abstraction — keep them parallel until a real third use case justifies extraction).
- Frontend: Receipt modal on Material detail page (currency displayed read-only from Material). Receipt history table. Movements ledger view. Adjustment modal. Low-stock badge on catalog list (same visual as PKG-2's amber LOW badge).
- Material detail page: shows current stock, weighted-average cost, recent receipts, ledger history.

**Acceptance:**
- Sergii enters 10+ receipts across multiple materials, sees stock counters update + weighted-average recompute. Adjusts stock for one material. SQL inspection confirms ledger integrity.
- pytest passes (incl. compile-SQL guard for the weighted-average formula).

**Effort estimate:** 1-2 sprints.

### MAT-3 — BOM editor (recipes, no consumption yet)

**Scope:**
- Backend: `BomItem` model + Alembic migration 3 (also adds `Order.computed_production_cost` and `Order.production_cost_source` if we commit to that field; otherwise just `computed_production_cost`). BOM CRUD endpoints. Computed unit cost endpoint.
- Frontend: BOM tab on Product detail page. Recipe editor with add/remove/edit rows. Live computed cost display + variance vs manual cost.

**Acceptance:**
- Sergii authors BOMs for 3-5 high-volume products. Computed cost matches Excel estimates within reason. `has_bom` flag visible in product list.
- pytest passes.

**Effort estimate:** 1 sprint.

### MAT-4 — Consumption automation (the magic moment)

**Scope:**
- Backend: hook into `services/order_service.transition_status(order, SHIPPED)`. On transition: consume materials per BOM × qty × (1 + waste_percent/100), write MaterialMovement rows, snapshot unit_cost_at_movement, set `Order.computed_production_cost`. Idempotency guard via existing ledger rows for the order_id. Permissive race policy. Single-transaction integrity.
- Frontend: Order detail page shows both `production_cost` and `computed_production_cost` side-by-side with diff badge when they diverge by >5%. Toast on SHIPPED includes "Consumed N materials, computed cost X UAH". Negative-stock warning toast surfaces same as PKG-2.

**Acceptance:**
- Sergii ships an order with a BOM-equipped product. Material counters decrement. Computed cost appears on order detail. Stock ledger shows consumption row with correct unit_cost_at_movement snapshot.
- Status flip SHIPPED → IN_PROGRESS → SHIPPED doesn't double-consume.
- pytest passes (incl. test for the idempotency guard).

**Effort estimate:** 1-2 sprints. Highest risk surface — touches order lifecycle.

### MAT-5 — P&L integration + overhead surface

**Scope:**
- Backend: extend `/api/shops/{shop_id}/finance` response with `overhead_expenses` KPI card. Extend Net Profit formula to subtract overhead. Time-series chart: optionally split COGS into "Direct (BOM)" vs "Overhead" — defer if UI gets too dense.
- Frontend: render the new card. Diagnostic badge logic updates: now flags products without BOM (in addition to orders without production_cost).
- Phase B of cutover: FIN-1 COGS card prefers `computed_production_cost` over `production_cost` when both exist.

**Acceptance:**
- Lamamarka finance page shows overhead expenses correctly summing `OverheadMaterialReceipt` totals. Net Profit reflects the new term. Manual COGS values still show for orders without BOMs.
- pytest passes.

**Effort estimate:** 1 sprint.

### MAT-6 — (Future, optional) Cutover finalisation + cleanup

Not part of the initial five-sprint scope. Triggered when BOM coverage approaches 90% of active products. Renames columns, deprecates manual UX, adds banner messaging. Documented here as the endgame; sprint spec written when we get there.

---

**Total effort estimate for MAT-1 through MAT-5: ~6–8 sprints.** Comparable to the FIN-1 sprint scope, spread over multiple work sessions. Each sprint individually low-risk; cumulative impact is substantial.

## 8. Open questions (mostly resolved)

Status legend: **R** = resolved by review-round-1; **D** = deferred to sprint planning when reached.

1. **(R)** **Material soft-delete + BomItem reference:** Resolved in settled-decision #10 — soft-delete via `is_active=False`, BomItem rows preserved with a "discontinued" warning badge in BOM editor.
2. **(D)** **Backfill of legacy orders.** Currently shipped orders have manual `production_cost`. Migration phases A → B → C explicitly leave legacy orders untouched. Re-costing past orders after retroactive BOM additions is **not in scope** for MAT-* — listed in §9 Known Limitations #2. Confirm operational impact in MAT-5 planning.
3. **(R)** **Currency on receipts and Material.** Resolved in settled-decision #12 — both Material and Receipt carry `currency` field; Material's value locks all its receipts; cross-currency aggregation explicitly out of scope.
4. **(D)** **Receipts on partner-supplied materials.** Sometimes a partner brings materials (free or at cost) for a specific project. Defer to Phase 2 (Partners) when it arrives — for now, operator records a `MaterialReceipt` with `unit_cost=0` and a note. Or skips the receipt entirely if it's a one-off out-of-system delivery.
5. **(R)** **BomItem `qty_per_unit` precision.** Resolved — `Decimal(8,2)`. 0.01 precision is plenty for hand-crafted goods.
6. **(D)** **Order detail UI density.** Side-by-side manual + computed cost might be visually heavy. Alternative: single field with badge indicating source. Surface in MAT-4 UI planning.
7. **(R)** **Why store `current_unit_cost` on Material rather than compute from ledger on demand?** Because (a) it's the same denormalisation pattern PKG-2 uses for stock_quantity, (b) FIN-1's COGS query becomes a simple `JOIN materials` instead of a windowed ledger aggregation, (c) Sergii will look at it in the catalog UI constantly. Performance >> theoretical purity here.
8. **(D)** **Stock-take feature.** Eventually Sergii will want a "physical count vs system count" reconciliation flow. Out of MAT-1..5 scope. File when raised.
9. **(D)** **Diff-badge threshold for computed vs manual production_cost** (default 5%). Configurable per-shop in shop settings, or global constant? Surface in MAT-4 planning; cheap to make configurable but YAGNI for v1.

## 9. Known limitations (accepted, not bugs)

Honest gaps in v1 that we're explicitly choosing not to close yet. Each is fixable with a future sprint if and when the operational need outweighs the engineering cost.

1. **~~Multi-currency COGS rollup.~~ CLOSED by FX-CONVERSION (2026-08-02).** Material currency (always UAH today) and Order currency (UAH for KoraKlenu, USD for Lamamarka/Etsy) used to mismatch, and the rollup was skipped whenever they did. Since FX-CONVERSION, the consumption fold accumulates per-currency buckets and converts each into `Order.currency` at the single UAH/USD rate in Settings, so `computed_production_cost` is always denominated in `Order.currency` and FIN-1's per-currency Net Profit no longer mixes units. The rate used, plus the pre-conversion basis, is frozen onto the order (`cogs_fx_rate`, `cogs_basis_amount`, `cogs_basis_currency`) — changing the rate later only affects future ships. **Residual gaps:** (a) only UAH↔USD is built; an order in any other currency still degrades to a null cost with a warning while stock is consumed; (b) if *any* material currency in the recipe cannot be converted, the whole cost is nulled rather than partially booked (deliberate — a partial cost would under-state COGS and over-state profit silently); (c) orders shipped before the cutover keep their null cost, since costing remains forward-only (limitation 2).
2. **Backfill of historical orders.** Adding a BOM today for a Product whose orders shipped last month does NOT retroactively re-cost those orders. They keep their original manual `production_cost`. By-design (immutable history); a "Re-cost shipped orders since date X" admin action could be added later if needed.
3. **Concurrent-receipt race on weighted-average.** If two operators register a receipt on the same Material simultaneously, the second write overwrites the first's computed weighted-average (last-write-wins, optimistic-free pattern matching PKG-2's permissive race policy on stock counts). **Practical impact:** Sergii is the only operator today; if someone hires help, this becomes a real concern and we add optimistic-locking via a `version` column. Documented assumption: **single-operator workshop**.
4. **Waste expense invisibility.** Materials lost to `waste_percent` are included in COGS (correct), but no dashboard surfaces "you wasted X UAH on brak this period". Operator only sees waste indirectly through higher consumption rates. Future feature: a "Waste expense" card on the materials dashboard.
5. **`current_unit_cost` snapshot lag.** Between a receipt at 10:00 and the next consumption at 10:05, any reads of `Material.current_unit_cost` reflect the new average. Reports based on point-in-time costs are fine (use `MaterialMovement.unit_cost_at_movement` for historical answers), but there's no "what was the unit cost on 2026-04-15" query helper in v1. Easy to add when reporting needs it.
6. **No BOM revision history.** Edit a BOM today, the previous recipe is overwritten. To know "what was the recipe when order #123 shipped 6 months ago", reconstruct from `MaterialMovement` rows attached to that order's `order_id`. Explicit BOM versioning is a future feature.
7. **Per-Variant BOM not supported.** Per settled-decision #7, recipes live at Product level. If "Large wallet" ever needs more leather than "Small wallet", add a per-Variant override layer — but until then, recipes apply to the whole Product.

## 10. Out of scope (explicit non-goals)

These are deliberately not part of Phase 3. If they become important, they're new epics, not scope creep into MAT-* sprints. (Some items here are also referenced in §9 Known Limitations — the distinction is that §9 are limitations *we live with in v1*, while §10 are features we deliberately don't build.)

- **FIFO/LIFO cost methods.** Weighted Average only. FIFO can be a per-Material opt-in later if a use case emerges (e.g. inflation-sensitive materials where lot-tracking matters for partner accounting).
- **Multi-warehouse.** Same parked decision from PKG-1b — until Lamamarka opens a second location or a partner has a separate stash, single global warehouse is correct.
- **Material price history graphs.** Receipts carry timestamps; a "leather cost over the last year" chart is trivially derivable but not built in v1.
- **CSV bulk import of materials.** Manual UI entry for v1. If pain emerges, build it; if not, save the engineering time.
- **Material supplier catalog.** `supplier` is a free-text string for now. Promoting it to a `Supplier` entity with deduplication, contact info, etc. is a future feature.
- **OCR / photo invoice import (the "agent reads видаткова накладна" feature).** Sergii's far-future MCP idea. Blocked until materials warehouse is solid and there's volume worth automating. Filed for posterity.
- **FX conversion between Material currency and Order currency.** Documented as Known Limitation #1 (§9). Real impact for Lamamarka/Etsy; out of MAT-* scope; needs a separate FX-rate-management epic that also affects Order aggregation in Net Profit.
- **Predictive reorder suggestions.** Low-stock badge alerts; no auto-purchase or recommendation logic.
- **Recipe versioning / change history on BOM.** Documented as Known Limitation #6. Current design has implicit "last edit wins"; reconstruction possible from MaterialMovement ledger.
- **Per-Variant BOM overrides.** Per settled decision #7, recipes live at the Product level.
- **Order BomItem snapshotting.** Could store BomItem snapshot in `OrderItem` for full historical reconstruction. Deferred — the MaterialMovement ledger with `order_id` + `unit_cost_at_movement` already gives us the consumption record for that order.
- **Pro-rata allocation of unallocated overhead expenses to shops.** Per settled-decision #11, expenses with `shop_id=NULL` stay on a global card; Sergii does any allocation manually when calculating partner payouts.

---

## 11. Next steps

1. Sergii reads this doc; flags any decisions to revisit, fills in open questions where ready, adds use cases I missed.
2. Cowork iterates the doc until "ship-ready" — usually 1–2 rounds.
3. We break MAT-1 into a `task.md` spec, run it as a regular sprint following the AI_ONBOARDING.md workflow. Subsequent MAT-* sprints follow as catalog matures and BOMs accumulate.
4. Phase 2 (Partners) re-enters the conversation whenever Sergii is ready. Phase 3 (this doc) doesn't block Phase 2 design — only the reverse.

**This document lives at `docs/design/materials-warehouse.md` and should be edited in-place as decisions evolve. Each material update gets a short note at the top in the Status line.**

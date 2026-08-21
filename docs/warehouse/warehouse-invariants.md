# Warehouse Invariants — As Shipped (WH-1 + WH-2)

**Status:** describes the state of `main`. Extracted verbatim from CLAUDE.md § Gotchas on 2026-08-21 (docs restructuring; content unchanged, only re-sectioned).
**Read this BEFORE touching** materials, packaging boxes, BOM, consumption, receipts, or the SHIPPED transition / shipping stock effects.
**Why it was designed this way:** `docs/warehouse/DESIGN-inventory-architecture.md` (proposal + rejected alternatives). **Sprint history:** `implementation_plan.md` → WH-1, WH-2.

## 1. Warehouse unification (WH-1, merged + deployed 2026-08-07)

Every `packaging_boxes` row is 1:1 paired with a `Material` — `packaging_boxes.material_id` (NOT NULL UNIQUE FK RESTRICT), `materials.category` (`'MATERIAL'|'PACKAGING'`, **plain String, NOT a PG enum** — `Capability` precedent), `materials.is_stock_tracked` (untracked BOM lines contribute cost to `computed_production_cost` but never write movements or decrement stock — that's how services like cutting/sewing are modelled).

- Paired lifecycle is `catalog_service`-only: box create → material+geometry in one transaction; box rename syncs the material name; box delete **archives** the material.
- `PATCH /api/materials` answers **409** for rename/category change on a box-backed material.
- BOM picker and the default materials list filter `category=MATERIAL`.
- `consume_materials_for_order` idempotency is movement-probe **plus** `computed_production_cost`-already-set (an all-untracked recipe leaves no ledger row); accepted delta: an FX-failed first ship (cost=None) recomputes on a later ship.
- Prod has ZERO packaging boxes until WH-3 seeds the catalog.

## 2. Packaging consumed at SHIPPED (WH-2, branch `feat/wh-2-consumption-shipped`)

The box is consumed **once per parcel at SHIPPED**, in `order_consumption_service` under the same idempotency guard as BOM materials — `order.packaging_id`, falling back to `computed_packaging_box_id` with a ⓘ warning; both NULL is legal and silent (pickup). One unit per *shipment*, never per product, which is why packaging is deliberately not a BOM line.

- The box is resolved **before** the first movement is staged (every read precedes every write, so the fold stays autoflush-free) and **the block may never raise** — `routers/shipping.py` catches bare `Exception` and rolls back *after* NP has already minted the label, so a missing box/material degrades to a warning.
- **The TTN no longer touches stock at all**: both `apply_movement` calls in `shipping.py` are gone, and deleting a TTN gives nothing back (re-shipping is stopped by the ledger probe, not by a give-back).
- **`bom_equipped == 0` still books NULL** — a box-only `computed_production_cost` would win the row-wise `COALESCE(computed, manual, 0)` in five aggregates (`finance_service` KPI cogs, `_run_product_only_aggregate` → the PROFIT partner base, `compute_base_quality`, dashboard) and replace a hand-entered `production_cost`; the box is consumed anyway and a ⓘ warning says the cost was not booked.
- Counters moved onto the paired materials (migration `f2a7c1d84b63`: stock **summed** so a post-WH-1 receipt is never destroyed, threshold copied only where the material's is still WH-1's 0; downgrade restores from *current* values via a carrier table).
- `packaging_boxes.stock_quantity`/`low_stock_threshold` are **dropped** — `PackagingBox` exposes same-named **properties** over `self.material`, so a box read without its material raises `MissingGreenlet` (deliberate: the three sites that build `PackagingBoxRead` load it explicitly; the relationship stays default-lazy because `Order.packaging` is `selectin` and would tax every orders page).
- `packaging_stock_movements` is **frozen** — `services/stock_service.py` was deleted, so nothing can write it. Box **delete now archives** (geometry row survives; hard delete used to CASCADE that frozen ledger away); the parcel calculator filters `Material.is_active`, never stock.
- Restock is gone — replenishment is a material receipt, which puts it behind `view_costs` (managers default to no capabilities; the page disables the action rather than 403-ing).
- `PackagingBoxRead` counters are **Decimals → JSON strings**: always `Number()` them before comparing, or `"10" <= "5"` lights the low-stock badge on healthy boxes. `PackagingBoxCreate` is `extra="forbid"` so a stale client sending the removed `initial_quantity` gets a loud 422.
- The packaging picker and parcel estimate are **no longer UA-gated** (they were, which meant international orders could never resolve a box).
- `apply_receipt`'s `stock_quantity <= 0` re-baseline already *is* the negative-stock WAC clamp — no code change, regression test only.

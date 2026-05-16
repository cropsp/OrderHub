# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Design source of truth:** [docs/design/partner-payouts.md](docs/design/partner-payouts.md) v1.1 — full PART-1 design (entities, formulas, UI, edge cases). Read this first.
> - **Profit reference:** [docs/design/profit-definition.md](docs/design/profit-definition.md) v1.1 — `net_profit_product_only` formula and why partners use a different "profit" than FIN-1.
> - **Current task:** PART-1 — Partner Payouts monoblock (settlements + payments + balance + Shipping Net KPI)
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## PART-1 — Partner Payouts monoblock (settlements + payments + balance + Shipping Net KPI)

### Goal

Phase 2 of the Finance epic. Replace Sergii's Excel-based partner payout tracking with a first-class CRM surface: per-period settlement calculator that **freezes a base + computed amount snapshot** at save time, a **payments ledger** that tracks the actual money movements out to partners (with multiple partial payments per settlement supported), a **live per-partner balance** (`SUM(settlements) − SUM(payments)` per `(shop, partner, currency)`), and an informational **Shipping Net KPI** card on the FIN-1 finance page.

**Single monoblock sprint per Sergii's confirmation** (*"PART-1 моноблок"*). Larger than FIN-1 because it ships two entities (PartnerSettlement + PartnerPayment), two formulas (`revenue_items_minus_fees` + `net_profit_product_only`), per-partner balance computation, the Shipping Net KPI card, and the full UI for all of the above. Each individual piece is straightforward CRUD + aggregation; none break new patterns.

**Why this matters:** OrderHub's original raison d'être was Sergii's frustration with Excel-driven partner payouts. FIN-1 delivered the underlying numbers; Phase 3 Materials Warehouse made those numbers trustworthy (BOM-computed COGS); PART-1 finally ships the operator-facing surface that closes the loop on the original ask. Partial payment tracking + balance display were surfaced during second-pass discovery and are first-class in this sprint (decisions #12-15 in `partner-payouts.md` §2).

**Critical formula deviation:** all four profit-share partners use `net_profit_product_only` — NOT FIN-1's full Net Profit. This formula excludes shipping economics (shipping revenue AND shipping cost) from the partner-share base because partners contribute nothing to shipping logistics. See `profit-definition.md` §6 for the rationale and `partner-payouts.md` §4.2 for the SQL sketch. FIN-1's Net Profit definition is **unchanged**; the new formula lives alongside it.

### Behaviour rules (settled — do not relitigate)

1. **Single atomic commit, single sprint (monoblock).** Commit message: `feat(part-1): partner payouts + payments ledger + shipping net kpi`. Squash any work-in-progress micro-commits before pushing.

2. **No Partner entity.** `partner_name` is free text (`str(200)`) on both `partner_settlements` and `partner_payments`. Autocomplete dropdown populated from DISTINCT union of both tables drives UX consistency. Typo risk is an accepted limitation (`partner-payouts.md` §6.3); do not add a `Partner` model.

3. **No FIN-1 schema mutation.** PART-1 adds two new tables and a new Postgres ENUM (`partner_settlement_formula`). It does NOT change `orders`, `order_items`, `overhead_material_receipts`, or any existing FIN-1 column. The only additive change to existing FIN-1 surface is two new helper methods on `finance_service` (`compute_net_profit_product_only`, `compute_shipping_net`) and one optional new field on the `/shops/{id}/finance` response payload (Shipping Net KPI, auto-omitted when zero).

4. **Snapshot pattern: `base_amount` and `computed_amount` frozen on settlement creation.** Same audit-integrity pattern as MAT-2's `MaterialMovement.unit_cost_at_movement`. If FIN-1 numbers change retroactively (e.g. a new receipt added in June changes May's COGS), already-saved May settlements DO NOT recompute. Settlement is "this is what I computed and told the partner that day."

5. **Settlements and payments are immutable + delete-and-recreate.** No edit endpoint, no update endpoint, no PATCH. Wrong value → operator deletes the row and creates a new one. Hard delete is acceptable (Sergii on simplified taxation, no audit-retention requirement).

6. **Two formula types in the new ENUM:** `revenue_items_minus_fees` AND `net_profit_product_only`. Postgres ENUM name: `partner_settlement_formula`. Do NOT add a third `net_profit` (with shipping) option — explicitly rejected per decision #17. Do NOT add a speculative `revenue_total` option — YAGNI.

7. **`net_profit_product_only` formula** = `SUM(OrderItem.quantity × OrderItem.unit_price) − SUM(COALESCE(orders.computed_production_cost, orders.production_cost, 0)) − SUM(COALESCE(orders.platform_fee, 0)) − SUM(COALESCE(overhead_material_receipts.total_cost, 0))` — per currency, per shop, per period. **Differences from FIN-1 Net Profit:** revenue is `OrderItem.qty × unit_price` (items only, no shipping) instead of `Order.total_price`; fees are `platform_fee` only (NOT `shipping_np_cost`). COGS and overhead are unchanged. Filters mirror FIN-1: `orders.shop_id = :shop_id AND status IN ('shipped', 'completed') AND COALESCE(shipped_at, ordered_at) BETWEEN :start AND :end`; overhead filter on `overhead_material_receipts.shop_id = :shop_id` + receipt-date in period.

8. **`revenue_items_minus_fees` formula** = `SUM(OrderItem.quantity × OrderItem.unit_price) − SUM(COALESCE(orders.platform_fee, 0))` — per currency, per shop, per period. Same filters as rule #7. Used ONLY by Sergii's Lamamarka Shopify creative partner case.

9. **`net_profit_product_only` and `compute_shipping_net` live in `finance_service`, NOT in `partner_payout_service`.** Keeps FIN-1 formula primitives co-located. `partner_payout_service` simply calls the appropriate helper based on `formula_type`. This mirrors how MAT-5's COGS preference lives in finance_service even though it's consumed by multiple surfaces.

10. **`PartnerPayment.settlement_id` is NULLABLE with `ondelete='SET NULL'`.** Linked payments enable per-settlement progress badges ("Paid 1,000 / 2,450"); unlinked payments still count toward overall partner balance. Deleting a settlement DOES NOT delete its payments — payments survive with `settlement_id = NULL` (UI warns operator at delete time per `partner-payouts.md` §6.7).

11. **Balance computation: `SUM(settlements.computed_amount) − SUM(payments.amount)` per `(shop_id, partner_name, currency)`.** Computed live in `get_partner_balances()`, not materialized. **CRITICAL implementation note:** do NOT compute via a single LEFT JOIN — that multiplies rows when a partner has both N settlements and M payments. Compute the two aggregates separately (two queries OR one query with subqueries), then combine in Python. The SQL sketch in `partner-payouts.md` §3.5 is illustrative only; pin the exact shape in the plan with verified correctness on multi-settlement-multi-payment fixtures.

12. **Per-settlement payment progress**: each settlement row in the UI shows `SUM(payments.amount WHERE settlement_id = settlement.id)`. Badge states: no payments → grey "Unpaid"; partial → orange "Paid X / Y"; equal → green "Paid in full"; over → purple "Overpaid by X". Service method: `compute_settlement_payment_progress(db, settlement_ids: list[UUID]) -> dict[UUID, Decimal]` (one query, GROUP BY settlement_id, returned as a dict for O(1) lookup during list rendering).

13. **Shipping Net KPI** = `SUM(orders.total_price − items_subtotal) − SUM(COALESCE(orders.shipping_np_cost, 0))` per currency, per period, where `items_subtotal = SUM(OrderItem.qty × OrderItem.unit_price)` per order. Same filters as rule #7. **Auto-hide rule:** if both shipping_revenue AND shipping_cost are zero for the period, the KPI card is NOT rendered (typical Etsy-only shops where customer pays NP directly).

14. **Role gating:** all new endpoints and the Partner Payouts UI section are `OWNER` + `MANAGER` only. `DESIGNER` role → 403 on every PART-1 endpoint. Mirror existing FIN-1 / MAT-5 gating pattern (CC: grep for the existing role dependency helper).

15. **Currency-mismatch on payment: warn but don't block.** If operator picks a settlement in USD but selects UAH for the payment, inline orange warning (`"Currency differs from linked settlement. The payment will not contribute to the USD balance for this partner."`) — operator may proceed. Backend stores the payment as recorded (no auto-conversion). Currency-mismatched payments simply don't contribute to that partner's balance in the linked-settlement currency.

16. **Negative base banner: warn but don't block.** When live-preview shows negative `base_amount` (loss period), show info banner per `partner-payouts.md` §6.4. Operator decides whether to save (Sergii's policy is to absorb losses himself — see `profit-definition.md` Q4 — so typically operator declines).

17. **Multi-currency in one period: dropdown.** If formula returns multiple currency rows for the period (rare; happens if KoraKlenu ever takes a USD order), modal shows a currency dropdown. Single-currency = dropdown auto-selected/hidden.

18. **No FX storage in either entity.** Settlement currency = whatever currency the base aggregation produced. Payment currency = operator's free choice. Operator handles UAH equivalent at payment time mentally. No FX rate stored anywhere in PART-1 (per `profit-definition.md` Q3, deferred indefinitely).

### Scope

- **In scope, backend — new files:**
  - **`backend/models/partner_settlement.py`** — `PartnerSettlement` SQLAlchemy model per `partner-payouts.md` §3.1 schema. Use existing `UUIDPrimaryKeyMixin` + `TimestampMixin` pattern (CC: grep for these mixins to confirm names). Decimal columns use `Numeric(precision, scale)` per existing convention (CC: grep for `Numeric(` in `backend/models/` to confirm). CHECK constraints declared via `__table_args__`. No `relationship()` back-references to Shop / User (lightweight read-only references; service uses explicit JOINs). Define `partner_settlement_formula` Postgres ENUM as a separate `sqlalchemy.Enum(..., name='partner_settlement_formula')` per existing enum pattern (CC: grep `sqlalchemy.Enum(` in models to mirror style).
  - **`backend/models/partner_payment.py`** — `PartnerPayment` SQLAlchemy model per `partner-payouts.md` §3.4 schema. `settlement_id` is `Mapped[UUID | None]` with `ForeignKey('partner_settlements.id', ondelete='SET NULL')`. CHECK constraint `amount > 0` via `__table_args__`.
  - **`backend/schemas/partner_payout.py`** — Pydantic request/response models:
    - `PartnerSettlementCreate` (partner_name, formula_type, percent, period_start, period_end, notes; base_amount + computed_amount are computed server-side from formula + period — NOT taken from request)
    - `PartnerSettlementResponse` (all columns + `paid_amount: Decimal` populated from `compute_settlement_payment_progress`)
    - `PartnerSettlementListResponse` (paginated)
    - `PartnerPaymentCreate` (partner_name, settlement_id, amount, currency, paid_at, notes)
    - `PartnerPaymentResponse`
    - `PartnerPaymentListResponse` (paginated)
    - `PartnerBalanceResponse` (partner_name, currency, total_settled, total_paid, balance_owed)
    - `PartnerBalancesResponse` (list of above)
    - `PartnerPayoutPreviewRequest` (formula_type, percent, period_start, period_end, optional currency for multi-currency disambiguation)
    - `PartnerPayoutPreviewResponse` (base_amount, base_currency, computed_amount, OR list of CurrencyAmount when multi-currency without filter)
    - `ShippingNetCurrencyAmount` (currency, amount) — used in FIN-1 response extension
  - **`backend/services/partner_payout_service.py`** — new service module with methods listed under rule #11 + #12 + create/list/delete for both entities. Each method takes `db: AsyncSession` (or `Session` — CC: confirm sync vs async pattern via `finance_service.py`) as first arg per existing convention.
  - **`backend/routers/partner_payouts.py`** — new router with the 8 endpoints from `partner-payouts.md` §7 (preview, settlement create/list/delete, payment create/list/delete, balances, partner-names autocomplete). All role-gated `OWNER` + `MANAGER` per rule #14.
  - **Alembic migration** — one revision, autogenerated then hand-tuned: creates `partner_settlement_formula` ENUM, creates both tables with their indexes + CHECK constraints, no data migration needed. CC must verify autogenerate detects all constraints (CHECK constraints often need manual addition — see `partner-payouts.md` §3 column constraints).

- **In scope, backend — extensions to existing files:**
  - **`backend/services/finance_service.py`** — add two methods:
    - `compute_net_profit_product_only(db, shop_id, period_start, period_end) -> list[CurrencyAmount]` per formula in rule #7. Should reuse as much of the existing `compute_net_profit` plumbing as possible — query filters, currency grouping, overhead JOIN. The deltas are: items_revenue from OrderItem JOIN instead of `total_price` SUM, and platform_fee only (drop the shipping_np_cost term from fees).
    - `compute_shipping_net(db, shop_id, period_start, period_end) -> list[CurrencyAmount]` per rule #13.
  - **`backend/routers/shops.py` (or wherever `/shops/{id}/finance` lives — CC: grep for the existing endpoint)** — extend the response payload to include `shipping_net: list[ShippingNetCurrencyAmount]` field. Auto-empty list when zero (frontend handles the auto-hide decision). Backwards-compatible addition (existing fields unchanged).
  - **`backend/main.py` (or wherever routers are mounted)** — register the new `partner_payouts` router under `/api/shops/{id}/partner-payouts`.

- **In scope, backend tests:**
  - **`tests/test_partner_payout_service.py` (new)** — 8-10 tests:
    - `revenue_items_minus_fees` formula correctness (seed orders + items + fees, assert base_amount)
    - `net_profit_product_only` formula correctness (seed orders + items + production_cost + platform_fee + overhead_receipts, assert base_amount)
    - Settlement create persists snapshot values (verify base_amount / computed_amount frozen at row insert time)
    - Settlement create with negative base (loss period) does NOT raise — stored as-is
    - Settlement delete: linked payments survive with `settlement_id = NULL`
    - Payment create persists; linked payment contributes to per-settlement progress
    - Balance computation: single partner, multi-partner-same-shop, multi-currency-same-partner (verify no row multiplication bug per rule #11 — seed 3 settlements + 2 payments, assert balance correct)
    - Per-settlement progress: unpaid / partial / full / overpaid states each compute correctly
    - Currency-mismatched payment: stored as-is, does NOT contribute to mismatched-currency balance
  - **`tests/test_finance_service.py` (extend)** — 3 new tests:
    - `compute_net_profit_product_only` excludes shipping (seed an order where shipping economics flip sign of FIN-1 Net Profit, assert product-only formula gives different result)
    - `compute_shipping_net` correctness (shipping_revenue − shipping_cost per currency)
    - `compute_shipping_net` returns empty list when both components are zero
  - **`tests/test_partner_payouts_router.py` (new)** — 4-5 tests: role gating (DESIGNER → 403 on each endpoint; OWNER + MANAGER → 200); path-param validation (invalid UUID → 422); happy-path create / list / delete cycle; preview endpoint returns expected shape.
  - **Expected pytest delta:** ~153 → ~170 (+~17). CC must confirm current baseline before sprint start.

- **In scope, frontend — new files:**
  - **`frontend/src/pages/finance/PartnerPayouts.tsx` (or co-located inside the existing Finance page — CC: grep for `/shops/{id}/finance` page component)** — top-level section component composing the balances summary + settlements table + payments table.
  - **`frontend/src/components/finance/PartnerBalancesSummary.tsx`** — renders per-partner-per-currency balance rows per `partner-payouts.md` §5.1 layout. Hidden when no settlements exist.
  - **`frontend/src/components/finance/PartnerSettlementsTable.tsx`** — log table with payment-progress badges + per-row `[+ Record Payment]` + `[Delete]` actions.
  - **`frontend/src/components/finance/PartnerPaymentsTable.tsx`** — payments ledger with `[Delete]` per row + linked-settlement reference.
  - **`frontend/src/components/finance/CalculateSettlementModal.tsx`** — calculator modal per `partner-payouts.md` §5.2: partner name (autocomplete), formula dropdown (2 options), percent input, period (inherited / override), live preview, save checkbox, notes, save action.
  - **`frontend/src/components/finance/RecordPaymentModal.tsx`** — payment entry modal per §5.3: partner name (autocomplete), linked-settlement dropdown (optional, filtered by partner), amount + currency, paid_at date, notes. Pre-fills when launched from a settlement row's button.
  - **`frontend/src/components/finance/ShippingNetKpi.tsx`** — small KPI card sitting in the existing FIN-1 KPI grid. Auto-hides when value is zero.
  - **`frontend/src/api/partnerPayouts.ts`** — Axios methods for the 8 endpoints + types from backend Pydantic models.
  - **`frontend/src/hooks/usePartnerPayouts.ts`** — React Query hooks (one per endpoint). Mutation hooks invalidate the relevant query keys: creating/deleting a settlement invalidates settlements list + balances + per-settlement-progress; creating/deleting a payment invalidates payments list + balances + per-settlement-progress for the linked settlement.

- **In scope, frontend — extensions to existing files:**
  - **`frontend/src/pages/finance/Finance.tsx` (or whatever the existing `/shops/{id}/finance` page is called)** — add the Shipping Net KPI to the existing KPI grid (placed alongside Revenue / COGS / Fees / Overhead / Net Profit per the existing grid order). Add the new "Partner Payouts" section below existing surfaces.

- **In scope, frontend tests:**
  - **`frontend/src/components/finance/__tests__/CalculateSettlementModal.test.tsx`** — modal renders both formula options; live preview updates on percent change; save button label changes with checkbox state.
  - **`frontend/src/components/finance/__tests__/PartnerSettlementsTable.test.tsx`** — progress badges render correctly for each state (unpaid / partial / full / overpaid).
  - **`frontend/src/components/finance/__tests__/RecordPaymentModal.test.tsx`** — pre-fill from settlement context; currency-mismatch warning shows when applicable.
  - **`frontend/src/components/finance/__tests__/ShippingNetKpi.test.tsx`** — renders when non-zero; doesn't render when both components are zero.
  - **Expected vitest delta:** ~4-6 new test files, each with 2-4 cases.

- **Out of scope (do NOT touch):**
  - **PDF generation** — deferred to PART-2 (`partner-payouts.md` §7 PART-2). Operator gets the data on screen; PDF triggered after ≥1 month of real usage when Sergii knows what fields the PDF needs.
  - **Partner-facing dashboard / login flow** — far-future.
  - **`Partner` entity / agreements table** — explicitly rejected (`partner-payouts.md` §3.2). Free-text `partner_name` is the design.
  - **Automatic settlement creation / month-end reminders** — PART-4 future work.
  - **FX conversion / multi-currency aggregation** — see `profit-definition.md` Q3, deferred.
  - **Settlement workflow states** (draft / approved / paid) — single state. Payment progress is derived from linked PartnerPayment rows.
  - **Cross-shop partner aggregation** ("what did Олег earn across all shops?") — partners are per-shop today.
  - **`Order` / `OrderItem` / `overhead_material_receipts` schema changes.** None needed; verify in OQ.
  - **`finance_service.compute_net_profit`** — UNCHANGED. FIN-1's Net Profit definition stays as-is per `profit-definition.md` §6 ("FIN-1's Net Profit definition stays unchanged").
  - **MCP server endpoints** — partner payouts NOT exposed via MCP. Operator UI only.
  - **Soft delete / deleted_at columns** — accepted limitation per decision #5.
  - **Audit-history rows for settlement / payment create / delete** — NOT in scope. The `created_at` + `created_by_user_id` columns on each entity are the audit. If Sergii later wants a richer audit trail, that's a separate sprint.
  - **Migration of historical (Excel-era) partner data** — out of scope. Sergii's Excel history stays in Excel; PART-1 records future settlements forward from sprint date.
  - **Sender / customer phone normalization** — already shipped in NP-ROBUSTNESS-1, untouched.

### Open questions for the planner

CC must answer each in the plan with cited grep evidence (file:line refs).

1. **`Order` and `OrderItem` column verification.** Grep `backend/models/order.py` (or wherever Order is defined) and confirm exact column names + types for: `currency`, `total_price`, `platform_fee`, `shipping_np_cost`, `computed_production_cost`, `production_cost`, `status`, `shipped_at`, `ordered_at`. Grep `backend/models/order_item.py` for: `quantity`, `unit_price`, `order_id`. State the verified names in the plan; if any differ (e.g. `qty` instead of `quantity`), all SQL sketches in `partner-payouts.md` and the rules above must be patched accordingly.

2. **`overhead_material_receipts` table verification.** Grep `backend/models/` for the OverheadMaterialReceipt model. Confirm columns: `shop_id`, `total_cost`, and the **date column used for period filtering**. The design doc uses `received_at` provisionally — verify against the actual model. If the actual column is named `receipt_date` / `created_at` / something else, state the corrected name. This affects the `net_profit_product_only` SQL in rule #7.

3. **Existing `compute_net_profit` helper signature + currency grouping pattern.** Read `backend/services/finance_service.py`. Locate `compute_net_profit` (or equivalent name). State its signature, return type, and how it groups by currency. The new `compute_net_profit_product_only` must mirror this shape exactly so `partner_payout_service` can swap between them cleanly. If `compute_net_profit` is structured as one big query rather than composable helpers, decide whether to extract the per-currency-skeleton into a private helper now (reduces duplication for the product-only variant) OR copy-modify (simpler but duplicative).

4. **Decimal precision convention.** Grep `Numeric(` in `backend/models/`. Confirm the project uses `Numeric(precision, scale)` for money columns (typical: `Numeric(12, 2)` for amounts, `Numeric(5, 2)` for percentages). State the chosen precision for `base_amount`, `computed_amount`, `percent`, `amount` (payments).

5. **Existing role-gating helper.** Grep for the dependency function used in FIN-1 / MAT-5 routers to restrict to OWNER + MANAGER. Likely named `require_owner_or_manager`, `current_active_user_with_role(...)`, or similar. State the exact helper to reuse for PART-1's router.

6. **Autocomplete component pattern.** Grep `frontend/src/components/` for existing autocomplete-input components. Is there a reusable `<AutocompleteInput>` / `<ComboBox>` / similar? If yes, reuse for partner_name field. If not, decide: roll new (small simple component) OR use a third-party (check `package.json` for existing dependencies like `cmdk`, `headlessui`, `radix-ui` that might offer one). State the decision with rationale.

7. **KPI grid structure on `/shops/{id}/finance`.** Read the existing FIN-1 page component. Identify how KPI cards are composed (one component per metric? a shared `<KpiCard>` primitive?). State where `<ShippingNetKpi>` slots in. Confirm the grid handles N+1 cards layout-wise (no hardcoded 5-column grid that breaks at 6).

8. **`compute_net_profit_product_only` SQL plan.** Show in the plan the **actual SQL** (not pseudo) that will be generated, including how the JOIN to `order_items` and `overhead_material_receipts` is structured. Specifically address: (a) is the overhead JOIN currency-aware? Overhead is per shop, but shop currency is in `orders`, so the overhead amount gets subtracted from the per-currency aggregate — does the existing FIN-1 query already handle this correctly? Confirm with `compute_net_profit`'s current SQL. (b) Do we run two queries (items+fees per currency, overhead separately) then combine in Python, or one big CTE? Pick consistent with FIN-1's existing pattern.

9. **Currency-aware overhead in mixed-currency shops.** If a shop has both UAH and USD orders in a period, but overhead is recorded in only one currency (UAH typically — materials are local), how is overhead allocated across currencies in FIN-1's Net Profit today? State the answer from FIN-1's existing code. The new `net_profit_product_only` must follow the same allocation rule for consistency. If FIN-1 simply subtracts overhead from the dominant currency (or always-UAH) row, document that and apply same.

10. **Migration filename convention + autogenerate verification.** Generate the Alembic migration via `alembic revision --autogenerate -m "part1_partner_payouts"`. Verify the autogenerated file detects: both new tables, the new ENUM, all indexes, the CHECK constraints. CHECK constraints frequently need manual addition (Alembic doesn't always autogenerate them). Show the migration diff in the plan and call out anything hand-edited.

### Verification

- **Backend gates:**
  - `cd backend && python -m pytest tests/ -v` — expect ~153 → ~170 passing (+~17 new). CC must record actual current baseline + new total in the closure note.
  - `cd backend && alembic upgrade head` — clean apply on a fresh DB.
  - `cd backend && alembic downgrade -1 && alembic upgrade head` — round-trip works (forward + back + forward).

- **Frontend gates:**
  - `cd frontend && npx tsc --noEmit` — clean.
  - `cd frontend && npm run lint` — clean for touched files.
  - `cd frontend && npm run test` — all new vitest cases pass.

- **Manual smoke (Cowork via browser MCP, after Sergii approves):**
  1. **Pre-flight (Sergii):** ensure a test shop has at least 3-5 SHIPPED orders in the current period across at least 2 partners' expected formulas. KoraKlenu is the natural candidate (operating partner on profit-share). For revenue-share scenario, use Lamamarka Shopify if it has shipped orders, OR temporarily seed test orders.
  2. **Calculate Settlement — profit-share path:**
     - Open `/shops/KoraKlenu/finance`. Verify the Shipping Net KPI card renders (if any shipping economics in period) OR is hidden (if zero).
     - Click `[+ Calculate Settlement]`. Modal opens.
     - Enter partner name "Тест Партнер" (no autocomplete yet — first settlement). Select formula "% of Net Profit (product-only)". Enter percent 50. Period inherits from page.
     - Live preview populates: base_amount (UAH), computed_amount = base × 50%.
     - Check "Save as settlement record" → save. Modal closes. Settlement appears in Settlements table with "Unpaid" badge.
     - Confirm: per-partner balance row shows "Owed X UAH" for "Тест Партнер".
  3. **Calculate Settlement — revenue-share path:**
     - Click `[+ Calculate Settlement]` again. Partner name "Тест Партнер" should now appear in autocomplete suggestions.
     - Select formula "% of Items Revenue minus Platform Fees". Enter percent 25. Same period.
     - Live preview shows a DIFFERENT base_amount (items revenue minus platform fee, no COGS/overhead subtracted).
     - Save. Second settlement appears.
  4. **Record Payment — linked + partial:**
     - On the first settlement row (the profit-share one), click `[+ Record Payment]`. Modal opens pre-filled with partner name + linked settlement.
     - Enter amount = 50% of computed_amount. Today's date. Note: "first half".
     - Save. Modal closes. Payment appears in Payments table linked to that settlement. Settlement row badge updates to orange "Paid X / Y (partial)". Per-partner balance reflects the reduced owed amount.
  5. **Record Payment — unlinked / standalone:**
     - Click top-level `[+ Record Payment]`. Modal opens empty.
     - Enter "Тест Партнер" (autocomplete should now offer it). Leave linked settlement = "(none)". Amount = 100 UAH. Save.
     - Payment appears in ledger with no linked settlement. Per-partner balance decreases by another 100 UAH. Settlement-1 badge UNCHANGED (unlinked payment doesn't affect per-settlement progress).
  6. **Currency-mismatch warning:**
     - For a shop with USD orders (Lamamarka), create a settlement (it'll be USD). Then try to record a payment in UAH against that USD settlement → modal shows orange warning, allows submit. Saved payment appears in ledger but doesn't reduce the USD balance (would create a separate UAH balance row showing overpayment, OR no UAH row at all if no UAH settlements exist — confirm during smoke which happens).
  7. **Negative base banner:**
     - Pick a period where the shop has loss (or temporarily seed one). Open calculator with profit formula. Live preview shows negative `base_amount` and warning banner per rule #16.
  8. **Delete settlement with linked payments:**
     - Click delete on settlement-1 (which has the partial payment linked). Confirmation dialog warns about linked payments. Confirm.
     - Settlement disappears. Payment-1 (formerly linked) still appears in Payments table but now shows "(unlinked)" or "(none)" for the linked-settlement column. Per-partner balance recalculates accordingly.
  9. **Delete payment:**
     - Click delete on payment-2 (unlinked, 100 UAH). Confirm. Payment disappears. Per-partner balance increases by 100 UAH.
  10. **Console clean throughout, no React-Query stale-cache anomalies after any mutation.**

- **Edge-case spot checks (during smoke):**
  - Empty state: a shop with zero settlements — Partner Payouts section shows friendly empty state with `[+ Calculate Settlement]` CTA. Balances summary hidden.
  - DESIGNER role: log in as designer (or hit endpoints with designer token via MCP / Bruno) → 403 on all PART-1 endpoints.
  - Refresh page after creating a settlement → settlement persists, balance persists.

### Workflow

- **Plan mode REQUIRED.** This sprint has 10 OQs and non-trivial decisions (formula SQL shape, overhead currency allocation, KPI grid integration, autocomplete component choice). CC MUST NOT bypass plan mode (NP-ROBUSTNESS-1 deviation precedent — do not repeat).
- The plan MUST:
  - Read `docs/design/partner-payouts.md` v1.1 in full and `docs/design/profit-definition.md` v1.1 §6 specifically.
  - Answer all 10 Open Questions with cited file:line evidence.
  - Show the **actual SQL** for both formulas (rule #7 and rule #8), reflecting verified column names from OQ1+OQ2.
  - Show the `PartnerSettlement` and `PartnerPayment` model definitions (Mapped columns + CHECK constraints + indexes).
  - Show the Alembic migration diff (autogenerated + hand-edits).
  - Show the `get_partner_balances()` implementation sketch — explicitly NOT the naive LEFT JOIN (per rule #11). The plan must demonstrate the correct row-multiplication-free shape.
  - Show the `compute_settlement_payment_progress(settlement_ids)` query.
  - Show the new Pydantic schema definitions for all request/response shapes.
  - Show the new router endpoint signatures with role-gating dependency wired in.
  - List the frontend component file paths (verified or proposed) and the integration point in the existing FIN-1 page component.
  - Confirm out-of-scope files won't be touched.
  - State expected pytest + vitest deltas (numbers, not vague "more tests").
- **No code edits until Sergii approves the plan.**
- After approval: backend models + migration → service layer → router → backend tests → frontend API client + hooks → frontend components → frontend tests → backend pytest → frontend gates → **MANUAL SMOKE via browser MCP per the 10-step scenario above** → commit.
- Commit: `feat(part-1): partner payouts + payments ledger + shipping net kpi`
- Do **NOT** update `implementation_plan.md` or `task.md` post-sprint — Cowork writes those after smoke verification.
- **No Co-Authored-By or Claude trailer** (AI_ONBOARDING.md §9).

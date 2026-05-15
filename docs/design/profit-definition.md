# Profit Definition — Reference Note

**Status:** Living document — 2026-05-15.
**Purpose:** Single source of truth for what "profit" means across the OrderHub system. Specifically referenced by **partner payout calculations** (see `partner-payouts.md`) and the FIN-1 finance dashboard.

**Why this note exists:** "Profit" is the single most-disputed term in small business partnerships (per industry research — see PART-1 design doc §1). Every partner agreement Sergii has uses "profit" without explicit definition. To avoid future "wait, what counts as profit?" conversations with partners, we lock the current definition here and explicitly list questions that may need revisiting.

---

## 1. Current definition (as of 2026-05-15, post-MAT-5 Phase B)

**Net Profit per shop, per period, per currency:**

```
Net Profit = Revenue − COGS − Fees − Allocated Overhead Expenses
```

Where each component is computed by `backend/services/finance_service.py` for the `/api/shops/{id}/finance` endpoint:

| Component | SQL source | Notes |
|---|---|---|
| **Revenue** | `SUM(orders.total_price)` | Includes shipping; NOT items-only. Filters: `status IN ('shipped', 'completed')`, `COALESCE(shipped_at, ordered_at) BETWEEN :start AND :end`, grouped by `currency`. |
| **COGS** | `SUM(COALESCE(orders.computed_production_cost, orders.production_cost, 0))` | Phase B: prefers BOM-computed cost when available (set by MAT-4 consumption hook); falls back to manual `production_cost` for orders without a BOM-equipped product. NULL/missing → 0 contribution. |
| **Fees** | `SUM(COALESCE(orders.platform_fee, 0) + COALESCE(orders.shipping_np_cost, 0))` | Platform fees (Shopify / Etsy commission) plus Nova Poshta shipping cost. Note: Shopify shipping cost (paid by customer) is NOT in `shipping_np_cost`; it's bundled into `total_price` and not separately tracked. |
| **Allocated Overhead Expenses** | `SUM(overhead_material_receipts.total_cost) WHERE shop_id = :shop_id` | Per-shop tagged overhead from MAT-5. Excludes unallocated overhead (workshop-wide expenses on `/dashboard`). |

All four aggregates are per-currency. Net Profit retains per-currency breakdown — no cross-currency aggregation is performed (see Known Limitation #1 below).

## 2. What is NOT in this definition (currently)

- **Operator's own labor cost** — Sergii's time isn't valued against profit. If Sergii decides his hourly rate matters, that's a future feature (would require a new "labor cost" entity or per-order hours tracking).
- **Workshop overhead (unallocated)** — `OverheadMaterialReceipt` rows with `shop_id IS NULL` (workshop-wide expenses Sergii hasn't tagged to specific shops) are visible on `/dashboard` but **NOT subtracted from any single shop's Net Profit**. Sergii does any allocation manually when calculating partner payouts (per MAT-5 settled decision #2 of design `materials-warehouse.md`).
- **Tax** — Sergii works on simplified taxation system. Tax provisions are NOT subtracted from Net Profit.
- **Reserves / depreciation** — no equipment depreciation, no cash reserve accounting in OrderHub.
- **FX gains/losses** — orders in USD stay in USD. No realized/unrealized currency revaluation.

## 3. Open questions to revisit

These are intentional gaps. Each may need a decision when triggered by operational reality (e.g. partner asks for a different definition; new revenue stream emerges; tax system changes).

### Q1 — COGS source preference and partner agreement transparency

**Issue:** After MAT-4, COGS prefers `computed_production_cost` (BOM-driven) over `production_cost` (manual). For an order with both, `computed_production_cost` wins. For a partner who agreed to "% of profit" before BOM was set up, the COGS number they see today may differ from what they would have seen 3 months ago.

**Question:** Should partners be informed when COGS source changes for a shop? Or is the post-Phase-B Net Profit just "the new normal" they accept?

**When to revisit:** Next time a partner questions a settlement amount.

### Q2 — Allocated overhead should be included for ALL partners?

**Issue:** Per current MAT-5 implementation, Allocated Overhead is part of Net Profit (subtracted). For a partner with "% of profit" agreement signed BEFORE overhead tracking existed, this means their share is now smaller than it would have been. Counter-argument: overhead is a real cost; sharing profit should always factor it in.

**Question:** Should partners be able to opt out of overhead inclusion in their profit share? E.g. "% of pre-overhead profit"?

**When to revisit:** If partner formally pushes back on the lower amounts after MAT-5 / PART-1 ships.

### Q3 — Multi-currency partner share

**Issue:** Lamamarka Shopify is USD; partners may be paid in UAH. Today Sergii converts manually at payment time using current FX rate. There's no record in OrderHub of what conversion rate was used, and the settlement record stores USD amount only.

**Question:** Should OrderHub track the FX rate used for each settlement? Auto-pull from NBU? Operator enters? Or stays manual outside the system?

**When to revisit:** If FX volatility makes manual conversion error-prone, or if partner asks for UAH-equivalent records.

### Q4 — Negative Net Profit handling

**Issue:** A shop can have Net Profit < 0 in a period (overhead exceeds revenue, or COGS exceeds revenue if BOM-computed costs are high). For "% of profit" partner, a 50% share of -1000 UAH is -500 UAH. Does the partner share the loss? Or are they sheltered?

**Current behavior (PART-1):** Settlement record shows the negative computed amount as-is. Operator interprets — typically chooses to log a 0 settlement instead, or doesn't save the calculation that period.

**Question:** Should OrderHub auto-clamp negative shares to 0? Or surface a warning at calculator time?

**When to revisit:** First time Sergii actually shows a partner a negative settlement screen.

### Q5 — Manual production_cost fallback as data quality signal

**Issue:** FIN-1's diagnostic badge already counts orders missing both manual and computed cost. But for orders where manual `production_cost` is the source (no BOM), partners trust an operator's manual number — which may be inaccurate.

**Question:** Should partner settlements show how many orders in the period used computed-vs-manual COGS, so partner can ask follow-up if needed?

**When to revisit:** When BOM coverage approaches 90%+ (Phase C cutover prerequisite per `materials-warehouse.md` §6.2).

## 4. How to update this document

When any of the open questions above gets resolved (typically through a partner conversation or a new feature design), update the definition in §1 and move the resolved question to a "Resolved decisions" section at the bottom. Keep the audit trail.

The single most important rule: **never silently change the Net Profit formula without updating this doc**. Partner trust depends on the definition staying stable or changing visibly.

## 5. References

- `docs/design/materials-warehouse.md` v1.1 (Phase 3 design) — full Materials epic context
- `docs/design/partner-payouts.md` — PART-1 design (uses Net Profit definition for `net_profit` formula)
- `implementation_plan.md` FIN-1 closure entry — original Net Profit formula introduction
- `implementation_plan.md` MAT-5 closure entry — Phase B COGS cutover (`COALESCE(computed, manual, 0)`)
- `backend/services/finance_service.py` — actual implementation

# Profit Definition — Reference Note

**Status:** Living document — v1.1 — 2026-05-15.
**Purpose:** Single source of truth for what "profit" means across the OrderHub system. Specifically referenced by **partner payout calculations** (see `partner-payouts.md`) and the FIN-1 finance dashboard.

**Why this note exists:** "Profit" is the single most-disputed term in small business partnerships (per industry research — see PART-1 design doc §1). Every partner agreement Sergii has uses "profit" without explicit definition. To avoid future "wait, what counts as profit?" conversations with partners, we lock the current definition here and explicitly list questions that may need revisiting.

**Changelog:**
- **v1.1 (2026-05-15):** Q1-Q5 resolved per Sergii's discovery answers. Added §6 documenting the **partner formula deviation** — partners use `net_profit_product_only` (excludes shipping economics), not FIN-1's `Net Profit` (which includes shipping). FIN-1 itself unchanged.
- **v1.0 (2026-05-15):** Initial draft, 5 open questions surfaced.

---

## 1. Current FIN-1 Net Profit definition (as of 2026-05-15, post-MAT-5 Phase B)

**Net Profit per shop, per period, per currency** — as displayed on `/shops/{id}/finance`:

```
Net Profit = Revenue − COGS − Fees − Allocated Overhead Expenses
```

Where each component is computed by `backend/services/finance_service.py`:

| Component | SQL source | Notes |
|---|---|---|
| **Revenue** | `SUM(orders.total_price)` | **Includes shipping**; `total_price` is the order's gross total. Filters: `status IN ('shipped', 'completed')`, `COALESCE(shipped_at, ordered_at) BETWEEN :start AND :end`, grouped by `currency`. |
| **COGS** | `SUM(COALESCE(orders.computed_production_cost, orders.production_cost, 0))` | Phase B: prefers BOM-computed cost (set by MAT-4 consumption hook); falls back to manual `production_cost`. NULL/missing → 0 contribution. |
| **Fees** | `SUM(COALESCE(orders.platform_fee, 0) + COALESCE(orders.shipping_np_cost, 0))` | Platform fees (Shopify/Etsy commission) + Nova Poshta shipping cost. **Shipping is netted via Fees.** |
| **Allocated Overhead** | `SUM(overhead_material_receipts.total_cost) WHERE shop_id = :shop_id` | Per-shop tagged overhead from MAT-5. Excludes unallocated overhead. |

All four aggregates are per-currency. Net Profit retains per-currency breakdown — no cross-currency aggregation.

## 2. What FIN-1 Net Profit does NOT include

- **Operator's own labor cost** — Sergii's time isn't valued.
- **Workshop overhead (unallocated)** — `OverheadMaterialReceipt.shop_id IS NULL` rows live on `/dashboard`; **NOT subtracted from any shop's Net Profit**. Sergii does any allocation manually.
- **Tax** — simplified taxation system; no tax provisions.
- **Reserves / depreciation** — no equipment depreciation, no cash reserve accounting.
- **FX gains/losses** — orders in USD stay in USD; no realized/unrealized FX revaluation.

## 3. Resolved questions (from 2026-05-15 discovery)

### Q1 (RESOLVED) — COGS source transparency for partners

**Original concern:** Should partners be told when COGS source switched from manual to BOM-computed?

**Sergii's answer (2026-05-15):** *"Працюємо на довірі, питань не буде."* No proactive disclosure. If a partner asks why their share changed in a given month, operator explains then.

**Decision:** No technical change required. Documented as "operator handles via direct conversation if asked".

### Q2 (RESOLVED) — Allocated overhead in partner profit base

**Original concern:** Should partners share overhead expenses, or only "pre-overhead" profit?

**Sergii's answer (2026-05-15):** *"Витрати на ці розхідники мінімальні, теж не проблема, поки хай так буде як є, profit після всіх витрат."* Allocated overhead stays subtracted (current behavior). Risk of dispute is low because the overhead amounts are small.

**Decision:** No technical change. Allocated overhead remains in Net Profit calculation. Revisit if overhead amounts grow significantly OR a partner formally challenges the inclusion.

### Q3 (RESOLVED) — FX tracking for cross-currency settlements

**Original concern:** Should OrderHub track FX rate at payment time, or rely on operator's manual conversion?

**Sergii's answer (2026-05-15):** *"Рахую на момент виплати. Це звісно не коректно глобально, але на моїх обертах це допустимо, далі за потреби пофіксимо."* Manual conversion at payment time, no FX rate stored. Acceptable at current volume; revisit if FX volatility makes manual error-prone.

**Decision:** PART-1 settlements stay in shop currency (no FX). Operator manually computes UAH equivalent at payment time. If revisited, see PART-2 / PART-3 future work.

### Q4 (RESOLVED) — Negative Net Profit handling

**Original concern:** If shop has loss in a period, does partner share the loss (negative settlement) or get 0?

**Sergii's answer (2026-05-15):** *"В основному я беру на себе ризики і перекриваю касові розриви за потреби. Але намагаюсь тримати баланс і не доводжу до такого."* **Sergii absorbs losses himself; partners get 0 (or no settlement created) in negative-profit months.** Operator manages this via discipline (avoiding loss months) rather than passing it to partners.

**Decision:** PART-1 calculator displays the negative computed amount as informational ("base is negative; partner share would be -X UAH"), but operator typically doesn't save the settlement OR saves with `computed_amount = 0` and a note. UI surfaces an info banner when base is negative warning operator before save. See `partner-payouts.md` §6.4.

### Q5 (DEFERRED) — BOM-vs-manual COGS transparency in partner settlements

**Original concern:** Should partner settlements show "X of Y orders used BOM cost" so partner can ask follow-up?

**Sergii's answer (2026-05-15):** *"Поки partner won't care. Але потім до цього повернемось. Бо важливе питання."* Defer to a later iteration. Will revisit when first partner asks about COGS methodology, OR when BOM coverage approaches Phase C cutover (~90% of catalog).

**Decision:** Not in PART-1 scope. May land as a small UX enhancement in PART-2 or later.

## 4. Resolved internal definitions

These are no longer "open questions" — they're settled facts the system implements.

- "Profit" in FIN-1 context = the four-component formula in §1.
- "Profit" in **partner-share** context = `net_profit_product_only` formula (see §6 below + `partner-payouts.md` §4).
- COGS preference: COALESCE(computed_from_BOM, manual, 0) per row, then SUM (Phase B semantics).
- Shipping is currently part of FIN-1's Fees (subtracted), but **excluded from partner profit calculations** (see §6).

## 5. What's still open (not currently triggered)

- **FX conversion in settlement records** — see Q3 above; deferred.
- **Tax provisions** — out of scope until Sergii migrates off simplified taxation system.
- **Operator labor cost** — out of scope; Sergii's time isn't valued today.
- **Workshop overhead pro-rata allocation to shops** — currently manual; could be auto-allocated by revenue/order-count weighting if the unallocated card grows persistently.

## 6. Partner formula deviation — why partners use a different "profit"

**Important distinction surfaced during PART-1 discovery:**

For partner share calculations, Sergii's mental model treats **shipping as a transit pass-through**, not as part of product economics:

> *"Доставка завжди йде транзитом — ні я, ні партнери з неї не маємо нічого. А якщо брати НП то взагалі клієнт платить при отриманні."*

(Shipping always passes through — neither I nor partners profit from it. For Nova Poshta, the customer pays directly on pickup.)

**Implication:** if FIN-1's Net Profit (which includes shipping income/costs) were used as the partner-share base, partners would inadvertently share in any positive shipping margin OR get penalized by negative shipping margin — **even though they contributed nothing to shipping logistics**.

**Resolution:** PART-1 uses a partner-specific formula `net_profit_product_only` that explicitly excludes shipping economics:

```
net_profit_product_only =
    items_revenue                                            -- SUM(OrderItem.qty × unit_price)
  − COGS                                                     -- COALESCE(computed, manual, 0)
  − non_shipping_fees                                        -- platform_fee only (NOT shipping_np_cost)
  − allocated_overhead                                       -- per-shop tagged overhead
```

**Two key differences from FIN-1's Net Profit:**

1. Revenue uses `SUM(OrderItem.qty × unit_price)` (items only, no shipping component) instead of `SUM(total_price)`.
2. Fees include `platform_fee` only, NOT `shipping_np_cost`.

**FIN-1's Net Profit definition stays unchanged** — it still includes shipping economics for the operator's overall view (e.g. "did I profit on shipping margin?"). PART-1 ships a new informational `Shipping Net` KPI card on `/shops/{id}/finance` showing the shipping margin separately, so operator can see both "product profit" (what partners share) and "shipping margin" (operator-only, e.g. small markup or accidental loss on logistics) at a glance.

**Why two definitions instead of one:**

- Changing FIN-1 globally would silently shift Net Profit numbers across the dashboard and historical comparisons (post-MAT-5 just shipped — too disruptive).
- Partner-specific formula gives precise control without touching FIN-1's contracts.
- Operator's view (FIN-1) and partner's view (PART-1) are answering different questions: "how is the shop doing overall?" vs. "what does this person get for their contribution to product creation?"

This deviation is **intentional**, **documented**, and **stable** until either FIN-1 or PART-1 design evolves explicitly.

## 7. How to update this document

When any open question gets resolved (typically through a partner conversation or a new feature design), update §3 and move the resolved question to a "Resolved decisions" subsection. Keep the audit trail; never silently change the formula without updating this doc.

The single most important rule: **partner trust depends on the definition staying stable or changing visibly**. If we ever rebase partner formulas on different math, document the change AND the operational reason here, so future Sergii (or future Cowork) understands why.

## 8. References

- `docs/design/materials-warehouse.md` v1.1 (Phase 3 design) — full Materials epic context
- `docs/design/partner-payouts.md` v1.1 — PART-1 design (uses `net_profit_product_only` formula for profit-share partners)
- `implementation_plan.md` FIN-1 closure entry — original Net Profit formula introduction
- `implementation_plan.md` MAT-5 closure entry — Phase B COGS cutover (`COALESCE(computed, manual, 0)`)
- `backend/services/finance_service.py` — actual FIN-1 implementation

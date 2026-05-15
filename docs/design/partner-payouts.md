# Partner Payouts — Design Document

**Status:** Draft 1.1 — 2026-05-15
**Phase:** Phase 2 of Finance epic (Phase 3 Materials Warehouse closed end-to-end at MAT-5)
**Authors:** Sergii (operator) + Cowork (planning)
**Review state:** Ship-ready pending Sergii sign-off. Will translate to `task.md` (PART-1 monoblock) next.

**Changelog:**
- **v1.1 (2026-05-15):** 6 new decisions from second-pass discovery integrated. Added `PartnerPayment` entity for tracking actual money movements (separate from settlements). Replaced `net_profit` formula with `net_profit_product_only` (drops shipping economics from partner share base — see `profit-definition.md` §6). Added partner balance computation (`SUM(settlements) − SUM(payments)`). Added Shipping Net KPI card on FIN-1 (informational, operator-only). PART-1 confirmed as monoblock sprint. All four profit-share partners migrate from old `net_profit` to `net_profit_product_only` — no partner sees a worse share because shipping margin was previously bundled in.
- **v1.0 (2026-05-15):** Initial draft. 11 settled decisions, single `PartnerSettlement` entity, two formulas (`revenue_items_minus_fees` + `net_profit`).

---

## 1. Context

OrderHub's primary motivation from day 1 was **Sergii's frustration with Excel-based partner payout tracking**. Each shop has 1–2 partners with different deal structures — some on % of revenue, some on % of profit, sometimes mixed within one shop. Today partners ask "what's my share for May?" and Sergii recomputes from scratch in Excel, with the implicit risk of inconsistency between conversations. Worse: partners often get **partial payments** (not always the full settlement at once), and tracking "how much do I still owe Олег from May?" lives in Sergii's head + WhatsApp threads.

Phase 3 (Materials Warehouse, 5 sprints, commits MAT-1..5) shipped reliable per-shop financial primitives — Net Profit per shop per period per currency, with COGS sourced from BOM-computed costs (or manual fallback) and overhead expenses subtracted. With these primitives in place, **PART-1 builds the partner payout layer on top**, including a payment-tracking ledger so balances are first-class.

### 1.1 Sergii's actual partner contracts (2026-05-15)

Captured from discovery conversation:

| Shop | Partner role | Formula |
|---|---|---|
| Lamamarka Shopify | Creative / ideas / traffic | **25% of revenue** (items only, minus Shopify platform fees, NO shipping) |
| Lamamarka Shopify | Mockups + foreign-shipment paperwork | **15% of profit** (product-only, no shipping) |
| Lamamarka Etsy | Generic partner | **10% of profit** (product-only, no shipping) |
| Lamamarka Etsy | Mockups + tracking | **15% of profit** (product-only, no shipping) |
| KoraKlenu | Operating partner | **50% of profit** (product-only, no shipping) |

Two formula categories cover all of Sergii's current arrangements:
- **One partner on revenue-share** with shop-specific basis (items minus fees, excluding shipping)
- **Four partners on profit-share** with consistent basis (`net_profit_product_only` — explicitly excludes shipping economics; see `profit-definition.md` §6)

### 1.2 Industry research findings (concise)

Web research (2026-05-15, see this discovery's chat history for full citations) surfaced three relevant patterns:

1. **~80% of small business partnerships fail within 5 years; money disagreements are the #1 cause** — most disputes trace to ambiguous definition of "profit". Locked in `profit-definition.md` and explicitly defined here.
2. **Revenue-share is structurally riskier for the operator**: partner gets their cut regardless of whether the shop is profitable. Industry consensus prefers profit-share for partner alignment. Sergii's Lamamarka Shopify creative on revenue-share is the higher-risk arrangement; documented but not flagged for change.
3. **Existing Shopify/Etsy partner-tracking apps all use configured-partner-records pattern** (CollabPay, Revenue Split, etc.). I did NOT find an "ad-hoc calculator + settlements log + payments ledger" pattern in market tools. Sergii's preferred design (no Partner entity) is uncommon but defensible for his solo-operator, low-volume, varying-partner-arrangement reality.

## 2. Settled decisions (from 2026-05-15 discovery, both passes)

| # | Decision | Rationale |
|---|---|---|
| 1 | **No Partner entity** — `partner_name` is free text on each settlement and each payment | Per Sergii: partner relationships evolve; new shops bring new partners; explicit Partner records would force setup-and-archive ceremony for every arrangement change. Maximum flexibility. Cost: typo risk on partner names (mitigated by autocomplete dropdown). |
| 2 | **Two formula types** in PART-1 enum: `revenue_items_minus_fees` and `net_profit_product_only` | These cover all five of Sergii's current contracts. A speculative `revenue_total` option (% of gross sales including shipping) was considered and dropped — no current partner uses it, YAGNI. Future formulas added via Alembic `ALTER TYPE ADD VALUE` if a new contract requires it. |
| 3 | **Snapshot pattern: base_amount and computed_amount frozen on creation** | If FIN-1 numbers change retroactively (e.g. a new receipt added in June changes May's COGS), already-saved settlements DO NOT recompute. Each settlement is "this is what I computed and told the partner that day". Same audit-integrity pattern as `MaterialMovement.unit_cost_at_movement` from MAT-2. |
| 4 | **Settlements immutable + delete-and-recreate** (no edit) | Settlement records cannot be edited after creation. Operator can delete and re-save with correct values. Preserves audit trail; if Sergii saved 25% then realized it should be 20%, the deletion-recreation pattern shows both attempts in the operator's history (delete logged via audit; recreation is a new row). |
| 5 | **Hard delete is acceptable for v1** | No regulatory audit requirement (simplified taxation system per Sergii). If Sergii later wants soft-delete for traceability, `deleted_at` column added without migration headache. |
| 6 | **Settlement records stay in shop currency, no FX conversion** | Lamamarka USD partner shares store as USD; Sergii converts manually at payment time using whatever FX rate he chooses. Same workflow as today's Excel approach. No FX rate stored in PART-1; if needed, Q3 in `profit-definition.md`. |
| 7 | **Profit-share base = `net_profit_product_only`** (NOT FIN-1's full Net Profit) | All four profit-share partners use a partner-specific formula that **excludes shipping economics** from the base. Per Sergii: *"Доставка завжди йде транзитом — ні я, ні партнери з неї не маємо нічого."* See `profit-definition.md` §6 for the full deviation rationale. FIN-1's Net Profit definition stays unchanged for operator's overall view. |
| 8 | **`revenue_items_minus_fees` formula = `SUM(OrderItem.quantity × OrderItem.unit_price) − SUM(Order.platform_fee)`** | Per Sergii: revenue basis is items only (no shipping), minus Shopify/Etsy platform fee. `total_price` includes shipping (verified on Heavy Mushroom Keychain: item 14.99 + shipping 8 = total 22.99) so it's the wrong basis. JOIN order_items table to get item-level subtotal. Filters mirror Net Profit: `status IN ('shipped', 'completed')` + period range on `COALESCE(shipped_at, ordered_at)`. |
| 9 | **PDF generation deferred to PART-2** | Sergii confirmed: "Якщо недорого зробити генерацію PDF давай зробимо". Defer until PART-1 calculator + settlements log + payments ledger are in use for ≥1 month — Sergii will have learned what fields he actually wants in the PDF (signature blocks? line-item breakdowns? logo? balance summary?). Designing PDF prematurely = waste. |
| 10 | **Independent partners on same shop** — each partner's share computed from the original FIN-1 numbers, not from "what's left after another partner's share" | Per Sergii: "з оригінального profit беру 15% незалежно". KoraKlenu 50% partner doesn't compound from a "post-partner" profit; Lamamarka Shopify 15%-profit partner gets 15% of original `net_profit_product_only`, not 15% of (profit − 25% creative cut). Order of saving settlements doesn't matter. |
| 11 | **Self-share is implied, not tracked** (Sergii doesn't create settlements for himself) | KoraKlenu = 50/50; Sergii creates partner's 50% settlement; his own 50% is whatever's left after partner settlements. No "self-settlement" record. Cleaner audit log. |
| 12 | **Separate `PartnerPayment` entity for tracking money movements** | Per Sergii (Q1.1): partial payments happen routinely — partner gets 1,000 UAH on the 5th, another 1,500 UAH on the 20th, against a settlement of 2,450 UAH. A single `paid_at` field on PartnerSettlement can't model this. Payments live in their own table; balance is computed `SUM(settlements) − SUM(payments)` per partner per shop. |
| 13 | **Payments may be linked to a specific settlement OR unlinked** (`settlement_id NULLABLE`) | Per Sergii (Q1.2 recommended option): typical payment is "paying down May 2026 settlement" → link it. Sometimes payment is a standalone advance, OR clears multiple settlements at once → leave unlinked. Linked payments enable per-settlement progress display ("settled / partially paid / paid in full"); unlinked payments still count toward overall balance. |
| 14 | **Payment immutable + delete-and-recreate** (mirrors settlement) | Same audit-integrity reasoning as decision #4. If amount or date is wrong, delete the payment row and create a new one. |
| 15 | **Balance computation per partner per shop per currency** = `SUM(settlements.computed_amount) − SUM(payments.amount)` | Positive balance = "operator owes partner this much". Zero = "fully settled". Negative = "operator overpaid" (rare; treated as advance against next month). Computed live; not materialized. |
| 16 | **Shipping Net KPI on FIN-1** (informational only, operator-eyes) | Per Sergii (Q2.3): *"Додаємо, інколи варто глянути скільки трачено на доставку."* New small KPI card on `/shops/{id}/finance` showing `shipping_revenue − shipping_cost` for the period. Auto-hides when both components are 0 (Etsy shops where customers pay NP directly). Helps operator notice if shipping is silently bleeding margin. |
| 17 | **All four profit-share partners migrate from FIN-1 Net Profit to `net_profit_product_only`** | Per Sergii (Q2.2): *"конвертувати їх на net_profit_product_only. Тобто ціна доставки ніяк не вплине на прибуток партнерів, так?"* — yes, exactly. No partner sees a worse share because the previous formula included shipping economics that nobody contributed to. This is a quiet improvement, not a renegotiation. New formula applies to all settlements created from PART-1 forward; old (Excel-era) settlements unaffected because they live outside OrderHub. |

## 3. Domain model

### 3.1 `PartnerSettlement` entity

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `shop_id` | UUID | FK → Shop, NOT NULL, `ondelete='RESTRICT'` | Don't accidentally drop settlement history on shop delete (use shop archive instead). |
| `partner_name` | str(200) | NOT NULL | Free text. NO Partner entity. |
| `formula_type` | ENUM | NOT NULL | `revenue_items_minus_fees` \| `net_profit_product_only` (Postgres ENUM `partner_settlement_formula`). |
| `percent` | Decimal(5,2) | NOT NULL, > 0 AND ≤ 100 | E.g. 25.00 for 25%. CHECK constraint at DB level. |
| `period_start` | date | NOT NULL | Inclusive. |
| `period_end` | date | NOT NULL | Inclusive. CHECK constraint: `period_end >= period_start`. |
| `base_amount` | Decimal(12,2) | NOT NULL | **Snapshot.** The total amount the formula was applied to (e.g. SUM(items - fees) for `revenue_items_minus_fees`, or `net_profit_product_only` for the profit-share formula). Frozen at creation time. |
| `base_currency` | str(3) | NOT NULL | ISO 4217 code. Whatever currency the base aggregation produced (typically the shop's primary currency). |
| `computed_amount` | Decimal(12,2) | NOT NULL | **Snapshot.** Calculated as `base_amount × percent / 100`. Can be negative if `base_amount` is negative. |
| `notes` | text | NULL | Optional operator memo (e.g. "verified with partner via WhatsApp Apr 15"). |
| `created_at` | datetime(tz) | NOT NULL, default `now()` | |
| `created_by_user_id` | UUID | FK → User, NOT NULL, `ondelete='RESTRICT'` | Audit; never delete user that created settlements. |

Indexes:
- `(shop_id, period_start)` — primary lookup pattern (list settlements for shop, sorted by period DESC)
- `(partner_name, shop_id)` — autocomplete dropdown source + cross-shop partner lookup if ever needed

No `relationship()` back to `Shop` or `User` (lightweight read-only references; service queries explicit JOINs if needed). PartnerPayment relationship is one-to-many via `payments.settlement_id` FK (see §3.4).

### 3.2 Why no Partner entity (rationale)

**Considered and rejected:**

```python
class Partner(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "partners"
    name: Mapped[str]
    contact_info: Mapped[str | None]
    is_active: Mapped[bool]
    ...

class PartnerAgreement(Base, ...):
    partner_id: FK
    shop_id: FK
    formula_type: ENUM
    percent: Decimal
    effective_from: date
    effective_to: date | None
    ...

class PartnerSettlement(...):
    agreement_id: FK PartnerAgreement
    ...
```

This is the "industry-standard" shape (CollabPay-style). **Why we don't ship it for Sergii:**

- **Setup cost per partner is wasted on his volume.** 5 partners across 4 shops = 5 PartnerAgreement records to create. Onboarding/maintenance overhead per partner.
- **Sergii's partner arrangements evolve.** Operating partner today; maybe two next year; maybe none if Sergii goes solo on a shop. Hard to model as immutable agreements vs amendable contracts vs versioned.
- **No regulatory need.** Sergii on simplified taxation, no audit obligation for formal contract records.
- **Free-text partner_name is enough** for his actual workflow — partners are colleagues he knows personally; he doesn't need a contact-management database.

**What we'd gain by adding it later** (in some far future):
- Automatic settlement triggering (e.g. "month closed, compute everyone's share automatically")
- Partner-facing dashboard ("partner logs in, sees own settlements")
- Multi-shop aggregation per partner ("Олег earned X total across both shops in 2026")

None of these are operational asks today. If Sergii later wants them, **migrating from `partner_name` (string) to `partner_id` (FK)** is a one-time data cleanup: deduplicate strings on both `partner_settlements` and `partner_payments`, create Partner records, backfill FK. Manageable.

### 3.3 Additive changes to existing entities

**None.** Phase B (MAT-5) already added `Order.computed_production_cost`. All other components of the partner formulas use existing columns. **No schema changes outside the two new tables (`partner_settlements`, `partner_payments`).**

### 3.4 `PartnerPayment` entity

Tracks actual money movements out to partners. Separate from settlements because:
- One settlement can be paid in multiple installments (Sergii: *"Так буває"*).
- A payment can be unlinked (advance, or clears several settlements at once).
- Payment date ≠ settlement creation date; both matter independently.

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `shop_id` | UUID | FK → Shop, NOT NULL, `ondelete='RESTRICT'` | Same protection as settlements. |
| `partner_name` | str(200) | NOT NULL | Free text. Must match an existing settlement's `partner_name` for balance to make sense — UI uses the same autocomplete source as settlements. Not enforced at DB level (intentional flexibility). |
| `settlement_id` | UUID | FK → PartnerSettlement, NULLABLE, `ondelete='SET NULL'` | Optional link. If set, payment is "paying down THIS settlement". If NULL, payment counts toward overall partner balance only. `SET NULL` so deleting a settlement leaves payment intact (operator can re-link or leave unlinked). |
| `amount` | Decimal(12,2) | NOT NULL, > 0 | Always positive. Refunds/clawbacks (rare) handled by recording a negative settlement, not a negative payment — keeps payment ledger semantically "money out". |
| `currency` | str(3) | NOT NULL | ISO 4217. Should match the linked settlement's `base_currency` if linked; UI warns on mismatch but doesn't block (operator knows their FX situation). |
| `paid_at` | date | NOT NULL | The date money actually moved (operator's record of when, not when it was entered into the system). |
| `notes` | text | NULL | Optional memo: "Privatbank transfer", "cash на руки 15.05", "first half of May settlement", etc. |
| `created_at` | datetime(tz) | NOT NULL, default `now()` | |
| `created_by_user_id` | UUID | FK → User, NOT NULL, `ondelete='RESTRICT'` | |

Indexes:
- `(shop_id, paid_at)` — primary lookup (payments log sorted by date)
- `(partner_name, shop_id)` — balance-per-partner aggregation
- `(settlement_id)` — fast lookup of payments for a given settlement (badge / progress display)

### 3.5 Partner balance computation

Computed live, not materialized. Per `(shop_id, partner_name, currency)`:

```sql
SELECT
    settlements.partner_name,
    settlements.base_currency AS currency,
    COALESCE(SUM(settlements.computed_amount), 0) AS total_settled,
    COALESCE(SUM(payments.amount), 0) AS total_paid,
    COALESCE(SUM(settlements.computed_amount), 0)
        - COALESCE(SUM(payments.amount), 0) AS balance_owed
FROM partner_settlements settlements
LEFT JOIN partner_payments payments
    ON payments.shop_id = settlements.shop_id
   AND payments.partner_name = settlements.partner_name
   AND payments.currency = settlements.base_currency
WHERE settlements.shop_id = :shop_id
GROUP BY settlements.partner_name, settlements.base_currency;
```

**Note on the JOIN shape:** the SQL above is illustrative — the actual implementation should compute `total_settled` and `total_paid` separately (two simple aggregates) then combine in Python, because a naive LEFT JOIN multiplies rows when a partner has both N settlements and M payments. PART-1 task spec will pin the exact query shape during planning.

**Interpretation:**
- `balance_owed > 0`: operator owes partner this much
- `balance_owed = 0`: fully settled
- `balance_owed < 0`: operator has overpaid (treated as advance against next settlement)

**Per-settlement progress** (linked payments only): each `PartnerSettlement` row in the UI shows a small badge like "Paid 1,000 / 2,450 UAH" computed from `SUM(payments.amount WHERE settlement_id = settlement.id)`. Unlinked payments contribute to overall balance but not to per-settlement progress.

## 4. Formulas

Both formulas compute a per-currency `base_amount` for a given shop + period. The settlement's `computed_amount` is `base_amount × percent / 100`.

### 4.1 `revenue_items_minus_fees`

**Purpose:** Sergii's Lamamarka Shopify creative partner case. Revenue from item sales minus platform fees (Shopify commission), excluding shipping.

**SQL:**

```sql
SELECT
    o.currency,
    SUM(oi.quantity * oi.unit_price) - COALESCE(SUM(o.platform_fee), 0) AS base_amount
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.shop_id = :shop_id
  AND o.status IN ('shipped', 'completed')
  AND COALESCE(o.shipped_at, o.ordered_at) BETWEEN :start AND :end
GROUP BY o.currency;
```

**Why this works:**
- `Order.total_price` includes shipping (verified via Heavy Mushroom Keychain example: item_unit_price 14.99 × qty 1 = 14.99 items_subtotal; total_price 22.99 = items + 8 shipping). So `total_price` is the wrong basis.
- `OrderItem.quantity × unit_price` is item-level subtotal. SUM across all items in matched orders = items revenue.
- `Order.platform_fee` is the Shopify/Etsy commission (existing FIN-1 Fees component).
- Subtraction at the SQL level: `SUM(items) - SUM(fees)`. Equivalent to operator's mental model.

**Caveat on the GROUP BY shape:** if a shop ever has orders in multiple currencies in one period, the SUM-then-subtract pattern at the row level is correct per currency. The actual implementation should validate that `platform_fee.currency` matches `order.currency` per row — already an invariant in FIN-1, but worth re-verifying during PART-1 task planning.

**Negative base handling:** if platform fees somehow exceed items (e.g. high-fee Etsy order combined with a refund), `base_amount` goes negative. Settlement stored as-is; computed_amount also negative. Operator interprets — see §6 Edge Cases.

### 4.2 `net_profit_product_only`

**Purpose:** All four profit-share partners. Explicitly excludes shipping economics from the base — partners contribute nothing to shipping logistics, so they neither benefit from positive shipping margin nor get penalized by negative shipping margin.

**Formula** (per `profit-definition.md` §6):

```
net_profit_product_only =
    items_revenue                                            -- SUM(OrderItem.qty × unit_price)
  − COGS                                                     -- COALESCE(computed, manual, 0)
  − non_shipping_fees                                        -- platform_fee only (NOT shipping_np_cost)
  − allocated_overhead                                       -- per-shop tagged overhead
```

**SQL sketch:**

```sql
WITH per_currency AS (
    SELECT
        o.currency,
        SUM(oi.quantity * oi.unit_price) AS items_revenue,
        SUM(COALESCE(o.computed_production_cost, o.production_cost, 0)) AS cogs,
        COALESCE(SUM(o.platform_fee), 0) AS non_shipping_fees
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    WHERE o.shop_id = :shop_id
      AND o.status IN ('shipped', 'completed')
      AND COALESCE(o.shipped_at, o.ordered_at) BETWEEN :start AND :end
    GROUP BY o.currency
),
overhead AS (
    SELECT COALESCE(SUM(total_cost), 0) AS allocated_overhead
    FROM overhead_material_receipts
    WHERE shop_id = :shop_id
      AND received_at BETWEEN :start AND :end
)
SELECT
    p.currency,
    p.items_revenue - p.cogs - p.non_shipping_fees - o.allocated_overhead AS base_amount
FROM per_currency p
CROSS JOIN overhead o;
```

**Implementation note:** rather than re-implementing the per-currency JOIN logic in `partner_payout_service`, the service should add a new method to `finance_service` (e.g. `compute_net_profit_product_only(db, shop_id, period_start, period_end) -> list[CurrencyAmount]`) that mirrors the existing `compute_net_profit` but with the two component changes (items revenue instead of total_price; platform_fee only instead of platform_fee + shipping_np_cost). Keeps formula definitions co-located with FIN-1's existing helpers.

**Difference from FIN-1's Net Profit (deltas only):**

| Component | FIN-1 Net Profit | `net_profit_product_only` |
|---|---|---|
| Revenue | `SUM(orders.total_price)` (items + shipping) | `SUM(OrderItem.qty × unit_price)` (items only) |
| Fees | `SUM(platform_fee + shipping_np_cost)` | `SUM(platform_fee)` only |
| COGS | unchanged | unchanged |
| Overhead | unchanged | unchanged |

**Negative base handling:** if `net_profit_product_only` is negative (loss period), `computed_amount` goes negative too. UI surfaces a warning banner; operator typically declines to save (or saves with `notes` documenting the loss). See §6.4.

### 4.3 Currency handling

Both formulas return `list[CurrencyAmount]` — typically a single row per shop (Lamamarka USD, KoraKlenu UAH). For mixed-currency shops (rare in Sergii's practice), see §6.2.

## 5. UI / UX

### 5.1 New section on `/shops/{id}/finance`

Below the existing KPI grid + Revenue Trend chart + diagnostic badge, add a new Card section titled **"Partner Payouts"** with two sub-sections (settlements + payments) and a partner-balance summary at the top.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  Partner Payouts                       [+ Calculate Settlement] [+ Record Payment] │
│  Settlements log + payments ledger + per-partner balance.                      │
├────────────────────────────────────────────────────────────────────────────────┤
│  Balances (current):                                                            │
│    Олег        Settled 4,550 UAH  Paid 3,000 UAH  →  Owed 1,550 UAH            │
│    Світлана    Settled 1,470 UAH  Paid 1,470 UAH  →  Settled in full           │
│    Andriy      Settled  840 USD   Paid   500 USD  →  Owed   340 USD            │
│                                                                                 │
│  Filter:  [Partner ▼]   [Settlements / Payments / All ▼]   Period: [inherited]  │
│                                                                                 │
│  ─── Settlements ─────────────────────────────────────────────────────────────  │
│  Date         Partner    Period       Formula                  %    Amount      │
│  2026-05-31   Олег       May 2026     Items − fees           25%   2,450 UAH   │
│                ↳ Paid 1,000 / 2,450 (partial)         [+ Record Payment] [Del]  │
│  2026-05-31   Світлана   May 2026     Net Profit (product)   15%   1,470 UAH   │
│                ↳ Paid in full                                              [Del] │
│  2026-04-30   Олег       Apr 2026     Items − fees           25%   2,100 UAH   │
│                ↳ Paid in full                                              [Del] │
│                                                                                 │
│  ─── Payments ───────────────────────────────────────────────────────────────   │
│  Date         Partner    Amount        Linked to              Notes             │
│  2026-05-15   Олег       1,000 UAH     May 2026 settlement    Privatbank   [Del]│
│  2026-05-05   Світлана   1,470 UAH     May 2026 settlement                 [Del]│
│  2026-05-02   Олег       2,100 UAH     Apr 2026 settlement    cash         [Del]│
└────────────────────────────────────────────────────────────────────────────────┘
```

Empty state: friendly message + the same `[+ Calculate Settlement]` CTA. Balance summary hidden when no settlements exist.

### 5.2 Calculate Settlement modal

Clicking `[+ Calculate Settlement]` opens (largely unchanged from v1.0; formula label updated):

```
┌────────────────────────────────────────────────────────────┐
│  Calculate Partner Settlement                          [×] │
├────────────────────────────────────────────────────────────┤
│  Partner name:    [Олег___________________________]        │
│                   (autocomplete suggests existing names)   │
│                                                            │
│  Formula:         [% of Net Profit (product-only)        ▼]│
│                   Options:                                 │
│                   • % of Items Revenue minus Platform Fees │
│                   • % of Net Profit (product-only)         │
│                                                            │
│  Percent:         [25.00]  %                               │
│                                                            │
│  Period:          May 2026 (inherited from finance page)   │
│                   [Override...]                            │
│                                                            │
│  ─────────────────────────────────────────────────         │
│  Live preview:                                             │
│  Base amount:     9,800 UAH   (Net Profit product-only)    │
│  Partner share:   2,450 UAH   (25.00% of 9,800)            │
│  ─────────────────────────────────────────────────         │
│                                                            │
│  ☐ Save as settlement record                               │
│  Notes (optional): [_________________________________]     │
│                                                            │
│                       [Cancel]   [Save Settlement]         │
└────────────────────────────────────────────────────────────┘
```

**Key UX details (mostly unchanged from v1.0; small formula-label tweaks):**

- **Partner name autocomplete:** `SELECT DISTINCT partner_name FROM partner_settlements WHERE shop_id = :shop_id UNION SELECT DISTINCT partner_name FROM partner_payments WHERE shop_id = :shop_id ORDER BY partner_name`. Reduces typo risk over time; covers names introduced via either entity.
- **Formula dropdown helper text:** show one-liner description below the dropdown explaining each option:
  - *Items Revenue minus Platform Fees* — for revenue-share partners; excludes shipping
  - *Net Profit (product-only)* — for profit-share partners; excludes shipping margin/cost
- **Live preview:** recomputes on every field change (debounced). Hits a lightweight backend endpoint (`POST /api/shops/{id}/partner-payouts/preview`) — does NOT persist. Returns `{base_amount, base_currency, computed_amount}`.
- **"Save as settlement record" checkbox:** Default ON for the typical monthly cadence. Operator can uncheck for ad-hoc "what's the number" checks. If unchecked, modal closes without persisting (calculator-only use case).
- **Period override:** opens a small inline date-range picker. Used when operator wants to compute a partial month or custom range.
- **Save button label dynamically:** "Save Settlement" when checkbox ON, "Close" (or grey-out) when OFF.

### 5.3 Record Payment modal

Clicking `[+ Record Payment]` (top-level) OR per-row `[+ Record Payment]` (inside a settlement) opens:

```
┌────────────────────────────────────────────────────────────┐
│  Record Partner Payment                                [×] │
├────────────────────────────────────────────────────────────┤
│  Partner name:    [Олег___________________________]        │
│                   (autocomplete; pre-filled if launched    │
│                    from a settlement row)                  │
│                                                            │
│  Linked settlement (optional):                             │
│   [May 2026 — 2,450 UAH (paid 0 / 2,450)             ▼]   │
│   Options:                                                 │
│   • (none — count toward balance only)                     │
│   • May 2026 — 2,450 UAH (paid 0 / 2,450)                  │
│   • Apr 2026 — 2,100 UAH (paid in full)                    │
│   ...                                                      │
│   (List filtered to selected partner; pre-selected if      │
│    launched from settlement row)                           │
│                                                            │
│  Amount:          [1,000.00]  [UAH ▼]                      │
│                                                            │
│  Paid on:         [2026-05-15]                             │
│                                                            │
│  Notes (optional): [Privatbank transfer ___________]       │
│                                                            │
│                       [Cancel]   [Record Payment]          │
└────────────────────────────────────────────────────────────┘
```

**Key UX details:**

- **Pre-fill from context:** if launched from a settlement row's `[+ Record Payment]` button, partner name + linked settlement + currency are pre-filled. Operator usually only enters amount + date + optional note.
- **Currency mismatch warning:** if operator picks a settlement in USD but selects UAH from the currency dropdown, show inline warning (orange, not blocking): *"Currency differs from linked settlement. The payment will not contribute to the USD balance for this partner."* Operator can proceed if intentional.
- **Amount validation:** `> 0` required. If linked settlement has a remaining balance smaller than the entered amount, show inline note: *"This exceeds the linked settlement's remaining balance (1,450 UAH). Excess will count toward partner's overall balance."* Not blocking — overpayment is a real scenario.
- **Linked-settlement dropdown:** filtered by selected partner_name (autocomplete-driven). Each option shows period + amount + payment progress. The *(none)* option is always first.

### 5.4 Settlements log table — per-row payment progress badge

Per-settlement row shows a small badge: `Paid X / Y currency` computed from linked payments. States:
- **No payments yet:** small grey "Unpaid" pill.
- **Partial:** orange "Paid X / Y" pill.
- **Full:** green "Paid in full" pill.
- **Overpaid:** small purple "Overpaid by X" pill (rare; happens if operator records payment exceeding settlement).

Per-row actions: `[+ Record Payment]` (opens modal pre-filled), `[Delete]` (confirmation dialog warning that linked payments will become unlinked but not deleted).

### 5.5 Shipping Net KPI card on FIN-1

New small KPI card on `/shops/{id}/finance`, sitting in the existing KPI grid alongside Revenue, COGS, Fees, Overhead, Net Profit:

```
┌──────────────────────────┐
│  Shipping Net            │
│  +120 UAH                │
│  ▲ +15 UAH vs prev period│
└──────────────────────────┘
```

**Calculation (per currency, per period):**

```
shipping_net = SUM(orders.total_price - items_subtotal) - SUM(orders.shipping_np_cost)
             = shipping_revenue - shipping_cost
```

Where `items_subtotal = SUM(OrderItem.qty × OrderItem.unit_price)` per order.

**Auto-hide rule:** if both `shipping_revenue = 0` AND `shipping_cost = 0` for the period (typical Etsy shop where customers pay NP directly, and no Shopify-style shipping income captured), card is not rendered. This avoids cluttering the KPI grid with empty zeros for shops where shipping isn't an OrderHub concern.

**Why this card belongs on FIN-1, not in Partner Payouts:** Shipping margin is operator-only economics (partners don't share in it per decision #7 + #17). Putting it next to Net Profit lets operator notice "huh, shipping bled 80 UAH this month" without polluting the partner-share view. PART-1 ships this card alongside the partner UI as a small additive enhancement to FIN-1 — not a separate sprint.

### 5.6 No changes to existing FIN-1 surfaces (besides the new KPI card)

KPI grid — gets one new card (Shipping Net) when applicable. Revenue Trend chart, Diagnostic badge — unchanged. Sergii's existing finance workflow is unaffected; partner payouts + Shipping Net are additive.

## 6. Edge cases (documented, not auto-handled)

### 6.1 Currency handling — settlement and payment stay in same currency

Per settled decision #6. Lamamarka USD partner share stored as USD. Operator handles UAH conversion at payment time outside the system. No FX rate stored. Payments are recorded in their actual currency; balance computation groups by currency, so a partner could theoretically have "owed 340 USD AND owed 0 UAH" displayed as two rows (rare; only happens if operator mixes payment currencies for one partner, which would be unusual practice).

Future possibility (`profit-definition.md` Q3): if FX volatility makes this painful, add `payment_currency` + `payment_amount_in_settlement_currency` columns later, or track a daily FX rate table.

### 6.2 Multi-currency shop edge case

If KoraKlenu (UAH-primary) somehow accumulates a few USD orders in a period (rare but theoretically possible), the formula returns multiple currency rows. Calculator modal must pick **one** currency for the settlement.

**MVP behavior:** show currency dropdown in the modal when more than one currency in the base. Operator picks which currency the settlement is for. If operator wants per-currency settlements, they save two records (one per currency).

If single currency: dropdown is hidden / disabled, currency auto-selected.

### 6.3 Partner name typo risk

Free-text `partner_name` allows "Олег" + "oleh" + "Oleg" as three distinct partners in the filter and balance calculation.

**Mitigations:**
- Autocomplete dropdown (5.2 + 5.3) suggests existing names from BOTH settlement and payment tables — operator selects rather than retypes.
- Filter dropdown is case-insensitive (`LOWER()` in WHERE / via collation).
- **Accepted limitation** — no auto-canonicalization. If Sergii notices a typo accidentally created two "Олег" identities, he deletes the outliers and recreates with the canonical name. Payment-settlement linkage is preserved via FK during this cleanup (only the displayed name normalizes).

### 6.4 Negative base / negative settlement

If `base_amount` is negative (loss period: overhead exceeds revenue, or fees exceed items revenue), `computed_amount = base_amount × percent / 100` is also negative.

**MVP behavior:** display preview as-is. Surface info banner: *"Net profit (product-only) for this period is negative (loss). Partner share would also be negative. Per §6.4 of profit-definition.md, Sergii typically absorbs losses; consider not creating a settlement for this period."*

Operator typically declines to save (Sergii's policy: he absorbs losses, partners get 0). If operator does save, the negative settlement is tracked normally and contributes to balance (operator could receive money back from partner to offset, though this is unprecedented in Sergii's practice).

### 6.5 Self-share convention

Per settled decision #11. Sergii creates settlements for OTHER partners; his own share is "whatever's left". Convention, not enforced. If Sergii later wants to track his own share (e.g. for personal income records), he creates a settlement with `partner_name = "Sergii"` like any other partner.

### 6.6 Payment without prior settlement

If operator creates a payment for a partner who has no settlements yet (e.g. cash advance), `settlement_id` is NULL. The payment shows in the payments log. The partner's balance becomes negative (operator overpaid). This is fine; next settlement will reduce the overpaid amount.

### 6.7 Deleting a settlement with linked payments

`ondelete='SET NULL'` on `payments.settlement_id` means deleting a settlement leaves linked payments intact (just unlinked). The payments still count toward overall partner balance. UI delete dialog warns: *"This settlement has 2 linked payments totaling 1,000 UAH. Those payments will remain in the ledger but no longer linked to a settlement."* Operator can then re-link them via edit (no — payments are immutable; operator deletes + recreates with new linkage if needed).

## 7. Implementation sprint breakdown

### PART-1 — Partner Payout monoblock (settlements + payments + balance + Shipping Net KPI)

**Confirmed scope** (per Sergii: *"PART-1 моноблок"*):

**Backend:**
- New entity `PartnerSettlement` (per §3.1 schema)
- New entity `PartnerPayment` (per §3.4 schema)
- One Alembic migration (two new tables + one Postgres ENUM + indexes + CHECK constraints)
- New service `backend/services/partner_payout_service.py` with:
  - `compute_base_amount(db, shop_id, period_start, period_end, formula_type) -> list[CurrencyAmount]`
  - `create_settlement(...)` — persists `PartnerSettlement` with snapshot values
  - `list_settlements(db, shop_id, filters) -> paginated list`
  - `delete_settlement(db, settlement_id)` — hard delete; linked payments become unlinked via FK
  - `create_payment(...)` — persists `PartnerPayment`; warns on currency mismatch
  - `list_payments(db, shop_id, filters)` — paginated
  - `delete_payment(db, payment_id)` — hard delete
  - `get_partner_balances(db, shop_id) -> list[PartnerBalance]` — per-partner-per-currency aggregate
  - `compute_settlement_payment_progress(db, settlement_ids) -> dict[settlement_id, paid_amount]` — for badge rendering
- New method on `finance_service`: `compute_net_profit_product_only(db, shop_id, period_start, period_end) -> list[CurrencyAmount]` (mirrors existing Net Profit logic with deltas from §4.2 table)
- New method on `finance_service`: `compute_shipping_net(db, shop_id, period_start, period_end) -> list[CurrencyAmount]` (for Shipping Net KPI card)
- Update existing `get_shop_finance` response to include `shipping_net` field (auto-omitted if zero)
- New router `backend/routers/partner_payouts.py`:
  - `POST /api/shops/{id}/partner-payouts/preview` — returns `{base_amount, base_currency, computed_amount}` without persisting
  - `POST /api/shops/{id}/partner-payouts/settlements` — creates settlement
  - `GET  /api/shops/{id}/partner-payouts/settlements?partner=&limit=&offset=` — paginated list (includes `paid_amount` per settlement)
  - `DELETE /api/shops/{id}/partner-payouts/settlements/{id}` — hard delete
  - `POST /api/shops/{id}/partner-payouts/payments` — creates payment
  - `GET  /api/shops/{id}/partner-payouts/payments?partner=&settlement_id=&limit=&offset=` — paginated list
  - `DELETE /api/shops/{id}/partner-payouts/payments/{id}` — hard delete
  - `GET  /api/shops/{id}/partner-payouts/balances` — per-partner-per-currency aggregates
  - `GET  /api/shops/{id}/partner-payouts/partner-names` — DISTINCT autocomplete source (both tables)
  - All role-gated `OWNER, MANAGER` (DESIGNER → 403, mirrors materials/finance gating)

**Frontend:**
- New section "Partner Payouts" Card on `/shops/{id}/finance` (per §5.1 layout)
- New components:
  - `<PartnerBalancesSummary>` — top of section
  - `<PartnerSettlementsTable>` — settlements log with payment-progress badges + per-row actions
  - `<PartnerPaymentsTable>` — payments ledger
  - `<CalculateSettlementModal>` — calculator + save (per §5.2)
  - `<RecordPaymentModal>` — payment entry (per §5.3)
- New `<ShippingNetKpi>` card in existing KPI grid (auto-hides on zero)
- New API client methods + React Query hooks (one hook per endpoint above)

**Tests:**
- Backend: 8–10 service-level tests:
  - Both formula types (preview correctness with seeded orders/items)
  - Settlement create/list/delete flows
  - Payment create/list/delete flows
  - Balance computation (single partner, multi-partner, multi-currency)
  - Per-settlement progress with linked + unlinked payments
  - Shipping Net KPI calculation (positive, negative, zero auto-hide)
  - Delete settlement → linked payments survive with NULL settlement_id
- Backend: 2–3 router tests (role gating + path validation + happy path)
- Frontend: 4–6 vitest cases (modals render, live preview updates, payment progress badges, Shipping Net KPI auto-hides)

**Estimated effort:** medium-large full-stack sprint, **~5–7 work sessions**. Larger than FIN-1 due to two entities + balance logic + Shipping Net KPI, but each piece is straightforward CRUD + aggregation. No unprecedented patterns; mirrors existing FIN-1 / MAT shape.

**Out of scope (deferred):**
- PDF generation (PART-2)
- Partner-facing dashboard (future)
- Multi-shop aggregation per partner (future)
- Settlement export (CSV) (future)
- Reminders/notifications (future)
- Soft delete with trash (future, if operator needs it)

### PART-2 — PDF generation (future)

**Trigger:** Sergii has used PART-1 for ≥1 month and knows what fields he wants in the PDF (signature blocks? balance summary? line-item breakdowns? logo?).

**Anticipated scope:**
- New endpoint `GET /api/shops/{id}/partner-payouts/settlements/{id}/pdf` returns a generated PDF with:
  - Shop name + logo (if uploaded)
  - Partner name
  - Period
  - Formula description (human-friendly: "25% of items revenue minus platform fees")
  - Base amount + computed amount
  - Payment history for this settlement (if any)
  - Outstanding balance for this settlement
  - Operator name + date
  - Optional notes
- Optionally a "balance statement" PDF: `GET /api/shops/{id}/partner-payouts/balances/{partner_name}/pdf` summarizing all open settlements + payments per partner.
- Frontend "Download PDF" buttons on settlement rows + balance rows.
- PDF library: reportlab (Python-side) — simpler authentication, returns binary, consistent with backend tooling.

**Estimated effort:** small sprint, ~1–2 work sessions per PDF type.

### Future iterations (not committed)

- **PART-3** — `Partner` entity if Sergii's volume/complexity grows. Migration: deduplicate `partner_name` strings on both tables → create Partner records → backfill FK column. Done as separate sprint when triggered.
- **PART-4** — Automatic monthly settlement reminders / draft creation. Likely a `scheduled-tasks` job that pre-fills settlements at month-end based on previous month's pattern.
- **PART-5** — Partner-facing view (read-only access for partners to see their own settlements + payment history).
- **PART-6** — FX-aware payment recording (track FX rate at payment time; produce UAH-equivalent reports across all USD shops). Triggered by `profit-definition.md` Q3 revisit.

None of these are committed; surfaced for context only.

## 8. Out of scope (explicit non-goals)

- **Partner entity / agreements table** — Sergii's choice, see §3.2.
- **Automatic settlement triggering** — operator manually creates each settlement (matches today's Excel-driven cadence).
- **FX conversion / multi-currency aggregation** — see `profit-definition.md` Q3.
- **Settlement editing** — immutable + delete-recreate. See settled decision #4.
- **Payment editing** — same pattern. See settled decision #14.
- **Partner-facing dashboard / login** — far-future. PART-1 is operator-only.
- **Settlement workflow states** (draft / approved / paid) — single state (saved). Payment progress derived from linked PartnerPayment rows; no need for a state machine.
- **Cross-shop partner aggregation** — partners are per-shop today. If Sergii ever wants "what did Олег earn across all shops in 2026?", that's a future feature requiring partner_name normalization first.
- **Shipping margin in partner share** — explicitly excluded per decisions #7 + #17. Shipping Net KPI exists for operator visibility only.
- **Negative settlement automation** — operator decides whether to save loss-period settlements (Sergii absorbs losses by policy). System informs but doesn't enforce.

## 9. Known limitations (accepted, not bugs)

1. **Snapshot pattern means historical settlements don't reflect retroactive data changes.** A receipt added in June for an April material won't change April's saved settlement. This is by design (audit integrity), and Sergii's monthly cadence makes this acceptable. If a partner challenges a settlement, operator deletes and recreates.

2. **Free-text partner names are typo-prone.** Mitigation via autocomplete (sources both settlements + payments) + case-insensitive listing (§6.3). If duplicates accumulate, operator manually cleans up by deleting outliers and recreating with canonical names.

3. **No FX in settlement records or payments.** Lamamarka USD partner share is stored as USD; operator manually converts at payment. If FX volatility creates pain, future `profit-definition.md` Q3 resolution.

4. **Negative settlements are visible but operator-interpreted.** UI surfaces a warning banner; doesn't auto-clamp.

5. **No partner-facing view.** Partners ask Sergii for settlement amounts and balance; Sergii reads them from the settlements + balance display (or, post-PART-2, generates PDFs to share). Partners don't log into OrderHub.

6. **Settlement deletion is silent (hard delete).** If Sergii deletes an incorrect settlement, there's no "trash" or recovery. Settlements are operator-controlled; mistakes are recreated, not recovered. Linked payments survive with NULL `settlement_id` (operator can re-link by deleting + re-creating the payment).

7. **`net_profit_product_only` formula inherits whatever its definition is at calculation time.** If FIN-1's underlying COGS or overhead logic changes in a future sprint (e.g. Phase C of `production_cost` cutover), live preview reflects the new formula, but already-saved settlements retain their snapshot. Per settled decision #3.

8. **Shipping Net KPI is informational only.** Doesn't drive any settlement math; doesn't get its own trend chart in PART-1; doesn't alert. If Sergii wants alerting on negative shipping margin, that's a future enhancement.

9. **Balance can be misleading across currencies.** If a partner has 1,000 UAH owed AND 100 USD owed, the UI shows two rows; there's no auto-conversion or "total in UAH equivalent". Same FX rationale as elsewhere.

10. **Payment without a matching settlement creates negative balance.** This is correct semantically (operator overpaid) but might confuse if operator doesn't realize they're recording an advance. UI treats negative balance as a normal display state with an info tooltip explaining "advance payment exceeds settlements to date".

## 10. Next steps

1. Sergii reads this v1.1; flags any decisions to revisit, fills in open questions where ready, adds use cases I missed.
2. Cowork iterates if needed (this discovery felt complete; expecting ≤1 round).
3. Cowork translates this design + companion `profit-definition.md` v1.1 into `task.md` (PART-1 monoblock spec).
4. CC executes PART-1 via standard AI_ONBOARDING workflow.
5. PART-2 (PDF) triggered by Sergii's signal after PART-1 is in use ≥1 month.

**Companion document:** `profit-definition.md` v1.1 — defines `net_profit_product_only` formula and documents why partner profit ≠ FIN-1 Net Profit.

---

This document lives at `docs/design/partner-payouts.md`. Update in place as decisions evolve. Like other design docs in this folder, each material update gets a Status line bump + Changelog entry.

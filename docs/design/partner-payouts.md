# Partner Payouts — Design Document

**Status:** Draft 1.0 — 2026-05-15
**Phase:** Phase 2 of Finance epic (Phase 3 Materials Warehouse closed end-to-end at MAT-5)
**Authors:** Sergii (operator) + Cowork (planning)
**Review state:** Awaiting first-pass review. **Not yet broken into sprints; no code touched.**

---

## 1. Context

OrderHub's primary motivation from day 1 was **Sergii's frustration with Excel-based partner payout tracking**. Each shop has 1–2 partners with different deal structures — some on % of revenue, some on % of profit, sometimes mixed within one shop. Today partners ask "what's my share for May?" and Sergii recomputes from scratch in Excel, with the implicit risk of inconsistency between conversations.

Phase 3 (Materials Warehouse, 5 sprints, commits MAT-1..5) shipped reliable per-shop financial primitives — Net Profit per shop per period per currency, with COGS sourced from BOM-computed costs (or manual fallback) and overhead expenses subtracted. With these primitives in place, **PART-1 builds the partner payout layer on top**.

### 1.1 Sergii's actual partner contracts (2026-05-15)

Captured from discovery conversation:

| Shop | Partner role | Formula |
|---|---|---|
| Lamamarka Shopify | Creative / ideas / traffic | **25% of revenue** (items only, minus Shopify platform fees, NO shipping) |
| Lamamarka Shopify | Mockups + foreign-shipment paperwork | **15% of profit** |
| Lamamarka Etsy | Generic partner | **10% of profit** |
| Lamamarka Etsy | Mockups + tracking | **15% of profit** |
| KoraKlenu | Operating partner | **50% of profit** |

Two formula categories cover all of Sergii's current arrangements:
- **One partner on revenue-share** with shop-specific basis (items minus fees, excluding shipping)
- **Four partners on profit-share** with consistent basis (FIN-1's Net Profit)

### 1.2 Industry research findings (concise)

Web research (2026-05-15, see PART-1 task.md or this discovery's chat history for full citations) surfaced three relevant patterns:

1. **~80% of small business partnerships fail within 5 years; money disagreements are the #1 cause** — most disputes trace to ambiguous definition of "profit". Locked in `profit-definition.md` and explicitly defined here.
2. **Revenue-share is structurally riskier for the operator**: partner gets their cut regardless of whether the shop is profitable. Industry consensus prefers profit-share for partner alignment. Sergii's Lamamarka Shopify creative on revenue-share is the higher-risk arrangement; documented but not flagged for change.
3. **Existing Shopify/Etsy partner-tracking apps all use configured-partner-records pattern** (CollabPay, Revenue Split, etc.). I did NOT find an "ad-hoc calculator + settlements log" pattern in market tools. Sergii's preferred design (no Partner entity) is uncommon but defensible for his solo-operator, low-volume, varying-partner-arrangement reality.

## 2. Settled decisions (from 2026-05-15 discovery)

| # | Decision | Rationale |
|---|---|---|
| 1 | **No Partner entity** — `partner_name` is free text on each settlement | Per Sergii: partner relationships evolve; new shops bring new partners; explicit Partner records would force setup-and-archive ceremony for every arrangement change. Maximum flexibility. Cost: typo risk on partner names (mitigated by autocomplete dropdown). |
| 2 | **Two formula types** in PART-1 enum: `revenue_items_minus_fees` and `net_profit` | These cover all five of Sergii's current contracts. A speculative `revenue_total` option (% of gross sales including shipping) was considered and dropped — no current partner uses it, YAGNI. Future formulas added via Alembic `ALTER TYPE ADD VALUE` if a new contract requires it. |
| 3 | **Snapshot pattern: base_amount and computed_amount frozen on creation** | If FIN-1 numbers change retroactively (e.g. a new receipt added in June changes May's COGS), already-saved settlements DO NOT recompute. Each settlement is "this is what I computed and told the partner that day". Same audit-integrity pattern as `MaterialMovement.unit_cost_at_movement` from MAT-2. |
| 4 | **Immutable + delete-and-recreate** (no edit) | Settlement records cannot be edited after creation. Operator can delete and re-save with correct values. Preserves audit trail; if Sergii saved 25% then realized it should be 20%, the deletion-recreation pattern shows both attempts in the operator's history (delete logged via audit; recreation is a new row). |
| 5 | **Hard delete is acceptable for v1** | No regulatory audit requirement (simplified taxation system per Sergii). If Sergii later wants soft-delete for traceability, `deleted_at` column added without migration headache. |
| 6 | **Settlement records stay in shop currency, no FX conversion** | Lamamarka USD partner shares store as USD; Sergii converts manually at payment time using whatever FX rate he chooses. Same workflow as today's Excel approach. No FX rate stored in PART-1; if needed, Q3 in `profit-definition.md`. |
| 7 | **Net Profit uses existing FIN-1 formula** (no separate definition for partner shares) | Per Sergii: use existing definition as starting point, revisit when partner conversation forces it. `profit-definition.md` documents the formula, all components, and open questions for future revisits. |
| 8 | **`revenue_items_minus_fees` formula = `SUM(OrderItem.quantity × OrderItem.unit_price) − SUM(Order.platform_fee)`** | Per Sergii: revenue basis is items only (no shipping), minus Shopify/Etsy platform fee. `total_price` includes shipping (verified on Heavy Mushroom Keychain: item 14.99 + shipping 8 = total 22.99) so it's the wrong basis. JOIN order_items table to get item-level subtotal. Filters mirror Net Profit: `status IN ('shipped', 'completed')` + period range on `COALESCE(shipped_at, ordered_at)`. |
| 9 | **PDF generation deferred to PART-2** | Sergii confirmed: "Якщо недорого зробити генерацію PDF давай зробимо". Defer until PART-1 calculator + settlements log are in use for ≥1 month — Sergii will have learned what fields he actually wants in the PDF (signature blocks? line-item breakdowns? logo?). Designing PDF prematurely = waste. |
| 10 | **Independent partners on same shop** — each partner's share computed from the original FIN-1 numbers, not from "what's left after another partner's share" | Per Sergii: "з оригінального profit беру 15% незалежно". KoraKlenu 50% partner doesn't compound from a "post-partner" profit; Lamamarka Shopify 15%-profit partner gets 15% of original Net Profit, not 15% of (Net Profit − 25% creative cut). Order of saving settlements doesn't matter. |
| 11 | **Self-share is implied, not tracked** (Sergii doesn't create settlements for himself) | KoraKlenu = 50/50; Sergii creates partner's 50% settlement; his own 50% is whatever's left after partner settlements. No "self-settlement" record. Cleaner audit log. |

## 3. Domain model

### 3.1 `PartnerSettlement` entity

| Column | Type | Constraint | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `shop_id` | UUID | FK → Shop, NOT NULL, `ondelete='RESTRICT'` | Don't accidentally drop settlement history on shop delete (use shop archive instead). |
| `partner_name` | str(200) | NOT NULL | Free text. NO Partner entity. |
| `formula_type` | ENUM | NOT NULL | `revenue_items_minus_fees` \| `net_profit` (Postgres ENUM `partner_settlement_formula`). |
| `percent` | Decimal(5,2) | NOT NULL, > 0 AND ≤ 100 | E.g. 25.00 for 25%. CHECK constraint at DB level. |
| `period_start` | date | NOT NULL | Inclusive. |
| `period_end` | date | NOT NULL | Inclusive. CHECK constraint: `period_end >= period_start`. |
| `base_amount` | Decimal(12,2) | NOT NULL | **Snapshot.** The total amount the formula was applied to (e.g. SUM(items - fees) for that formula, or Net Profit for `net_profit`). Frozen at creation time. |
| `base_currency` | str(3) | NOT NULL | ISO 4217 code. Whatever currency the base aggregation produced (typically the shop's primary currency). |
| `computed_amount` | Decimal(12,2) | NOT NULL | **Snapshot.** Calculated as `base_amount × percent / 100`. Can be negative if `base_amount` is negative. |
| `notes` | text | NULL | Optional operator memo (e.g. "paid via Privatbank Apr 15"). |
| `created_at` | datetime(tz) | NOT NULL, default `now()` | |
| `created_by_user_id` | UUID | FK → User, NOT NULL, `ondelete='RESTRICT'` | Audit; never delete user that created settlements. |

Indexes:
- `(shop_id, period_start)` — primary lookup pattern (list settlements for shop, sorted by period DESC)
- `(partner_name, shop_id)` — autocomplete dropdown source + cross-shop partner lookup if ever needed

No `relationship()` back to `Shop` or `User` (lightweight read-only references; service queries explicit JOINs if needed).

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

None of these are operational asks today. If Sergii later wants them, **migrating from `partner_name` (string) to `partner_id` (FK)** is a one-time data cleanup: deduplicate strings, create Partner records, backfill FK. Manageable.

### 3.3 Additive changes to existing entities

**None.** Phase B (MAT-5) already added `Order.computed_production_cost`. All other components of Net Profit and Revenue Items-Minus-Fees use existing columns. **No schema changes outside the new `partner_settlements` table.**

## 4. Formulas

Both formulas compute a per-currency `base_amount` for a given shop + period. The settlement's `computed_amount` is `base_amount × percent / 100`.

### 4.1 `revenue_items_minus_fees`

**Purpose:** Sergii's Lamamarka Shopify creative partner case. Revenue from item sales minus platform fees (Shopify commission), excluding shipping.

**SQL:**

```sql
SELECT
    oi.currency,  -- actually orders.currency via JOIN; orders has currency
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

**Negative base handling:** if platform fees somehow exceed items (e.g. high-fee Etsy order combined with a refund), `base_amount` goes negative. Settlement stored as-is; computed_amount also negative. Operator interprets — see §6 Edge Cases.

### 4.2 `net_profit`

**Purpose:** Sergii's profit-share partners (all four other cases). Reuses FIN-1's Net Profit calculation.

**Implementation:** Call existing `finance_service.compute_net_profit()` helper (or whatever the equivalent is — confirm during PART-1 sprint planning by greping `finance_service.py`). The new partner-payout-service simply wraps the existing helper, requesting Net Profit for the requested shop + period, returning per-currency rows.

**Pseudo-code:**
```python
async def compute_net_profit_for_period(db, shop_id, period_start, period_end):
    # Delegates to FIN-1's existing aggregate logic; returns
    # list[CurrencyAmount] mirroring the shape used in ShopFinanceResponse.
    finance_data = await finance_service.get_shop_finance(
        db, shop_id, period_start, period_end
    )
    return [
        CurrencyAmount(currency=c.currency, amount=c.amount)
        for c in finance_data.net_profit.current
    ]
```

**Why delegate:** keeps the Net Profit definition in one place (FIN-1's service). When `profit-definition.md` gets revised, only FIN-1 changes, partner payouts automatically reflect. No drift.

### 4.3 Currency handling

Both formulas return `list[CurrencyAmount]` — typically a single row per shop (Lamamarka USD, KoraKlenu UAH). For mixed-currency shops (rare in Sergii's practice), see §6.2.

## 5. UI / UX

### 5.1 New section on `/shops/{id}/finance`

Below the existing KPI grid + Revenue Trend chart + diagnostic badge, add a new Card section titled **"Partner Payouts"**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Partner Payouts                                       [+ Calculate Payout] │
│  Quick-compute partner shares; save settlement records for monthly cadence. │
├─────────────────────────────────────────────────────────────────────────────┤
│  Filter:  [Partner name (autocomplete) ▼]   Period: [inherited from above]  │
│                                                                              │
│  Date           Partner      Period       Formula              %    Amount  │
│  2026-05-31     Олег         May 2026     Items − fees       25%   2,450 UAH│
│  2026-05-31     Світлана     May 2026     Net Profit         15%   1,470 UAH│
│  2026-04-30     Олег         Apr 2026     Items − fees       25%   2,100 UAH│
│  ...                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

Empty state: friendly message + the same `[+ Calculate Payout]` CTA.

### 5.2 Calculate Payout modal

Clicking `[+ Calculate Payout]` opens:

```
┌────────────────────────────────────────────────────────────┐
│  Calculate Partner Payout                              [×] │
├────────────────────────────────────────────────────────────┤
│  Partner name:    [Олег___________________________]        │
│                   (autocomplete suggests existing names)   │
│                                                            │
│  Formula:         [% of Net Profit                       ▼]│
│                   Options:                                 │
│                   • % of Items Revenue minus Platform Fees │
│                   • % of Net Profit                        │
│                                                            │
│  Percent:         [25.00]  %                               │
│                                                            │
│  Period:          May 2026 (inherited from finance page)   │
│                   [Override...]                            │
│                                                            │
│  ─────────────────────────────────────────────────         │
│  Live preview:                                             │
│  Base amount:     9,800 UAH   (Net Profit for period)      │
│  Partner share:   2,450 UAH   (25.00% of 9,800)            │
│  ─────────────────────────────────────────────────         │
│                                                            │
│  ☐ Save as settlement record                               │
│  Notes (optional): [_________________________________]     │
│                                                            │
│                       [Cancel]   [Save Settlement]         │
└────────────────────────────────────────────────────────────┘
```

**Key UX details:**

- **Partner name autocomplete:** `SELECT DISTINCT partner_name FROM partner_settlements WHERE shop_id = :shop_id ORDER BY partner_name`. Reduces typo risk over time.
- **Formula dropdown helper text:** show one-liner description below the dropdown explaining each option (avoid operator misclicking and saving wrong-base settlement).
- **Live preview:** recomputes on every field change (debounced). Hits a lightweight backend endpoint (`POST /api/shops/{id}/partner-payouts/preview`) — does NOT persist. Returns `{base_amount, base_currency, computed_amount}`.
- **"Save as settlement record" checkbox:** **Default ON for the first month settlements** (the typical monthly cadence). Operator can uncheck for ad-hoc "what's the number" checks. If unchecked, modal closes without persisting (calculator-only use case).
- **Period override:** opens a small inline date-range picker. Used when operator wants to compute a partial month or custom range.
- **Save button label dynamically:** "Save Settlement" when checkbox ON, "Close" (or grey-out) when OFF.

### 5.3 Settlements log table

Shows `PartnerSettlement` rows for the current shop, sorted by `created_at DESC` (or by period — to be decided in PART-1 planning).

**Filter row:**
- Partner name dropdown (populated from existing settlements via DISTINCT query).
- Period range (currently shows all; sub-filter possible if many settlements accumulate).

**Per-row actions:**
- **Delete button** — opens confirmation dialog ("Delete settlement for Олег / May 2026 (2,450 UAH)? This cannot be undone."). On confirm, hard-deletes the row. No edit (per settled decision #4).

**Empty state:** "No settlements recorded yet. Use Calculate Payout above to start."

### 5.4 No changes to existing FIN-1 surfaces

The new Card sits below existing surfaces. KPI grid, Revenue Trend chart, Diagnostic badge — all unchanged. Sergii's existing finance workflow is unaffected; partner payouts are additive.

## 6. Edge cases (documented, not auto-handled)

### 6.1 Currency handling — settlement stays in shop currency

Per settled decision #6. Lamamarka USD partner share stored as USD. Operator handles UAH conversion at payment time outside the system. No FX rate stored.

Future possibility (`profit-definition.md` Q3): if FX volatility makes this painful, add `payment_currency` + `payment_amount` columns later.

### 6.2 Multi-currency shop edge case

If KoraKlenu (UAH-primary) somehow accumulates a few USD orders in a period (rare but theoretically possible), Net Profit returns multiple currency rows. Calculator modal must pick **one** currency for the settlement.

**MVP behavior:** show currency dropdown in the modal when more than one currency in the base. Operator picks which currency the settlement is for. If operator wants per-currency settlements, they save two records (one per currency).

If single currency: dropdown is hidden / disabled, currency auto-selected.

### 6.3 Partner name typo risk

Free-text `partner_name` allows "Олег" + "oleh" + "Oleg" as three distinct partners in the filter.

**Mitigations:**
- Autocomplete dropdown (5.2 above) suggests existing names — operator selects rather than retypes.
- Filter dropdown is case-insensitive collation (`COLLATE` choice at DB level if applicable, or `LOWER()` in the WHERE clause).
- **Accepted limitation** — no auto-canonicalization. If Sergii notices a typo accidentally created two "Олег" rows, he deletes the duplicates and saves with the canonical name.

### 6.4 Negative Net Profit / negative base_amount

If `base_amount` is negative (overhead exceeds revenue, or item fees exceed items revenue), `computed_amount = base_amount × percent / 100` is also negative.

**MVP behavior:** display as-is. Operator interprets — typically deletes the calculation without saving, or saves with `computed_amount = 0` via a custom note explaining "no settlement this period due to loss".

**Worth flagging in UI:** when preview shows negative base, surface an info banner: *"Net profit for this period is negative (loss). Partner share would also be negative. Consider not creating a settlement for this period, or check your formula choice."*

### 6.5 Self-share convention

Per settled decision #11. Sergii creates settlements for OTHER partners; his own share is "whatever's left". Convention, not enforced. If Sergii later wants to track his own share (e.g. for personal income records), he creates a settlement with `partner_name = "Sergii"` like any other partner.

## 7. Implementation sprint breakdown

### PART-1 — Partner Payout Calculator + Settlements log

**Scope:**
- New entity `PartnerSettlement` (per §3.1 schema).
- One Alembic migration (new table + Postgres ENUM + indexes + CHECK constraints).
- New service `backend/services/partner_payout_service.py` with:
  - `compute_base_amount(db, shop_id, period_start, period_end, formula_type) -> list[CurrencyAmount]` — calls into existing `finance_service` for `net_profit`, or runs the items-minus-fees SQL for `revenue_items_minus_fees`.
  - `create_settlement(...)` — persists `PartnerSettlement` with snapshot values.
  - `list_settlements(db, shop_id, filters) -> paginated list`.
  - `delete_settlement(db, settlement_id)` — hard delete.
- New router `backend/routers/partner_payouts.py` with three endpoints:
  - `POST /api/shops/{id}/partner-payouts/preview` — returns `{base_amount, base_currency, computed_amount}` without persisting. For live preview.
  - `POST /api/shops/{id}/partner-payouts` — creates a settlement record.
  - `GET /api/shops/{id}/partner-payouts?partner=&limit=&offset=` — paginated list.
  - `DELETE /api/shops/{id}/partner-payouts/{settlement_id}` — hard delete.
  - All role-gated `OWNER, MANAGER` (DESIGNER → 403, mirrors materials/finance gating).
- Frontend additions on `/shops/{id}/finance` page:
  - New section: "Partner Payouts" Card below existing finance surfaces.
  - New components: `<PartnerPayoutModal>` (calculator + save), `<PartnerSettlementsTable>` (log + delete).
  - New API client methods + React Query hooks.
- Tests:
  - Backend: 4–5 compile-SQL tests (preview formula assertions for both types; persist flow; list filtering; delete) + 1–2 router tests (role gating + path-param validation).
  - Frontend: 3–4 vitest cases (modal renders, live preview updates on field change, save calls API, table renders with mocked data).

**Estimated effort:** medium full-stack sprint, ~3–5 work sessions. Comparable to FIN-1.

**Out of scope (deferred to PART-2 or future):**
- PDF generation
- Partner-facing dashboard
- Multi-shop aggregation per partner
- Settlement export (CSV)
- Reminders/notifications

### PART-2 — PDF generation (future)

**Trigger:** Sergii has used PART-1 for ≥1 month and knows what fields he wants in the PDF.

**Scope (anticipated):**
- New endpoint `GET /api/shops/{id}/partner-payouts/{settlement_id}/pdf` returns a generated PDF with:
  - Shop name + logo (if uploaded)
  - Partner name
  - Period
  - Formula description (human-friendly: "25% of items revenue minus platform fees")
  - Base amount + computed amount
  - Operator name + date
  - Optional notes
- Frontend "Download PDF" button on each settlement row.
- PDF library choice: reportlab (Python-side) or jsPDF (frontend). Likely Python — simpler authentication, returns binary.

**Estimated effort:** small sprint, ~1–2 work sessions.

### Future iterations (not committed)

- **PART-3** — `Partner` entity if Sergii's volume/complexity grows. Migration: deduplicate `partner_name` strings → create Partner records → backfill FK column. Done as separate sprint when triggered.
- **PART-4** — Automatic monthly settlement reminders / draft creation. Likely a `scheduled-tasks` job that pre-fills settlements at month-end based on previous month's pattern.
- **PART-5** — Partner-facing view (read-only access for partners to see their own settlements).

None of these are committed; surfaced for context only.

## 8. Out of scope (explicit non-goals)

- **Partner entity / agreements table** — Sergii's choice, see §3.2.
- **Automatic settlement triggering** — operator manually creates each settlement (matches today's Excel-driven cadence).
- **FX conversion / multi-currency aggregation** — see `profit-definition.md` Q3.
- **Settlement editing** — immutable + delete-recreate. See settled decision #4.
- **Partner-facing dashboard / login** — far-future. PART-1 is operator-only.
- **Settlement workflow states** (draft / approved / paid)** — single state (saved). If operator wants to mark "paid", they edit the `notes` field. PART-2 may add a `paid_at` column if PDF generation prompts the need.
- **Cross-shop partner aggregation** — partners are per-shop today. If Sergii ever wants "what did Олег earn across all shops in 2026?", that's a future feature requiring DISTINCT partner_name normalization.

## 9. Known limitations (accepted, not bugs)

1. **Snapshot pattern means historical settlements don't reflect retroactive data changes.** A receipt added in June for an April material won't change April's saved settlement. This is by design (audit integrity), and Sergii's monthly cadence makes this acceptable. If a partner challenges a settlement, operator can delete and recreate.

2. **Free-text partner names are typo-prone.** Mitigation via autocomplete + case-insensitive listing (§6.3). If duplicates accumulate, operator manually cleans up by deleting outliers and recreating with canonical names.

3. **No FX in settlement records.** Lamamarka USD partner share is stored as USD; operator manually converts at payment. If FX volatility creates pain, future `profit-definition.md` Q3 resolution.

4. **Negative settlements are visible but operator-interpreted.** UI surfaces a warning banner; doesn't auto-clamp.

5. **No partner-facing view.** Partners ask Sergii for settlement amounts; Sergii reads them from the settlements log (or, post-PART-2, generates PDFs to share). Partners don't log into OrderHub.

6. **Settlement deletion is silent (hard delete).** If Sergii deletes an incorrect settlement, there's no "trash" or recovery. Settlements are operator-controlled; mistakes are recreated, not recovered.

7. **`Net Profit` for partner share inherits whatever the FIN-1 definition is at calculation time.** If FIN-1's formula changes in a future sprint (e.g. Phase C of `production_cost` cutover), live preview reflects the new formula, but already-saved settlements retain their snapshot. Per settled decision #3.

## 10. Next steps

1. Sergii reads this doc; flags any decisions to revisit, fills in open questions where ready, adds use cases I missed.
2. Cowork iterates until ship-ready (typically 1 round if discovery captured everything; this discovery felt complete).
3. Break PART-1 into `task.md` sprint spec, run via standard AI_ONBOARDING.md workflow.
4. PART-2 (PDF) triggered by Sergii's signal after PART-1 is in use ≥1 month.

**`profit-definition.md` already created as companion document.** Reference for partner conversations and future re-visits of "what counts as profit".

---

This document lives at `docs/design/partner-payouts.md`. Update in place as decisions evolve. Like other design docs in this folder, each material update should get a short note at the top in the Status line + a Changelog section if substantive.

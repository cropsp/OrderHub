# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current task:** FIN-1-CLEANUP — Finance icon visibility + OrderCountCard zero-previous edge case
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## FIN-1-CLEANUP — Finance icon visibility + OrderCountCard edge case

### Goal

Two small follow-ups from FIN-1 smoke (2026-05-14), bundled into one
atomic commit because they're both trivial, low-risk, and on the
same feature surface. Closes the cosmetic loose ends from FIN-1
before we pivot to the Materials BOM design phase.

1. **FIN-1-followup-2:** Finance icon button on `/shops` list page is
   in DOM but visually invisible (icon colour too close to the dark
   background). Affordance fails — users find the per-shop finance
   page only via direct URL.
2. **FIN-1-followup-3:** `OrderCountCard.change_percent` returns
   `-100%` instead of `None` when both current and previous-period
   order counts are 0 (observed on KoraKlenu, which has no SHIPPED
   orders in either window). Other KPI cards correctly show
   `— no prior period data` in the same edge case.

### Behaviour rules (settled — do not relitigate)

1. **Both fixes ship in one commit, one sprint.** Don't split. The
   two changes are independent (one backend, one frontend) so order
   doesn't matter.

2. **Finance icon — match the existing palette in `ShopsPage.tsx`'s
   MANAGEMENT column.** Whatever colour the existing connectivity
   badges / status indicators / action icons use, the new finance
   link should sit in the same visual register — neither louder
   nor quieter. Don't invent a new accent colour. Don't add a
   visible text label *(e.g. "Finance →")* unless matching the
   existing convention requires it; the icon-only pattern is fine
   if the icon is visible.

3. **OrderCountCard — backend guard, not frontend.** The fix is in
   `services/finance_service.py`. Frontend already handles
   `change_percent === null` correctly (the other KPI cards prove
   this — they render `— no prior period data` correctly under the
   same data condition). Don't touch frontend logic.

4. **Don't refactor the `change_percent` calculation.** Add a guard
   for `previous == 0` to whatever function computes OrderCountCard's
   change_percent. If the existing KpiCard helper already has this
   guard, just port the pattern. **Don't extract a shared helper**
   — single use, two-line guard is fine.

5. **Don't add new tests for the icon change.** It's a CSS-class /
   colour adjustment; the existing FIN-1 frontend tests already
   render `ShopsPage.tsx` (or its descendants) and won't regress.
   For the backend guard, optionally add a small Python unit test
   that calls the helper directly with `previous=0, current=0` and
   asserts `None`. If the helper is private / awkward to test in
   isolation, skip it — the manual smoke covers it.

### Scope

- **In scope, backend:**
  - `backend/services/finance_service.py` — locate the function that
    computes `OrderCountCard.change_percent` (likely a small helper
    or inline block in `get_shop_finance`). Add the
    `if previous == 0: return None` guard. Mirror whatever the
    `KpiCard` `change_percent` calculation already does.
  - **Optional:** `backend/tests/test_finance_router.py` — if the
    helper is callable in isolation, add a Python unit test
    asserting the None return. Skip if it's deeply nested.

- **In scope, frontend:**
  - `frontend/src/pages/ShopsPage.tsx` around line 540-560 — adjust
    the finance link's icon colour (or accompanying classes) so it's
    visible against the dark row background. Match the visual
    register of other action affordances in the MANAGEMENT column.

- **Out of scope (do NOT touch):**
  - `routers/finance.py`, `schemas/finance.py` — schema is correct.
  - Other KPI card calculation logic — only `OrderCountCard`'s
    edge case.
  - `ShopFinancePage.tsx`, `FinanceKpiCard.tsx`, `DiagnosticBadge.tsx`,
    `FinanceRevenueChart.tsx` — none need changes.
  - `routers/shops.py`, `routers/orders.py` — unrelated.
  - DASH-SHOP-WARNINGS (recharts mount noise) — separate parked item,
    not in this sprint.
  - FIN-1-followup (orders URL params) — separate parked item.

### Open questions for the planner

These are trivial enough that plan-mode may be skipped — but if CC
prefers to verify them via grep before editing, that's also fine.

1. **Exact location of the `change_percent` calculation.** Grep
   `change_percent` under `backend/services/`. Probably a 3-5 line
   helper or inline block. Identify which one applies to
   `OrderCountCard` (vs. `KpiCard`). Confirm the existing `KpiCard`
   helper already guards `previous == 0`; if yes, port the pattern;
   if no, surface that as a parallel bug *(in which case fix both
   in this sprint — minor scope expansion that's clearly the same
   bug class)*.

2. **Icon palette in `ShopsPage.tsx`.** Grep for other action-icon
   links / buttons in the MANAGEMENT column (or nearby in the same
   row component). What colour utility class do they use? Match it.
   If the row has no other action icons today, fall back to one of
   the existing connectivity-badge accent colours
   (`text-teal-400`, `text-zinc-300`, whatever is in use).

### Verification

- **Backend gates:**
  - `cd backend && python -m pytest tests/ -v` — must pass clean.
    Expected: same 121 passing (no test count change unless the
    optional unit test is added; if so, 122).

- **Frontend gates:**
  - `cd frontend && npx tsc --noEmit` — clean.
  - `cd frontend && npm run lint` — clean for the changed file.
  - `cd frontend && npm run test -- ShopFinancePage` — still 4/4
    passing (no regression).

- **Manual smoke (Cowork via browser MCP):**
  1. Navigate to `/shops`. **Finance icon button is now visible**
     for each shop row. Zoom verification — the icon renders with
     non-zero contrast against the dark background.
  2. Click the icon for KoraKlenu → lands on
     `/shops/<KoraKlenu UUID>/finance`. (Sanity check the link
     still works.)
  3. On KoraKlenu finance page, ORDER COUNT card shows
     `0` with subtitle `— no prior period data` (NOT
     `↓ 100.0% vs previous period`). Matches the other KPI cards'
     behaviour in the same edge case.
  4. Cross-check Lamamarka finance page — ORDER COUNT still shows
     `2` with `— no prior period data` (because previous-period
     count is 0 there too, current is 2; the existing behaviour
     was correct, fix should not regress it).

### Workflow

- **Plan mode is optional.** Both changes are trivial and the spec
  is concrete. CC may skip plan mode and edit directly **if** the
  grep confirmations from §Open Questions match the spec. If
  anything diverges (e.g., `KpiCard.change_percent` also lacks the
  guard, or `ShopsPage.tsx` doesn't have any reference icons to
  match), fall back to plan mode and surface the divergence.
- After edits: run backend pytest + frontend typecheck + lint, then
  commit.
- Commit: `fix(finance): cleanup — icon visibility + zero-previous edge case`
- Do **NOT** update `implementation_plan.md` or `task.md` post-fix
  notes — Cowork writes those after smoke verification.

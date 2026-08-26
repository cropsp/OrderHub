# Order Cases — design plan (CASE-1)

**Status:** settled design, approved by Sergii 2026-08-26; task.md to be written after `WB-POLL-CADENCE` closes
**Origin:** Cowork chat 2026-08-26, refining `OrderHub-parcel-watchlist-spec-2026-08-26.md` (uploaded draft). The parcel-automation half of that spec is a **separate, later track** — see § Relation to the parcel-watchlist track.

## 1. Problem

Problem orders today are tracked in heads and in Gmail. Real example (Aug 2026): order shipped → returned to sender → customer left a 1★ review → we contacted them, offered a reship → waiting on address confirmation → reship. None of these steps exists in OrderHub; nothing reminds the manager mid-thread, and nothing shows "what are we resolving right now vs. what is waiting" on one surface.

This is **not** parcel tracking (that exists at `/westernbid` + dashboard alerts for the NovaPost population). It is a lightweight per-order case log: a human workflow object with a timeline, a state, and a deadline.

## 2. Settled decisions (do not relitigate in planning)

All four were explicit choices by Sergii on 2026-08-26:

1. **Granularity: case with timeline.** An order can carry several cases (a return and, separately, a review), each with its own state and its own append-only note stream. Not a single "problem" flag, not bare notes.
2. **States: `in_progress` / `waiting` / `resolved`.** `waiting` = ball is not in our court (customer reply, carrier, claim). No separate "new/triage" state.
3. **Deadlines: yes, one `due_at` + `next_action` text per case.** Overdue cases surface at the top of the dashboard block. This absorbs the "Promise" entity from the parcel-watchlist spec — a written commitment to a customer is a case (or a note on one) with a due date; no separate Promise table.
4. **Types: short enum + other.** `return`, `lost_parcel`, `reship`, `review`, `address_issue`, `claim`, `other`. Gives dashboard filtering and future stats (returns per quarter etc.). Claims are a case type in v1, not a table.

Role default (Cowork recommendation, accepted with the plan): create/edit by OWNER/MANAGER; DESIGNER read-only at most, consistent with other operational surfaces. Flag in task.md as confirmable, not open.

## 3. Data model sketch

Two tables, no dependency on the wb_* tracking infrastructure.

```
order_case
  id                UUID PK
  order_id          FK -> orders, NOT NULL, ON DELETE CASCADE
  case_type         enum: return | lost_parcel | reship | review
                          | address_issue | claim | other
  title             varchar — short free-text headline
  status            enum: in_progress | waiting | resolved
  next_action       text nullable — "what happens next", shown on dashboard row
  due_at            timestamptz nullable — deadline / come-back-to-it date
  owner_id          FK -> users nullable
  created_by        FK -> users
  resolved_at       timestamptz nullable
  resolution_note   text nullable — optional summary at close
  created_at, updated_at

order_case_note      (append-only, the order_status_history pattern)
  id                UUID PK
  case_id           FK -> order_case, ON DELETE CASCADE
  author_id         FK -> users
  text              text
  created_at
```

Semantics worth writing down:

- **Notes are append-only** — no edit/delete in v1. The timeline is the record.
- **Overdue `waiting` does not auto-transition.** It sorts to the top with red highlight. No new scheduler logic; the dashboard query does the work.
- **`resolved` keeps the case readable forever** in the order card; the dashboard shows only non-resolved.
- **State changes should be visible in the timeline.** Cheapest honest option: writing a status change also appends a system-authored note ("status → waiting"); whether that is a note row or a rendered event from `updated_at` diffing is a planner question, but the timeline must show it one way or another.

## 4. UI

Two surfaces, exactly as requested:

- **Order card:** a new sub-component in `frontend/src/components/orders/detail/` (the existing 8 are a settled refactor — do not merge or modify them). Case list with status/type/due badges; a case expands to its note timeline + add-note input; "+ питання" button opens a minimal create form (type, title, optional due/next action).
- **Dashboard:** a "Питання по замовленнях" block alongside the existing WB parcel-alerts block (same collapsible pattern, same quiet all-clear line). Two groups: **В роботі** (overdue-first, red) and **Чекаємо** (with due date shown). Row: order ref, customer, type, title, next_action, due countdown, owner. Click → order card. Count badge on the block header.

The WB-ALERTS-1 lesson applies verbatim: the surface people already open daily is the dashboard, and the block must stay honestly short — it lists open cases, not history.

## 5. Access control & conventions

- Cases are strictly order-scoped ⇒ shop scope resolves through the order via the existing `access_service` path — read `docs/design/access-control.md` before touching the routers. New routes must be classified for `tests/test_route_scope_completeness.py`.
- No money fields ⇒ nothing for `test_money_field_completeness.py`, but state it in the plan rather than assume it.
- Alembic migration with round-trip verification (`upgrade head && downgrade -1 && upgrade head`); two new enums must match DB enum types exactly per CLAUDE.md DB conventions.
- MCP surface: out of scope for v1; note in task.md so the planner doesn't gold-plate.

## 6. Relation to the parcel-watchlist track (parked, separate)

The uploaded spec's automation half stays a distinct backlog with its own sequencing, agreed 2026-08-26 (research inputs: `docs/design/parcel-watchlist-research-2026-08-26.md`):

1. `UKRP-TRACK-1` — Ukrposhta StatusTracking ingestion into the (generalised) wb_* tracking/alert infra. Blocked on Sergii obtaining the separate StatusTracking bearer from the Ukrposhta manager (contract exists; key does not). Ask the manager: fee? which product is the `LP` prefix (PRIME or not)? rate limit?
2. `HOLD-1` — held-for-pickup return-to-sender countdown from a per-carrier config table (calendar vs business days + clock-start rules matter; verified table in the research doc).
3. `STAGE-1` — stage normalisation + per-stage stale thresholds as new alert kinds on `wb_parcel_alert`.
4. Later: alert→case linkage ("create case from alert" button) — the bridge between the two tracks. Node/partner incident counters stay ad-hoc SQL in the weekly parcel-health review until volume justifies more.

Aggregator decision: **not buying**; free NP feed already passes through US last-mile scans, and Ukrposhta's official API returns full history. Optional free 10-parcel diff test against 17TRACK's free quota before UKRP-TRACK-1 if we want the evidence.

## 7. CASE-1 scope (for the future task.md)

- **In:** the two tables + migration, CRUD routes (list by order, create, update status/fields, add note), order-card section, dashboard block, pytest + vitest coverage, route-scope classification.
- **Out:** MCP tools, email/Gmail linkage, auto-creation from parcel alerts, notifications/digests, edit/delete of notes, any wb_* changes.
- CC runs on Opus high effort; open questions in task.md should demand cited evidence (file:line) per the §8 onboarding template.

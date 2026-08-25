# Weekly parcel-health review — 2026-08-24

Automated Cowork run (scheduled Mon 10:00, agreed 2026-08-20 — replaces the one-off
no_data checkpoint). First weekly of the series: **comparison baseline is the
2026-08-20 checkpoint** (`docs/reviews/2026-08-20-wb-track-no-data-checkpoint.md`),
since no prior `weekly-parcel-health-*.md` exists. SQL below is ready to run, not run —
Cowork has no prod DB access. Findings get filled in when CC's output comes back.

## Baseline (2026-08-20)

- States: **71 delivered / 24 moving / 0 problem / 2 no_data / 7 untracked / 19 needs-attention**.
- Stub codes seen to date: **80, 81, 122** (81 was new on 08-20). Recovery ceiling 5.0 days dark.
- Composition concern: overdue-moving was **17/24 = 71% of in-flight**, many suspected
  "arrived, awaiting collection" (`WB-TRACK-ARRIVED-STATE` + `WB-2` are the levers).
- **WB-ALERTS-1 is LIVE since 2026-08-20** (closure in `implementation_plan.md`): table
  `wb_parcel_alert`, kinds `overdue_long` (7d) / `untracked_aging` (14d) / `no_data_stuck`
  (6d) / `delivery_problem`; launch wave was **16 alerts (8 overdue_long / 7 untracked_aging /
  1 no_data_stuck — `59500007135457`)**. Dismissal semantics: a dismissed alert's row stays
  open in the DB (`resolved_at` NULL) but leaves the UI; auto-resolution records
  cleared/aged_out. Dismissing the launch wave was left to Sergii — **whether anyone has
  dismissed anything is a first-class question this week.**

## Checked from the repo alone (this run)

- `implementation_plan.md`: WB-ALERTS-1 closed/deployed 2026-08-20; weekly review noted as
  its follow-on process. No newer WB-* closures since.
- `docs/reviews/`: no weekly report exists yet; this is #1.
- Choice made (noted per automated-run rules): exact `wb_parcel_alert` column names are not
  in the docs I can read, so the alerts section opens with `\d wb_parcel_alert` and CC
  should adapt column names (dismissed_by/dismissed_at vs similar) accordingly.

## SQL for CC (prod, read-only — `ssh orderhub`)

```bash
ssh orderhub
cd ~/OrderHub
docker compose -f docker-compose.prod.yml exec -T postgres psql -U crm -d crm_db
```

### 1. State distribution (compare against 71/24/0/2 + 7 untracked)

```sql
SELECT CASE
         WHEN status_code IN ('9','10','11') THEN 'delivered'
         WHEN no_data_since IS NOT NULL     THEN 'no_data'
         WHEN status_code IN ('2','99','102','103','104','105','110','111',
                              '112','113','116','117','118','123') THEN 'problem'
         ELSE 'moving'
       END AS state,
       COUNT(*)
FROM wb_parcel_tracking
GROUP BY 1 ORDER BY 1;

-- Retired parcels and how they left:
SELECT stopped_reason, COUNT(*) FROM wb_parcel_tracking
WHERE polling_stopped_at IS NOT NULL GROUP BY 1;

-- Untracked = wb_parcel rows with no tracking row; flag those older than 14 days:
SELECT COUNT(*) AS untracked,
       COUNT(*) FILTER (WHERE p.wb_created_at < now() - interval '14 days') AS untracked_14d_plus
FROM wb_parcel p
LEFT JOIN wb_parcel_tracking t ON t.shipment_id = p.shipment_id
WHERE t.shipment_id IS NULL;
```

### 2. no_data behaviour

```sql
-- Currently dark, with age; >6 days = alert threshold (recovery ceiling ever seen: 5.0d):
SELECT tracking_number,
       round(EXTRACT(epoch FROM (now() - no_data_since))/86400, 1) AS days_dark,
       status_code, status_text AS last_resolved_status, np_scheduled_delivery_at
FROM wb_parcel_tracking
WHERE no_data_since IS NOT NULL
ORDER BY no_data_since;

-- Stub codes since the 08-20 baseline — anything beyond 80/81/122 is NEW:
SELECT status_code AS stub_code, COUNT(*) AS times,
       min(observed_at) AS first_seen, max(observed_at) AS last_seen
FROM wb_tracking_event
WHERE status_text IS NULL AND observed_at >= '2026-08-20'
GROUP BY 1 ORDER BY 1;
```

### 3. Genuinely stuck parcels

```sql
-- Problem-state parcels (expect ~0; list them if any):
SELECT tracking_number, status_code, status_text, last_polled_at
FROM wb_parcel_tracking
WHERE status_code IN ('2','99','102','103','104','105','110','111',
                      '112','113','116','117','118','123')
  AND no_data_since IS NULL AND polling_stopped_at IS NULL;

-- Overdue split: total overdue-moving (baseline 17) and the >7d tail (alert threshold):
SELECT COUNT(*) AS overdue_moving,
       COUNT(*) FILTER (WHERE np_scheduled_delivery_at < now() - interval '7 days') AS overdue_7d_plus
FROM wb_parcel_tracking
WHERE (status_code NOT IN ('9','10','11') OR status_code IS NULL)
  AND no_data_since IS NULL AND polling_stopped_at IS NULL
  AND np_scheduled_delivery_at < now();
```

### 4. Alerts (WB-ALERTS-1, live since 08-20)

```sql
\d wb_parcel_alert
-- Adapt column names below to what \d shows (dismissed_by/dismissed_at assumed).

-- Open alerts by kind (launch wave was 16: 8 overdue_long / 7 untracked_aging / 1 no_data_stuck):
SELECT kind, COUNT(*) FROM wb_parcel_alert WHERE resolved_at IS NULL GROUP BY 1;

-- Activity since launch: new alerts, auto-resolutions by reason:
SELECT kind, COUNT(*) FILTER (WHERE created_at >= '2026-08-20') AS new_since_0820,
       COUNT(*) FILTER (WHERE resolved_at >= '2026-08-20') AS resolved_since_0820
FROM wb_parcel_alert GROUP BY 1;
SELECT resolution, COUNT(*) FROM wb_parcel_alert
WHERE resolved_at IS NOT NULL GROUP BY 1;

-- THE dismissal question — if this returns 0 rows, nobody has touched the dashboard
-- surface and it is failing exactly the way /westernbid did. Say so in Findings.
SELECT kind, COUNT(*), min(dismissed_at) AS first, max(dismissed_at) AS last
FROM wb_parcel_alert WHERE dismissed_at IS NOT NULL GROUP BY 1;
```

## Hand this to Claude Code

> Weekly parcel-health review 2026-08-24: run the SQL in
> `docs/reviews/weekly-parcel-health-2026-08-24.md` § "SQL for CC" against prod
> (read-only, via `ssh orderhub`, psql as documented in the file). In section 4, run
> `\d wb_parcel_alert` first and adapt the assumed column names (`dismissed_at`,
> `resolution`, `created_at`) to the real schema before running the alert queries.
> Paste raw outputs back; do not interpret or change anything — analysis happens in
> the Cowork session.

## Findings — queries run by CC on prod 2026-08-24 (read-only)

**Schema correction for future runs:** `wb_parcel_alert` has **`raised_at`**, not `created_at`
(also `last_seen_at`, `dismissed_by_id` → `users(id)`, `detail`; unique index
`uq_wb_parcel_alert_open`). Next week's SQL should use `raised_at` directly.

### 1. State distribution

| state | 08-20 | 08-24 | Δ |
|---|---|---|---|
| delivered | 71 | **78** | +7 |
| moving | 24 | **24** | 0 |
| problem | 0 | **1** | +1 |
| no_data | 2 | **11** | +9 |
| untracked | 7 | **7** | 0 |
| tracked total | 97 | 114 | +17 |

Throughput is healthy: +17 parcels entered tracking, +7 delivered. All 78 delivered rows
retired with `stopped_reason='delivered'`; **zero `aged_out`** — the 60-day retirement has
still never fired.

**The +9 no_data is one event, not a trend.** Nine parcels went dark **simultaneously
0.9 days ago** — eight last read code 119 "В процесі митного оформлення", one code 5.
All nine have scheduled delivery **in the future** (08-26 … 08-31), so none is late; this
is the familiar episodic feed blindness, now hitting at the *customs-processing* stage
rather than the 08-06 handoff signature. **Falsifiable prediction for next week: if the
5.0-day recovery ceiling holds, all nine are resolved by ~2026-08-27.** If any survives
past 6 days, the "self-clearing transient" model needs revisiting.

Corrected attention load: raw needs-attention is 17 overdue + 11 no_data + 1 problem =
**29 vs 19 at baseline (+53%)** — but strip the fresh 0.9-day batch and it is **20 vs 19,
i.e. flat**. The badge number overstates the real backlog; the batch is noise passing through.

### 2. no_data — one genuine outlier, no new stub codes

- **`59500007135457` — 14.7 days dark.** This is *the* parcel the 2026-08-20 review singled
  out by hand at 9.7d, and that WB-ALERTS-1 independently selected as its single
  `no_data_stuck` alert on launch day. It is now **~3× the observed recovery ceiling (5.0d)**,
  its scheduled delivery (2026-08-06) is 18 days past, and it last read code 120
  "Митне оформлення завершено". **The 08-20 action item — have the manager look it up in the
  WB cabinet — was not done.** Everything else about the self-clearing model still holds
  (43/45 historical recoveries), but this parcel is now the first case that plainly does not
  fit it, and it has been visible and un-acted-on for two weeks.
- **Stub codes: 122 (19×) and 81 (7×). Nothing new** beyond the known 80/81/122; code 80 did
  not appear at all this week.

### 3. Genuinely stuck

- **Problem: 1 — `59500007140095`, code 102 "Відмова від отримання"** (recipient refused).
  First problem-state parcel since baseline 0, and a real human-action case: refusal means a
  return to handle and a customer to contact. Its `delivery_problem` alert is open and
  untouched. This is precisely the case WB-ALERTS-1 was built to surface, and the surface
  produced no action.
- **Overdue: 17 (unchanged), but the tail has aged — 13 of 17 are now >7 days** vs 8 at
  launch. The overdue population is **sitting still, not churning**: the same parcels are
  getting older rather than being replaced. Overdue-moving is 17/24 = **71% of moving —
  identical ratio to baseline**, so `WB-TRACK-ARRIVED-STATE` / `WB-2` remain the right
  levers; nothing new argues against that prioritisation.
- **Untracked: 7, all >14 days** — the known permanent UPS/USPS backlog, unchanged.

### 4. Alerts — the headline finding: **zero dismissals**

Open: **23** (14 `overdue_long`, 7 `untracked_aging`, 1 `no_data_stuck`, 1 `delivery_problem`)
— up from 16 at launch. Raised since 08-20: 24. Resolved since 08-20: **1** (an
`overdue_long`, auto-`cleared`). **Dismissals: 0 rows. Nobody has touched a single alert.**

**Cause established 2026-08-25 (Sergii) — this is NOT the `/westernbid` failure repeating.**
Day-to-day order handling has **not yet migrated into OrderHub**; the CRM is still running as a
mirror alongside the existing process, so nobody is opening the dashboard as part of their work
yet. Zero dismissals is therefore expected, not a UX verdict — and future weeklies should not
re-raise it as one until migration lands. What the number *is* good for: it fixes the
pre-migration baseline (23 open / 1 auto-cleared / 0 touched), so the first week after migration
has something to be compared against.

The alerts themselves proved their worth this week regardless: both parcels investigated by hand
below were selected by the alert mechanism, and **both turned out to be real** — one physically
stuck, one a genuine address failure.

**Structural note worth recording:** `untracked_aging` (7 alerts, 30% of the open set) has
**no self-clearing path** — no tracking data will ever arrive for those parcels, so the
condition never disappears. They can only leave via dismissal or the 60-day age-out. If
dismissal never happens, that third of the list is permanent visual debt that trains the
operator to ignore the whole block. The auto-clear mechanism works (1 clearance proves it),
but it cannot rescue this kind.

### 5. Verdict for the week

Tracking mechanics are sound — classification, auto-resolution and age-out all behave as
designed, and no new failure mode appeared in the data. **The problem this week is human, not
technical:** three real action items (dark 14.7d parcel, refused parcel, 13 aging overdue) are
correctly identified by the system and nobody has looked at them. Before building anything
further on top of the alerts, the open question is whether the dashboard block is *seen*.

## Proposed edits to implementation_plan.md (not made — Cowork+Sergii own that file)

1. `WB-ALERTS-1` closure entry: append a first-week outcome line — 23 open / 1 auto-cleared /
   **0 dismissed**, and the `untracked_aging`-never-self-clears observation.
2. Consider a new small row, e.g. `WB-ALERTS-2`: `untracked_aging` needs either a dismissal
   nudge, a separate collapsed group, or suppression after first acknowledgement — it cannot
   auto-clear by construction.
3. `WB-TRACK-NO-DATA-TERMINAL` (closed): add a one-line footnote that `59500007135457` reached
   14.7d, ~3× the recovery ceiling the closure was based on — the closure stands, this is the
   documented exception.
4. `WB-TRACK-ARRIVED-STATE` / `WB-2`: unchanged priority; the 71%-of-moving ratio held steady,
   and the >7d tail deepening (8 → 13) mildly strengthens the case.

---

## Addendum 2026-08-25 — both action-item parcels investigated (Sergii, WB cabinet + NP site)

### `59500007135457` — genuinely stuck, not a feed artefact

**Reading the WB cabinet correctly matters here.** It shows two timestamps that are easy to
invert: **«Дані статусу»** is the time of the newest *event*, **«Останнє оновлення статусу»** is
merely when WB last *polled*. For this parcel: event 09.08 22:42, poll 25.08 10:46. The
today-looking date is the poll. Confirmed on the sibling parcel below, where «Дані статусу»
21.08 19:43 matches its newest route event exactly.

Newest event is **"The plane arrived at New York", 2026-08-09 22:42 — then nothing for 16 days.**
The comparison that sizes the anomaly: sibling parcel `59500007140095` flew the same route and
went from NY arrival to the US delivery partner (GoFo Express) in **~2 days**. This one has sat
at that step for 16.

**So the `no_data_stuck` alert was right, and right for the right reason** — the parcel really is
stuck, not merely invisible. Scheduled delivery was 2026-08-06; contents $45.99; recipient Nicole
Nehring (Beaverton, MI). Action: open an inquiry with WesternBid (sender of record) and write to
the customer, who has been waiting three weeks.

**Mirror-completeness defect found while checking this** (→ new backlog row): our DB's last
resolved status is code **120** "Митне оформлення завершено" (09.08 13:50), but NP's own site
shows **two later events the same day** — "Cleared customs, in transit" 19:02 and the 22:42 plane
arrival. We went dark *after* 13:50 and never recorded the final two. Whether the API returns
fewer events than the cabinet, or we simply stopped polling in between, is unknown and worth one
cheap check — every weekly report rests on this mirror being complete.

### `59500007140095` — bad address, not a refusal

Root cause confirmed by Sergii with the manager 2026-08-25: **the manager created the parcel
against the old address** despite having the correction — a human slip, not a system fault.
Shipped to `8036 Canonbury Dr, CHICAGO, IL 60617`; the customer's correction (2026-08-19) gives
the same street at **Nolensville, TN 37135**. Undeliverable → depot Carteret NJ 14.08 → Return
registered 21.08 19:43.

**Our label misdescribes it.** NP code 102 renders as "Відмова від отримання" (recipient
refusal), but the recipient never refused anything — the parcel could not reach him. An operator
reading the alert would contact the customer about the wrong thing (→ new backlog row on the
label).

Resolution chosen: **do not wait for the return** — reship to the corrected address once the
customer re-confirms it. Customer email sent 2026-08-25 asking him to confirm the full address
and **the recipient name** (NP has "Daniel Frazier", the reply is signed "Frederick Berry", same
mailbox `rerun2k@gmail.com`).

**Product point worth keeping:** this is exactly the failure `ADDR-VAL-1/2` was built to catch —
a plausible-looking US address whose street does not exist in the stated city. The feature is
built and deployed; the order never passed through it, because the workflow has not migrated
into OrderHub yet. This is an argument for migration, not a new defect.

---

## CC investigation 2026-08-25 — `WB-TRACK-EVENT-COMPLETENESS`: verdict **(a) systematic**

Read-only, no code written. Full record in `implementation_plan.md` →
`WB-TRACK-EVENT-COMPLETENESS`; the operative conclusions for this report:

**The Nova Poshta keyless API carries no history whatsoever.** `getStatusDocuments` returns a
single flat current-status record. Live response for `59500007135457` — 9 keys, `StatusCode: "81"`,
empty `Status` — at the same moment NP's public page showed all 11 events. Across 36 in-flight
parcels: no non-empty list or dict field in any record; the only array keys are empty and none is
a route list. Five candidate history methods all answer `success: false, "User is undefined"`.
**One method exists on the keyless surface and it is current-status only.**

So `wb_tracking_event` is **a poll-sampled approximation, not a mirror**. Three mechanisms thin it:

| # | mechanism | whose | evidence |
|---|---|---|---|
| 1 | API carries no history | NP's | structural, above |
| 2 | **poll runs once a day** (`scheduler.py:463-470`, `interval, days=1`) | **ours** | GoFo handover 17:37 → depot 17:47, 10 min apart, only one survived |
| 3 | API lateness / omission | NP's | 41 min after the 09.08 19:02 event it still returned 13:50; **the 14.08 Carteret NJ arrival never appeared across nine consecutive polls** |

That last line is what rules out the benign explanation — neither a stub window nor a poll gap can
account for it.

**Attribution, because the intuitive reading of the table is wrong.** Of the 16 events missed
across the two hand-diffed parcels: **stub windows 9 (56%)**, API lateness 3, API omission 1,
**cadence 3 (19%)**. Our own daily poll is the *smallest* of the three mechanisms, not the
largest — fixing it would not have recovered the other 13. The case for `WB-POLL-CADENCE` rests
on **freshness** instead: 41.6% of all 418 recorded events were 6–24h stale when first seen,
i.e. exactly one poll cycle late, which is the one term cadence controls.

**Measured density:** cabinet 11 events vs mirror 1 (`…135457`); cabinet 9 vs mirror 3
(`…140095`); fleet-wide 114 parcels / 519 events, mean 4.55 per parcel, **0.64–0.97 events/day**,
sitting at the 1/day cadence ceiling.

**Caveat on the "⅓ of ground truth" figure — it is an estimate, not a measurement.** It compares
our fleet rate against **one parcel's busiest leg** (`…135457`, 11 cabinet events in ~4 days ≈
2.75/day, a customs-and-transfer stretch). Events cluster in bursts, so a lifecycle average is
much lower than a burst rate. The delivered control `59500007140177` gives **0.83 events/day —
but that is our stored count, and it was never diffed against its own cabinet history**, so it
measures our ceiling, not the loss. **The true fleet-wide ratio is unmeasured.** Treat "~⅓" as an
order-of-magnitude indication of loss during active legs, and note that a cheap way to firm it up
is diffing two or three full lifecycles against the cabinet, not more aggregate arithmetic. Where an event *was* captured, its timestamp matches the cabinet to the minute: the
mirror is accurate about what it holds, it simply holds less.

### What this changes about the numbers in this report

- **State counts (78/24/1/11 + 7) are unaffected.** They read the current row in
  `wb_parcel_tracking`, and a parcel's present status is as true as the feed itself.
- **Everything derived from `wb_tracking_event` is a FLOOR:** the 5.0-day `no_data` recovery
  ceiling (a dark spell that opened and closed inside one poll gap never entered the sample),
  the 80/81/122 stub inventory (lower bound on both vocabulary and frequency — a fourth code
  may exist unobserved), and per-parcel event counts. **Future weeklies must quote these as
  floors, not measurements.**
- **The 2026-08-20 verdict still stands.** 43 recoveries out of 45 is not a marginal call, and
  the >6d `no_data_stuck` threshold is if anything conservative given the floor.

### Correction owed

The phrase "the 4h poll" in the original backlog row and in `task.md` was **Cowork's error** —
conflated with `NP-FIX-5`'s *designed* 4h domestic batch, which was never built. The WB poll has
always been daily. CC flagged it because the cadence half of the finding is invisible while that
premise stands. Follow-up filed: **`WB-POLL-CADENCE`** (change `days=1` → `hours=4`; one line,
six keyless requests a day, unblocks `WB-TRACK-1-followup-1` which cannot be answered at the
current sampling rate).

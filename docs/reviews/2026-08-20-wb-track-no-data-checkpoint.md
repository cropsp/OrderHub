# WB-TRACK no_data review checkpoint — 2026-08-20

Scheduled review agreed 2026-08-06 (see `WB-TRACK-NO-DATA-TERMINAL` in
`implementation_plan.md`). Written by Cowork in an automated session — Sergii was not
present, so the SQL below is **ready to run, not yet run**. Nothing was implemented and
`implementation_plan.md` was not edited; proposed edits are at the end.

## The question this settles

On 2026-08-06 six parcels went dark simultaneously (stub responses, codes 80/122), taking
`no_data` from 1 to 7. Hypothesis: NP stops resolving an export once the US carrier takes
over — i.e. `no_data` is a **normal terminal state**. If true, the attention group bloats
weekly and an arrived parcel sits flagged forever.

**The decisive test: has any parcel that went dark ever returned to a live status?**
One recovery falsifies the terminal hypothesis. Two weeks of `wb_tracking_event` data now
answer this.

## What I could answer without the DB

**Q5 — the WesternBid investigation is DONE (2026-08-06),** recorded in the
`WB-TRACK-NO-DATA-TERMINAL` backlog row:

- Across 109 parcels / 45 days, **no parcel ever carries more than two tracking
  elements** — each shipping type gets its carrier number at creation and never gains
  another. There is **no onward US-carrier number available from any source we have.**
- WB's status vocabulary is creation-time only (`Parcel created` ×101, `Sent from Ukraine
  warehouse` ×6, `Parcel canceled` ×2); zero parcels have a live WB status differing from
  our 3-day mirror. A *delivered* control parcel still read `Parcel created` four days
  after NP recorded delivery. **WB never learns the outcome**; widening
  `WB_POLL_WINDOW_DAYS` would gain nothing.
- Consequence: a third-party aggregator (17track / AfterShip) is the **only** data-bearing
  option, and it would also cover the 7 permanently-untracked UPS/USPS parcels.

**A mitigation already exists and bounds the "accumulates forever" fear:**
`WB_TRACKING_MAX_AGE_DAYS = 60` — `classify_parcels` skips parcels with `wb_created_at`
older than 60 days and polling retires them (`stopped_reason='aged_out'`). So `no_data`
accumulates for **up to 60 days per parcel**, not forever. Still bad — worst observed
transit is 31.3d (p90 11.4), so a dark parcel wrongly occupies the attention list for
roughly a month after any plausible arrival.

**One detection caveat for reading the results.** While a parcel is dark, its row keeps
the last *resolved* `(status_code, status_text)`. If it recovers with the *identical*
status, `no_data_since` is cleared but **no event is written** — so recoveries must be
detected from the current-state table (query 2a), not from events alone. Query 2b catches
the stronger case (status advanced after dark). Going dark itself always writes exactly
one event with `status_text IS NULL` and the stub code — that is the marker used below.

## SQL for Sergii (or hand to CC — prod DB, via `ssh orderhub`)

```bash
ssh orderhub
cd ~/OrderHub
docker compose -f docker-compose.prod.yml exec -T postgres psql -U crm -d crm_db
```

### 1. State distribution today (vs 2026-08-06 baseline: 24 delivered / 45 moving / 1 problem / 7 no_data / 7 untracked / 20 needs-attention)

```sql
-- Mirrors classify_parcels precedence (wb_tracking_service.py:561-573).
-- Untracked (no NP number) is not in this table — read it off /westernbid.
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

-- How many have been retired by the 60-day age-out, and in which state they left:
SELECT stopped_reason, COUNT(*)
FROM wb_parcel_tracking
WHERE polling_stopped_at IS NOT NULL
GROUP BY 1;
```

### 2. THE decisive queries — did any dark parcel ever come back?

```sql
-- 2a. Every parcel that ever went dark, and where it stands now.
--     no_data_since IS NULL on any row  ⇒  it RECOVERED  ⇒  hypothesis FALSIFIED.
--     All rows still dark (or aged_out while dark)       ⇒  hypothesis HOLDS.
SELECT t.tracking_number,
       min(e.observed_at) FILTER (WHERE e.status_text IS NULL) AS first_went_dark,
       max(e.observed_at) FILTER (WHERE e.status_text IS NULL) AS last_went_dark,
       t.no_data_since,          -- NULL = currently resolved (recovered)
       t.status_code, t.status_text,   -- last RESOLVED status (kept through darkness)
       t.stopped_reason, t.np_delivered_at
FROM wb_parcel_tracking t
JOIN wb_tracking_event e USING (tracking_number)
WHERE e.status_text IS NULL
GROUP BY t.tracking_number, t.no_data_since, t.status_code, t.status_text,
         t.stopped_reason, t.np_delivered_at
ORDER BY first_went_dark;

-- 2b. Stronger evidence: any LIVE event observed after a parcel first went dark
--     (status actually advanced post-darkness).
SELECT e.tracking_number, e.status_code, e.status_text, e.observed_at
FROM wb_tracking_event e
WHERE e.status_text IS NOT NULL
  AND e.observed_at > (SELECT min(e2.observed_at)
                       FROM wb_tracking_event e2
                       WHERE e2.tracking_number = e.tracking_number
                         AND e2.status_text IS NULL)
ORDER BY e.tracking_number, e.observed_at;

-- 2c. Growth rate: parcels entering no_data per day over the two weeks.
SELECT date(observed_at) AS day, COUNT(DISTINCT tracking_number) AS went_dark
FROM wb_tracking_event
WHERE status_text IS NULL
GROUP BY 1 ORDER BY 1;
```

### 3. Attention-list composition — is no_data over half?

```sql
-- Overdue among moving (stalled was a strict subset of overdue on both snapshots).
-- Needs attention ≈ problem + no_data + this count. Baseline: 1 + 7 + 12 = 20.
SELECT COUNT(*) AS overdue_moving
FROM wb_parcel_tracking
WHERE (status_code NOT IN ('9','10','11') OR status_code IS NULL)
  AND no_data_since IS NULL
  AND polling_stopped_at IS NULL
  AND np_scheduled_delivery_at < now();
```

### 4. Stub codes seen (known: 80, 122; anything new?)

```sql
SELECT status_code AS stub_code, COUNT(*) AS times,
       min(observed_at) AS first_seen, max(observed_at) AS last_seen
FROM wb_tracking_event
WHERE status_text IS NULL
GROUP BY 1 ORDER BY 1;
```

### 5. Age of currently-dark parcels, and what they last reported

```sql
SELECT tracking_number,
       round(EXTRACT(epoch FROM (now() - no_data_since))/86400, 1) AS days_dark,
       status_text AS last_seen_status,
       np_scheduled_delivery_at
FROM wb_parcel_tracking
WHERE no_data_since IS NOT NULL
ORDER BY no_data_since;
```

## Questions for the manager (the other half of this checkpoint)

Two weeks of real use of `/westernbid` — please ask/relay:

1. Which group do they actually act on — overdue, problem, no_data, untracked? What
   action follows (nudge customer / check WB cabinet / nothing)?
2. Is the no_data group read as "something is wrong" or already ignored as noise?
3. Did the "arrived, awaiting collection" pattern (`WB-TRACK-ARRIVED-STATE`) come up —
   are they nudging customers, and did the missing order/email link (`WB-2`) block that?
4. Anything missing that sent them back to the WB cabinet anyway?

## Recommendation on WB-TRACK-NO-DATA-TERMINAL (conditional on query 2)

**If no parcel ever recovered (expected):** the hypothesis is confirmed — `no_data` is
the normal end of NP's visibility at the US-carrier handoff, not an anomaly. Then:

- **Split expected-vs-unexpected, keyed on the last resolved status + age.** A dark
  parcel whose last status was "Відправлення прямує до \<city\>" (the handoff signature,
  all six of 2026-08-06) after a short grace (~2–3 days dark) becomes **"handed off — NP
  visibility ended"**: its own collapsed group, out of Needs attention. A parcel that went
  dark from any *other* status, or before reaching the destination leg, stays flagged —
  that is the genuinely anomalous residue (today: only `59500007112662` / code 80).
- **Add the manual "resolved" action** as the cheap complement for the residue — one
  column (`resolved_by` / `resolved_at` or reuse `polling_stopped_at` with a new
  `stopped_reason='manual'`), one button. Age-out **alone** is the wrong tool: 60 days is
  calibrated to transit time, not attention span, and a pure age-out would also silently
  hide a genuinely lost parcel.
- **Do not** shorten the 60-day poll retirement — polling a dark parcel is nearly free
  (one batched keyless request) and is the only way query 2 keeps collecting evidence.

**If even one parcel recovered:** the terminal story is wrong or incomplete — `no_data`
is (at least sometimes) transient. Then splitting by status-signature is unsafe; prefer
the manual "resolved" action only, keep the group in Needs attention, and re-review after
another two weeks with the recovery cases in hand.

**Either way,** the accurate-truth path remains the aggregator (17track/AfterShip): it is
the only option that can ever say "delivered" for these parcels and would close the 7
untracked UPS/USPS ones too. Worth a separate cost/benefit decision, not part of this fix.
Sequencing note: `WB-2` (order↔parcel matching) is waiting on this decision and is what
turns "arrived, nudge the customer" from a dead end into an action.

## VERDICT — 2026-08-20, queries run by CC on prod (read-only)

**The terminal hypothesis is FALSIFIED, decisively.** 45 parcels have ever gone dark;
**43 recovered** (30 of them since delivered), dark spells last 1–5 days (avg 2.15).
The six-parcel 2026-08-06 group the hypothesis was built on all recovered — five are
delivered, one is live-moving. Even the "anomalous" code-80 parcel `59500007112662`
resumed 08-07 and was delivered 08-09. Parcels resume the full status chain
(120 → 6 → 101 → 9) through to delivery. `no_data` is **episodic data-feed blindness**
(stub codes 80/81/122; 81 is new), not a carrier-handoff endpoint.

State today: 71 delivered / 24 moving / 0 problem / **2 no_data** / 7 untracked;
needs attention 19 (baseline 20). The group went 7 → 2 with **zero** aged_out and zero
manual action — real recoveries cleared it. Both current dark parcels last read
"Митне оформлення завершено" (code 120), not the "прямує до <city>" signature the
proposed split was keyed on — the split's premise fails on today's data too.

**Decisions:**

- **Status-signature split: rejected** (per this doc's own conditional — the
  "even one recovered" branch, at 43).
- **Manual "resolved" action: rejected** — the group self-clears; nothing sits
  permanently.
- **Optional follow-up (small, frontend+classify only, no migration):** an age
  highlight inside `no_data` at **>6 days dark** (observed recovery ceiling is 5.0d).
  Today it selects exactly one parcel: `59500007135457` — dark 9.7d, second episode,
  scheduled delivery 2026-08-06 long past. **Action now: ask the manager to look up
  this one parcel in the WB cabinet.**
- **WB-2 is unblocked** (it was sequenced on this decision). Composition shift to note:
  17 of 19 attention rows are overdue-moving (71% of in-flight vs 19% at baseline),
  and many "overdue" are known to be "arrived, awaiting collection" —
  `WB-TRACK-ARRIVED-STATE` + `WB-2` are now the levers that matter. Prioritise after
  the manager-feedback questions above are answered.

## Proposed edits to implementation_plan.md (not made — Cowork+Sergii own that file)

1. `WB-TRACK-NO-DATA-TERMINAL` row: append the 2026-08-20 review outcome once the
   queries run — the recovery verdict, today's distribution vs baseline, stub-code
   inventory — and the decision taken.
2. If the split+manual-resolved path is chosen, file it as a small sprint (backend
   classification tweak + one action + page group; no migration needed for the split,
   one nullable column or a new `stopped_reason` value for manual resolve).
3. `WB-TRACK-ARRIVED-STATE` and `WB-2` re-sequence according to the manager feedback.

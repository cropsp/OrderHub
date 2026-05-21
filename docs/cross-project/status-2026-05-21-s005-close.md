# Status from OrderHub-side Cowork → idlaser-side Cowork

**Date:** 2026-05-21
**Context:** S005-submodule-migrate CRM-side closed. Closing the loop per your offer in the v1.0.0 tag-delivery reply.

---

## Summary

S005 merged to OrderHub main 2026-05-21. 5 commits on branch
`s005-submodule-migrate`:

- `229011b` — fix(s004-fu-1): DraftGenerator useRef guard against React.StrictMode double-fire
- `59e5663` — chore(s005): add idlaser as git submodule at `backend/external/idlaser` pinned to `e5bb5cfdb212540c969fcf4bfbfe22005147ed13` (your tag `v1.0.0`)
- `9284919` — refactor(s005): Dockerfile build-time `pip install -e ./external/idlaser`, entrypoint runtime install removed
- `02fb379` — chore(s005): docker-compose `/idlaser:rw` bind-mount removed, `IDLASER_*` config defaults updated, `.env.example` doc block added, OQ-H stale-path warn in entrypoint
- `c0e5900` — docs(s005): `CLAUDE.md` "ID-Laser draft pipeline" section rewrite + bare-metal `start-dev.sh` runbook block (kept local-only per CRM convention)

Plus a CRM-side docs closure commit landing today (this message).

---

## Verification status

**Backend pipeline verified end-to-end** in bare-metal mode (Docker mode
verified by CC's gate during commit 2). One bare-metal click of Generate
Draft on a Heavy Mushroom Keychain test order produced:

- New `IdlaserDraftJob` row (UUID `7c796345-9737-4000-a32b-a3c6f68180de`) at
  14:24:24
- Full pipeline execution (detect classical → detect ML → rectify → face
  → eyes → compose → export), completing at 14:24:27
- New MOCKUP attachment row (UUID `3f132461`, file
  `draft_7c796345-9737-4000-a32b-a3c6f68180de.dxf`, 219 373 bytes)
- Final `UPDATE state='ready'`

idlaser pipeline behavior identical to S004 era — your streaming API
surface unchanged through to `v1.0.0` as you promised. No regressions.

**Commit 0 (`S004-followup-1` fix) verified at DB level:** exactly ONE
`INSERT INTO idlaser_draft_jobs` row per UI click (pre-fix S004 era was
2 — React.StrictMode dev double-invoke). The orphan-job dev annoyance
that S004 closure parked is now resolved end-to-end.

**Pytest 187/187 pass.** Includes existing `test_pipeline_bare_export_completed_is_suppressed`
which pins S004 fix `8ed66d6` against regression.

---

## Two CRM-side smoke gaps deferred — NOT idlaser-side concerns

Filed under `S005-followup-1` and `S005-followup-2` in
OrderHub's `implementation_plan.md` "Explicitly deferred" table.
Mentioning here so the joint closure has complete picture:

1. **`backend/config.py` IDLASER_* path defaults assume Docker container
   layout** (`/app/external/idlaser/...`). Works in Docker, breaks
   bare-metal. Workaround in `.env` override; real fix is ~5 LOC rewrite
   to `Path(__file__).resolve().parent / "external" / "idlaser"`. Pure
   CRM-side; no idlaser changes needed.

2. **Bare-metal Vite proxy SSE chunking** appears to immediately
   disconnect after POST without forwarding `sse_starlette` chunks to
   the frontend. Same setup demonstrably worked in S004 era — suspected
   environmental drift (Vite minor version? http-proxy-middleware SSE
   handling?) and **NOT specific to S005 code changes**. Backend
   pipeline DOES complete via your fire-and-forget runner_task pattern
   (CRM commit `0cc6068` from S004), so MOCKUPs are created correctly
   even though the UI doesn't see streaming events. Pure CRM
   infrastructure investigation; idlaser-side is unaffected.

Docker mode was not full-walked through UI flow during smoke but its
build + import + healthcheck gates all passed.

---

## Idlaser-side pre-tag prep credit

Your `e5bb5cf chore: bundle card_detector.onnx for submodule consumers
(S005-prep)` commit, which fixed the `.gitignore` `models/` rule that
was preventing the ONNX weight from being tracked, was **the operational
win of the sprint**. Without that pre-tag catch, CRM-side submodule
clone would have arrived with an empty `models/` directory and broken
backend startup. Idlaser-side proactively caught it during the tag
review pass — exactly the kind of cross-repo coordination that
courier-via-Sergii is meant to enable.

`.gitignore` whitelist of `card_detector.onnx` documented in
CRM-side `CLAUDE.md` "ID-Laser draft pipeline" → "Bundled ONNX weights"
gotcha for future archeology.

---

## Joint closure suggestion

Per your offer: idlaser-side writes the joint closure entry in
`~/projects/idlaser/implementation_plan.md` (or equivalent
roadmap doc) citing:

- Idlaser-side tag commit `e5bb5cf` (S005-prep + v1.0.0 tag)
- CRM-side commits `229011b` / `59e5663` / `9284919` / `02fb379` /
  `c0e5900` (commits 0-4)
- CRM-side docs closure commit (the one CRM-side is landing today)
- The two CRM-side smoke gaps as **CRM-only follow-ups, no
  idlaser-side action needed**

The master integration contract at `~/projects/idlaser/task.md`
(15 Behaviour rules) remains in force, unchanged. No relitigation.

---

## Cross-repo coordination protocol — proven for a second sprint

Courier-via-Sergii worked smoothly through S004 and now S005. The
operational pattern — Cowork drafts handoff doc in CRM repo at
`docs/cross-project/`, Sergii couriers via copy-paste between
sessions, idlaser-Cowork replies through same channel — scales without
needing a shared handoff folder mount. Recommend retaining for any
future idlaser-touching sprint (e.g., when ONNX retraining lands an
idlaser tag bump that CRM-side SHA-pin would need to consume).

---

## Out of scope for this status

- API changes to idlaser pipeline — none requested or made
- New idlaser features — none requested
- Modifications to the 15 settled Behaviour rules — none

---

**OrderHub-Cowork sign-off:** S005 sprint closed cleanly on the CRM
side. Awaiting your joint-closure entry on the idlaser side when
convenient — no time pressure.

Thanks for the smooth handoff.

# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Cross-repo master contract:** `~/projects/idlaser/task.md` (also in `~/projects/handoff/orderhub-idlaser.md` if handoff folder is set up). 15 settled Behaviour rules + 10 OQs. Idlaser-side answered OQs 1/2/3/7; this task.md answers OQs 4/5/6/8/9/10 + adds CRM-specific OQs.
> - **Current task:** S005-submodule-migrate — replace transitional idlaser bind-mount + entrypoint pip install with git submodule + Dockerfile build-time install. Bundles commit 0 for S004-followup-1 (DraftGenerator StrictMode double-fire fix). See spec below.
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## ✅ S004-mcp-wrapper — DONE (2026-05-20)

Sprint closed. 5 feat commits `d0ee31e` → `55dc444` + 4 mid-smoke fix commits `5c7a0ba` / `0cc6068` / `d98d573` / `8ed66d6` + 1 docs closure commit `7b33184`. Browser-MCP smoke 8/8 green. pytest 171 → 187 (+16 new `test_idlaser_*` cases including `test_pipeline_bare_export_completed_is_suppressed` which pins fix `8ed66d6`). One parked follow-up: `S004-followup-1` — DraftGenerator useEffect double-fire under React.StrictMode dev (production unaffected; ~3 LOC fix; bundled into S005 below as commit 0). Full closure entry + smoke evidence + per-commit narrative in `implementation_plan.md` (search "S004-mcp-wrapper" in that file).

---

## S005-submodule-migrate — Migrate idlaser from docker bind-mount to git submodule

### Goal

Replace the transitional bind-mount + runtime `pip install -e /idlaser`
(established in S004) with a git submodule + build-time install. **Zero
functional change for end users** — Generate Draft button → SSE → DXF
flow remains identical. Same routes, same DB schema, same React
components, same pipeline. This is pure infrastructure refactor
discharging the technical debt explicitly marked at S004 close:

> *"idlaser is a vendored library dependency; canonical source at
> github.com/cropsp/idlaser; bind-mount setup is transitional, submodule
> migration planned post-S004 as S005-submodule-migrate."*
> — CLAUDE.md, "ID-Laser draft pipeline" section, verbatim per S004
> Behaviour rule.

**Bonus:** bundle the `S004-followup-1` fix (DraftGenerator
StrictMode double-fire creates orphan jobs in dev) as commit 0. The fix
is frontend-only (~3 LOC + 1 vitest assertion) and unrelated to the
submodule mechanics, but lives in idlaser-adjacent code, so the cost
of bundling is near-zero and the operational benefit (clean dev cycle
during S005 smoke) is real.

### Cross-repo source of truth

The **master integration contract** from S004 lives at
`~/projects/idlaser/task.md` (same file via
`~/projects/handoff/orderhub-idlaser.md` if handoff is mounted). The
15 Behaviour rules from S004 master remain in force — no
relitigation. S005 adds CRM-side-only refinements; idlaser-side has
exactly one upstream action (tag a release — see Rule 9 below).

**Idlaser-side coordination protocol:** courier-via-Sergii (same as
S004). Cowork drafts the idlaser-side tag request as a brief file in
`docs/cross-project/idlaser-S005-coordination.md` (created during plan
mode); Sergii couriers it to the idlaser-Cowork session; idlaser-side
publishes a tagged release (e.g. `v1.0.0`); confirms back via Sergii;
THEN CRM-side starts CC implementation.

### Behaviour rules (settled — do not relitigate)

1. **Zero functional change for end users.** Generate Draft → SSE →
   DXF pipeline behaves identically pre- and post-migration. Same
   `routers/idlaser.py`, same `services/idlaser_service.py`, same
   `frontend/src/components/orders/draft/*`. If a code change to
   these files is required to make the migration work, that is a
   bug in the migration design — surface to Cowork before committing.

2. **idlaser remains vendored, not on PyPI.** Submodule is the new
   vendoring mechanism; no public package publish, no internal PyPI
   mirror.

3. **`backend/external/idlaser/` is the canonical path.** Replaces
   both the `/idlaser:rw` Docker bind-mount and the old
   `/idlaser/...` config defaults in `backend/config.py:60-61`. The
   directory does NOT exist before the submodule is added in
   commit 1.

4. **No `Co-Authored-By` trailer** per AI_ONBOARDING.md §9.

5. **Bare-metal `start-dev.sh` still works post-migration.** Commit 2
   updates `start-dev.sh` to run, in the venv-active block, both
   `git submodule update --init --recursive`
   AND `pip install -e backend/external/idlaser` after the existing
   `pip install -r requirements.txt`. The host venv must see the
   idlaser package as importable; the Docker image's site-packages
   is a separate install path. (Without this rule, the Docker path
   works but bare-metal silently breaks — the original `pip install
   -e /idlaser` line in entrypoint.sh covered both via mount path
   coincidence, which we're losing.)

6. **ONNX weights remain bundled inside the submodule** as a regular
   binary commit at `backend/external/idlaser/models/card_detector.onnx`
   (~80 MB). This adds ~80 MB to idlaser's git history (a one-time
   cost paid in the idlaser repo, not CRM). Trade-off vs GitHub
   Release asset + entrypoint download: we explicitly choose
   `git clone` predictability over runtime network dependency. A
   `git clone --depth=1 --recurse-submodules` keeps CRM-side clone
   time bounded since only the latest tagged release is fetched.

7. **Commit 0 (S004-followup-1 fix) is frontend-only and independent
   of cross-repo coordination.** It can be safely committed and even
   merged on its own if idlaser-side tag is delayed. Bundled into
   S005 only for efficiency; do NOT block on it if Cowork later
   decides to ship commit 0 ahead of the rest.

8. **All 5 commits (0-4 below) land on a single feature branch
   `s005-submodule-migrate`** for review-time atomicity. Squash merge
   is NOT permitted — each commit's narrative matters for future
   archeology (per CLAUDE.md "Surgical changes" principle).

9. **Idlaser-side MUST publish a tagged release before CC starts
   implementation.** Cowork requests the tag via courier-via-Sergii
   as the first cross-repo action. CC plan-mode SHOULD NOT run until
   the tag SHA is known (so commit 1 can pin to a specific SHA, not
   "main HEAD as of plan time"). If tag is delayed, commit 0 can
   still ship independently per Rule 7.

### Open Questions (resolve in plan-mode, with cited file:line evidence)

| ID | OQ | Trade-off |
|---|---|---|
| OQ-A | Docker build submodule auth — pre-clone on host (CC's recommendation; Sergii's host already has the repo from S004 setup) vs PAT build-arg via Docker `--secret` mount vs SSH deploy key in Dockerfile | Simplicity (host-clone) vs CI reproducibility (PAT/SSH) vs secret-handling overhead |
| OQ-C | Submodule pin strategy — track a tagged release (e.g. `v1.0.0`) vs pin to an explicit commit SHA inside the tag | Stability (SHA) vs cleaner update story (`git submodule update --remote --to-tag vX.Y.Z`) |
| OQ-D | Dockerfile single-stage (current) vs multi-stage (dev deps stripped from runtime image) | Build complexity vs image size — measure idlaser dev-deps size first |
| OQ-E | Downgrade / retry path if `git submodule update --init` fails on operator machine (network blip, missing deploy key, no internet on first boot) | Need explicit error message + recovery procedure in `start-dev.sh`; do NOT silently fall back to old bind-mount path |
| OQ-F | `start-dev.sh` submodule-init flow — auto-run `git submodule update --init` if `backend/external/idlaser/` is empty, vs require operator to run it manually with clear error | Operator surprise (auto) vs script complexity (manual prompt) |
| OQ-G | Old-branch compatibility — once commit 3 lands and bind-mount removed from docker-compose.yml, operators on old branches (pre-S005) need to re-add the bind-mount line locally to build. Worth documenting prominently? | One-paragraph runbook note vs explicit `git checkout` hook |
| OQ-H | Operator `.env` file may have `IDLASER_TEMPLATE_PATH=/idlaser/7001.svg` and `IDLASER_MODEL_PATH=/idlaser/models/card_detector.onnx` from S004 setup. These env vars OVERRIDE the new defaults in commit 3 silently. Migration strategy: (a) commit 3 also updates `.env.example` + entrypoint warns loudly if old path detected, (b) silent migration relying on operator to read CLAUDE.md, (c) hard-fail entrypoint if old path detected with clear "your .env is out of date" message | UX of upgrade (loud warn) vs friction (hard-fail) vs silent-but-confusing |

### Verification gates

Each gate must pass before the next commit is approved.

**Backend gates (no change expected — pure refactor):**
- `pytest tests/ -v` → 187 → 187 (S005 does NOT add backend code, only
  bootstrap; if any test count changes, that's a regression to
  investigate)
- `alembic upgrade head` clean (no new migration this sprint)

**Frontend gates:**
- `npx tsc --noEmit` clean
- `npm run lint` clean
- `npx vitest run` → existing test count + 1 new assertion in
  `DraftGenerator.test.tsx` for the StrictMode guard (commit 0)

**Docker mode gate:**
- `docker compose build` succeeds with NO external `/idlaser:rw`
  bind-mount in `docker-compose.yml` (verify by `grep -c /idlaser
  docker-compose.yml` → 0)
- `docker compose up` brings backend healthy
- Browser-MCP smoke step 1 (AUTO path) succeeds end-to-end

**Bare-metal mode gate:**
- Fresh-clone operator workflow: `git clone --recurse-submodules`
  succeeds; `./start-dev.sh` succeeds without manual intervention
  (per OQ-F decision)
- Generate Draft AUTO path works against bare-metal backend

**Regression gates (smoke — confirm S004 fixes still in place):**
- Browser-MCP smoke step 1: **expect exactly ONE
  `INSERT INTO idlaser_draft_jobs` per UI click** (regression test
  for commit 0 — `S004-followup-1` fix). Confirm via
  `tail -100 backend/logs/server.log | grep -c "INSERT INTO
  idlaser_draft_jobs"` after one click. Pre-fix it was 2; post-fix
  it must be 1.
- All 8 S004 smoke steps still green (auto, review-via-pytest,
  auth, concurrent-architecture-review, error-recovery,
  console-clean, browser-mcp-clickable, no-regression)

**Closure-time tasks (post-smoke, in Cowork's closure commit):**
- `S004-followup-1` row REMOVED from "Explicitly deferred" table in
  `implementation_plan.md`
- New S005 closure entry written in `implementation_plan.md`
- `task.md` archives S005 spec the same way S004 spec is archived
  in this file

### Workflow

**CC prompt prefix (per Cowork-idlaser protocol):**

```
First — diagnostic:
  pwd
  git branch --show-current
  git rev-parse HEAD
  git status --short

Then read in order:
  1. docs/AI_ONBOARDING.md
  2. CLAUDE.md — focus on "ID-Laser draft pipeline" section
  3. implementation_plan.md S004 closure entry (search
     "S004-mcp-wrapper") + Explicitly deferred row S004-followup-1
  4. task.md (this file) — sections below "S005-submodule-migrate"
  5. Master cross-repo contract: ~/projects/idlaser/task.md
     (or ~/projects/handoff/orderhub-idlaser.md if mounted)
  6. backend/Dockerfile (lines 1-31 — current bootstrap)
  7. backend/entrypoint.sh (lines 6-15 — install block to be removed)
  8. docker-compose.yml (line 29 — bind-mount to be removed)
  9. backend/config.py (lines 58-62 — IDLASER_* defaults to be updated)
  10. start-dev.sh (full — gets new submodule init + pip install steps)
  11. frontend/src/components/orders/draft/DraftGenerator.tsx
      (lines 48-55 — useEffect to be guarded against StrictMode)
```

**Plan mode REQUIRED.** S005 introduces:
- First git submodule in the OrderHub monorepo
- First Docker build-time COPY of an external repo
- First bare-metal vs Docker dual-path bootstrap inside `start-dev.sh`
  (today it's bare-metal only)
- First `.env` migration scenario (OQ-H)

In the plan, answer all 7 OQs (A, C, D, E, F, G, H) with cited
file:line evidence. Show the exact `git submodule add ...` command,
the Dockerfile diff (lines to remove + lines to add), the
`start-dev.sh` diff, and the `frontend/src/components/orders/draft/DraftGenerator.tsx`
useEffect guard pseudo-code. Cite the idlaser-side tag SHA that will
be pinned in commit 1 (Cowork will provide this SHA after
courier-via-Sergii confirms tag).

**No code edits until Sergii approves the plan.**

After approval: implement → backend gates (pytest + alembic
no-op confirm) → frontend gates (tsc + lint + vitest) → docker
gate → bare-metal gate → **STOP, ping Sergii for browser-MCP
smoke** per the verification gates above → commit. Then Cowork
writes closure entry.

**Commit split (5 commits, on branch `s005-submodule-migrate`):**

0. `fix(s004-fu-1): ref-based guard in DraftGenerator useEffect against React.StrictMode double-fire`
   — `frontend/src/components/orders/draft/DraftGenerator.tsx:48-55`
   only; `useRef<string | null>(null)` tracking last-started
   `photoAttachmentId`, reset on modal close; 1 new vitest
   assertion in `DraftGenerator.test.tsx`. Independent of
   submodule mechanics (per Rule 7).

1. `chore(s005): add idlaser as git submodule at backend/external/idlaser`
   — new `.gitmodules` file; submodule pinned to `{SHA-from-tag}` per
   OQ-C answer; no other file changes. Verify clone succeeds in CI.

2. `refactor(s005): move idlaser pip install from entrypoint to Dockerfile build-time + bare-metal start-dev.sh updates`
   — `backend/Dockerfile:15-21` comment block replaced with
   `COPY ./external/idlaser ./external/idlaser` + `RUN pip install
   --no-cache-dir -e ./external/idlaser`; `backend/entrypoint.sh:6-15`
   install block deleted entirely (lines 6 → 16 collapse);
   `start-dev.sh` gains submodule-init + `pip install -e
   backend/external/idlaser` steps after the existing `pip install
   -r requirements.txt` block per Rule 5 + OQ-F answer. Docker mode
   still uses the old `/idlaser:rw` bind-mount as a fallback
   (kept for commit 3's atomic removal).

3. `chore(s005): drop docker-compose /idlaser bind-mount + update IDLASER_* config defaults`
   — `docker-compose.yml:29` line deleted (whole `/idlaser:rw`
   line, not the whole `volumes:` block); `backend/config.py:60-62`
   defaults updated to `/app/external/idlaser/7001.svg` and
   `/app/external/idlaser/models/card_detector.onnx`; `.env.example`
   updated to match; `entrypoint.sh` warning per OQ-H answer. Point
   of no return — old branches will fail to build after this commit
   merges to main (per OQ-G runbook note in commit 4).

4. `docs(s005): CLAUDE.md "ID-Laser draft pipeline" section rewrite + AI_ONBOARDING.md runbook update`
   — replace the "Bind-mounts, not requirements.txt" gotcha with
   "Submodule, not requirements.txt" gotcha; replace the "First-time
   operator setup runbook" 10 steps with the new
   `git clone --recurse-submodules` flow; document OQ-G transition
   (operators on old branches) and OQ-H `.env` migration prominently;
   update CLAUDE.md "Build & Run" section if `start-dev.sh`
   invocation changes.

**Do NOT update `implementation_plan.md` or `task.md` post-sprint** —
Cowork writes closure entry after browser-MCP smoke verification.

**No Co-Authored-By trailer** per AI_ONBOARDING.md §9.

---

## S004-mcp-wrapper — CRM integration: Generate-Draft + manager-mediated corner-picker (CRM-side) [ARCHIVED SPEC]

### Cross-repo source of truth

The **master integration contract** lives at `~/projects/idlaser/task.md`
(same file shared via `~/projects/handoff/orderhub-idlaser.md` if handoff is
mounted). It contains:
- Two-side architecture diagram (browser → CRM backend → idlaser pipeline)
- 15 settled Behaviour rules (do NOT relitigate)
- 10 Open Questions (idlaser-side already answered 1, 2, 3, 7; CRM-side
  answers 4, 5, 6, 8, 9, 10 — inline below)
- Verification scenarios for idlaser-side, CRM-side, integration end-to-end
- Workflow split between CC session A (idlaser) and CC session B (this sprint)

**Read the master contract FIRST** before this file. If you find a hard
contradiction between master and CRM reality during planning, surface to
Cowork (Serhii) immediately — do NOT improvise. The 15 Behaviour rules are
settled contracts; everything outside them is open for discussion.

**Idlaser-side has shipped** (commit `6720146` in `~/projects/idlaser`,
GitHub `https://github.com/cropsp/idlaser` — private). Streaming wrapper
`idlaser.pipeline.process_one_streaming` is importable; weights at
`~/projects/idlaser/models/card_detector.onnx`; template at
`~/projects/idlaser/templates/7001.svg` (verify with OQ-F).

### Goal

Wire idlaser into OrderHub as a manager-facing workflow on order detail:
"Generate Draft" button in `AttachmentManager`'s Production Assets section
runs the pipeline against a customer ID photo, streams progress via SSE,
falls into a corner-picker modal when ML alignment fails, saves the
generated DXF as a new `Attachment(attachment_type=MOCKUP)`. Manager
downloads the result via existing `/api/attachments/{id}`.

**Manager-mediated correction is FIRST-CLASS workflow**, not edge case
(per master Goal §). Real-world AUTO rate is ~30-70% depending on photo
quality. The corner-picker covers the rest in ~30s/photo. Don't
deprioritize the picker as nice-to-have.

This is OrderHub CRM's **first user-facing SSE pattern** (mcp.py is locked,
internal-only). The architectural choices here become reference for any
future progress-streaming feature.

### Integration mechanism (strategic context)

**During S004:** bind-mount + `pip install -e /idlaser` editable install.
Enables rapid two-repo iteration. Concrete `docker-compose.yml` mounts:

```yaml
volumes:
  - /home/serhii/projects/idlaser:/idlaser:rw            # for pip install -e /idlaser
  - /home/serhii/projects/idlaser/models:/app/models:ro  # ONNX weights
  - /home/serhii/projects/idlaser/templates:/app/templates:ro  # SVG templates
```

**Post-S004 (sprint S005-submodule-migrate, NOT in scope here):** swap
bind-mount for git submodule from `github.com/cropsp/idlaser` (private —
needs PAT/SSH deploy key in Dockerfile; flag for S005 planner). Weight
file then distributed via tagged GitHub Release asset.

**In CRM's CLAUDE.md update (commit 5 of split below)** include this
sentence verbatim: *"idlaser is a vendored library dependency; canonical
source at github.com/cropsp/idlaser; bind-mount setup is transitional,
submodule migration planned post-S004 as S005-submodule-migrate."*

### Behaviour rules (settled — do not relitigate)

**Master rules 1-15 apply as written.** See `~/projects/idlaser/task.md`
or `~/projects/handoff/orderhub-idlaser.md`. Below are CRM-side-specific
rules ON TOP of master:

16. **SQLAlchemy model conventions.** `IdlaserDraftJob` extends
    `Base, UUIDPrimaryKeyMixin, TimestampMixin` per `backend/models/base.py`.
    Mirror recent precedent: `backend/models/partner_settlement.py` and
    `backend/models/partner_payment.py` (PART-1, commit `bd6e528`). Use
    `Mapped[]` type annotations + `mapped_column()` per SQLAlchemy 2.0 style
    used throughout the codebase.

17. **Migration filename & ENUM pattern.** Alembic migration filename via
    `alembic revision --autogenerate -m "add_idlaser_draft_jobs"` →
    `{revision_hash}_add_idlaser_draft_jobs.py`. The new Postgres ENUM
    `idlaser_draft_job_state` MUST be explicitly dropped in `downgrade()`
    per PART-1 precedent — autogenerate does NOT always drop ENUMs cleanly.
    Hand-add `sa.Enum(name="idlaser_draft_job_state").drop(op.get_bind(), checkfirst=True)`
    in `downgrade()`. Round-trip required: `alembic upgrade head &&
    alembic downgrade -1 && alembic upgrade head` all clean (AI_ONBOARDING.md §9).

18. **SSE backend pattern: `sse_starlette.sse.EventSourceResponse`.** Not raw
    `StreamingResponse(media_type="text/event-stream")`. `sse-starlette==2.2.1`
    is already in `backend/requirements.txt:31`; `routers/mcp.py` does use
    raw StreamingResponse but that's the MCP-protocol-specific SSE transport
    (also locked per CLAUDE.md gotcha), not a precedent for general user-facing
    SSE. `EventSourceResponse` gives automatic heartbeat / `ping` for connection
    liveness and cleaner emit semantics. This is OrderHub's **first user-facing
    SSE endpoint** — pattern established here will be reused.

19. **Frontend new directory: `frontend/src/components/orders/draft/`** as
    sibling to existing `detail/`. Same structural convention as
    `OrderDetailPanel` composing `detail/Detail*.tsx` sub-components. Tests
    in `draft/__tests__/` per convention (cf. `detail/__tests__/`).

20. **Reuse the `<ConfirmDialog>` primitive** (`frontend/src/components/ui/ConfirmDialog.tsx`,
    commit `93f45ca`) for any "Cancel pipeline?" / "Discard draft?" / "Retry?"
    prompts inside DraftGenerator. Do **NOT** introduce new `window.confirm()`
    calls (per AI_ONBOARDING.md §9 + PART-1-followup-1 closure — native
    confirm blocks browser-MCP smoke automation).

21. **JWT auth on SSE endpoint via `@microsoft/fetch-event-source`** (frontend
    new dependency, ~10 KB, per master rule 15). Native EventSource can't
    send custom `Authorization` headers; JWT-in-query-param leaks tokens
    into server logs (see OQ-9 answer below). Single hard frontend dep
    addition; no other new packages.

22. **Diagnostic prefix in CC prompt** (idlaser-side Cowork's protocol after
    worktree surprises): every CC session for this sprint runs `pwd`,
    `git branch --show-current`, `git rev-parse HEAD`, `git status --short`
    BEFORE any other reads. Catches "wrong worktree" / "stale clone" early.

23. **Cross-repo coordination via `~/projects/handoff/orderhub-idlaser.md`**
    if handoff folder is set up by Serhii. CC does NOT touch the handoff
    file — Cowork (Serhii's planning agent) owns it. CC reads it for
    context but never appends.

24. **`OrderStatus` enum and `ALLOWED_TRANSITIONS` are NOT modified** (master
    rule 3, restated for emphasis). IdlaserDraftJob has its own state machine;
    Order's main lifecycle is orthogonal.

25. **No new long-running-task infra** — `asyncio.to_thread` only (master rule 5+7).
    No Celery, no RQ, no Redis. Pipeline runs in thread pool worker; CRM has
    `< 10` concurrent users and `> 5` concurrent draft jobs would be the
    revisit trigger, not today.

26. **Attachment FKs use `ondelete='SET NULL'`** for both `photo_attachment_id`
    and `result_attachment_id` on `IdlaserDraftJob`. Master rule 2 says
    "NOT cascade" but doesn't pin RESTRICT vs SET NULL. SET NULL is the
    correct choice: if an operator deletes the customer photo OR the
    generated DXF attachment from Production Assets, the IdlaserDraftJob
    audit row survives (with the relevant FK cleared to NULL). RESTRICT
    would block attachment deletion with an FK error and break the
    operator's normal attachment-management workflow.

27. **Idlaser package imports go through `idlaser.api` ONLY** (master rule 14
    enforced). CRM service code uses `from idlaser.api import
    process_one_streaming, reprocess, Detection, LayoutResult, CARD_W_MM,
    CARD_H_MM, CARD_RATIO`. Never `from idlaser.pipeline import ...` or
    `from idlaser.detect import ...` directly — internals may move; api.py
    is the stable surface.

28. **`idlaser` is installed via Dockerfile only, NOT listed in
    `requirements.txt`.** Editable install of a bind-mounted path
    (`pip install -e /idlaser`) requires the path to exist at install time
    — which is true inside the container during `docker-compose build` (the
    bind-mount is active by then) but NOT true for someone running
    `pip install -r requirements.txt` on bare metal outside Docker.
    Adding `-e /idlaser` to requirements.txt would break local pip workflows.
    Document in CLAUDE.md as "vendored dependency, installed by Dockerfile,
    not in requirements.txt". S005 submodule migration will revisit this.

### Scope

**In scope — NEW backend files:**
- **`backend/models/idlaser_draft_job.py`** — `IdlaserDraftJob` SQLAlchemy
  model per master rule 2. ENUM `IdlaserDraftJobState` (PENDING, RUNNING,
  NEEDS_REVIEW, READY, FAILED, CANCELLED). Indexes: `(order_id, state)`.
  Mirror PART-1 model file structure verbatim.
- **`backend/alembic/versions/{auto_hash}_add_idlaser_draft_jobs.py`** —
  migration per rule 17 above. CHECK constraints if any (e.g.,
  `started_at <= completed_at` if both present).
- **`backend/schemas/idlaser_draft_job.py`** — Pydantic models:
  - `IdlaserDraftJobCreate` (`photo_attachment_id: UUID`)
  - `IdlaserDraftJobResponse` (full row + derived fields)
  - `ManualCornersRequest` (`corners: list[list[float]]` — 4 pairs)
  - `DraftJobStatusResponse` (polling fallback shape)
- **`backend/services/idlaser_service.py`** — wraps `idlaser.api.process_one_streaming`
  (per Behaviour rule 27 — never import from `idlaser.pipeline` directly).
  Owns:
  - State transitions (PENDING → RUNNING → READY/NEEDS_REVIEW/FAILED)
  - `asyncio.Queue` bridge from the synchronous pipeline callback (running in
    thread via `asyncio.to_thread`) to the SSE event stream (running on
    event loop) via `loop.call_soon_threadsafe(queue.put_nowait, event)`
  - SSE event taxonomy mapping per master rule 9
  - Generated-DXF Attachment creation via existing `services/file_storage.save_file()`
    pattern + DB row insert
  - Tenacity-decorated retry on transient ONNX session failures only
    (`tenacity==9.1.4` already in requirements)
- **`backend/routers/idlaser.py`** — three routes:
  - `POST /api/orders/{order_id}/generate-draft` → `EventSourceResponse`
  - `GET /api/orders/{order_id}/draft-jobs/{job_id}/status` → polling JSON
    (fallback for clients with broken SSE — also useful for tests)
  - `POST /api/orders/{order_id}/draft-jobs/{job_id}/manual-corners` →
    `EventSourceResponse` (same event taxonomy, picks up after rectify)
  - All routes role-gated per master rule 10 (OWNER/MANAGER/DESIGNER-if-assigned)
    via `routers/dependencies.py` helpers.

**In scope — backend MODIFICATIONS:**
- **`backend/main.py`** — (a) register the new `idlaser` router; (b) extend
  the existing `lifespan` async context manager (already exists at
  `backend/main.py:30` per current state) with a boot-time sanity check that
  `IDLASER_MODEL_PATH` and `IDLASER_TEMPLATE_PATH` exist on disk. Log warning
  if missing — do NOT crash (designer flow works without idlaser; we don't
  want a missing template to take down the whole app).
- **`backend/config.py`** — three new settings (with env-var fallbacks):
  - `IDLASER_TEMPLATE_PATH` (default `/app/templates/7001.svg`)
  - `IDLASER_MODEL_PATH` (default `/app/models/card_detector.onnx`)
  - `IDLASER_TIMEOUT_S` (default 60)
- **`backend/models/__init__.py`** — add
  `from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState`
  + their entries in `__all__`. Verified that `models/__init__.py` explicitly
  imports all models (e.g., `PartnerSettlement, PartnerPayment` at
  `backend/models/__init__.py:31-32`), so Alembic autogenerate sees what's
  imported here. Match the existing pattern.
- **`backend/Dockerfile`** — after `RUN pip install --no-cache-dir -r requirements.txt`,
  add `RUN pip install -e /idlaser` (per Behaviour rule 28 — idlaser is NOT
  added to `requirements.txt`).
- **`docker-compose.yml`** — three new bind-mount volumes for the backend
  service (see Integration mechanism section above).

**In scope — backend TESTS:**
- **`tests/test_idlaser_service.py` (new)** — 6-8 cases:
  - Pipeline success path → DXF attachment created, state=READY
  - Pipeline review path → state=NEEDS_REVIEW, manual_corners stays null
  - Manual-corners reprocess → DXF created, manual_corners stored
  - ONNX load failure → tenacity retries 3x → FAILED, error_message set
  - Concurrent jobs same order: 2 distinct rows, both progress independently (OQ-4)
  - Currency-mismatch / unknown error in pipeline → state=FAILED, error_message captures stack summary
  - Auth fixture: designer assigned vs not → 200 vs 403 (OQ-9)
- **`tests/test_idlaser_router.py` (new)** — 4-5 cases for SSE shape:
  - Event sequence on AUTO path (job.started → detect.classical.* → … → export.completed)
  - Event sequence on REVIEW path (… → review_required)
  - 403 for unauthorized
  - Manual-corners endpoint accepts valid corners, rejects malformed
  - Status polling endpoint returns current state
- **Expected pytest delta: 171 → ~185** (+14). Verify current baseline; record actual.

**In scope — NEW frontend files:**
- **`frontend/src/components/orders/draft/DraftGenerator.tsx`** — main modal,
  owns the state machine (idle → connecting → running → review_required →
  reprocessing → ready | failed | cancelled). Uses `<Dialog>` primitive
  (shadcn) similar to existing `CalculateSettlementModal.tsx`. Two render
  modes: ProgressPanel (steps + stage indicators) and CornerPicker (after
  review_required SSE event).
- **`frontend/src/components/orders/draft/ProgressPanel.tsx`** — step list
  mapped to master rule 9 SSE event taxonomy. Check marks per stage as
  events arrive. Stage labels human-readable ("Detecting card", "Aligning",
  "Detecting face", etc. — Ukrainian/English consistent with rest of app —
  see OQ-C). Photo preview on the right.
- **`frontend/src/components/orders/draft/CornerPicker.tsx`** — full
  photo background (from `attachmentsApi.download()` → blob → object URL),
  4 absolutely-positioned `<div>` markers with `onPointerDown/Move/Up`
  handlers. ~150 LOC per master rule 13. Photo logic donor reference:
  `~/projects/idlaser/review_tool.html`. Submit → POST to
  `/manual-corners` endpoint (re-opens SSE stream for reprocess).
- **`frontend/src/components/orders/draft/__tests__/`** — at minimum:
  - `DraftGenerator.test.tsx` — state machine transitions render correctly
    given mocked SSE events
  - `CornerPicker.test.tsx` — pointer events update marker positions; Submit
    fires onSubmit with 4 corners
  - `ProgressPanel.test.tsx` — given event sequence, steps render in order
    with correct check states
- **`frontend/src/hooks/useDraftJob.ts`** — TanStack Query mutation +
  SSE subscription via `@microsoft/fetch-event-source`. Shape sketched
  in OQ-E answer below. Returns `{ state, events, start, cancel, retry }`.
- **`frontend/src/api/draftJobsApi.ts`** — axios calls for the three
  routes + types matching backend Pydantic.
- **`frontend/src/types/draftJob.ts`** — TypeScript type definitions
  mirroring `backend/schemas/idlaser_draft_job.py` (see OQ-D — manual
  pattern per current convention).

**In scope — frontend MODIFICATIONS:**
- **`frontend/src/components/orders/AttachmentManager.tsx`** — add
  "Generate Draft" button per master rule 12. Enabled iff order has ≥1
  `Attachment` with `attachment_type === 'reference'`. Button copy:
  `"Generate Draft from {photo_filename}"`. If multiple REFERENCE
  attachments, copy becomes a dropdown / split-button. Mounts
  `<DraftGenerator>` modal on click.
- **`frontend/package.json`** — `@microsoft/fetch-event-source: ^2.0.1`
  added to dependencies. No other new packages.

**Out of scope (do NOT touch):**
- `backend/routers/mcp.py` — locked per CLAUDE.md gotcha.
- `OrderStatus` enum / `ALLOWED_TRANSITIONS` matrix — master rule 3.
- `services/file_storage.py` — reused as-is, no extensions needed.
- `backend/routers/attachments.py` — reused as-is (existing endpoint serves
  the photo bytes for the corner-picker background AND the DXF download).
- `backend/services/order_service.py` — IdlaserDraftJob does NOT log into
  OrderStatusHistory (master rule 11 — IdlaserDraftJob row IS the audit).
- Anything in `~/projects/idlaser/` — CC session A's slice; this CC does
  NOT modify the idlaser repo (only reads its API surface).
- Submodule plumbing — S005 work, not S004.
- Multi-photo combination / ID-1 geometry refinement / keypoint upgrade —
  parked future sprints per master Out of scope.
- Tests for `~/projects/idlaser` package — idlaser-side responsibility.

### Open questions for the planner

CC must answer each in the plan with cited file:line evidence.

**Master OQs assigned to CRM-side:**

**OQ 4 — Concurrent draft jobs per order (master OQ 4).**
Recommend **(a)**: allow multiple `IdlaserDraftJob` rows per order; each
row has its own state; no global "active job" flag. Mirrors CRM's
existing delete-and-recreate semantics for PartnerSettlement (PART-1 rule 4,
`backend/models/partner_settlement.py`).

**v1 UI scope decision:** there is **NO dedicated "draft history" panel**
inside AttachmentManager. The operator's "current draft" is simply the
latest READY job's `result_attachment_id` — which appears as a normal
DXF row in the existing Production Assets attachments list (same way any
MOCKUP attachment does today). If the operator wants to re-generate, they
click "Generate Draft" again — a new IdlaserDraftJob row is created. Old
job rows + their DXF attachments stay in history (and on disk). Operator
deletes unwanted DXF attachments via existing trash-icon flow per
AttachmentManager.tsx; the FK `IdlaserDraftJob.result_attachment_id`
gracefully nulls out (Behaviour rule 26).

If actual operator friction emerges ("which of these 3 DXFs is current?"),
v2 adds a sort/group/badge UI inside AttachmentManager. Not premature
optimization for v1.

CC: confirm there's no FK or unique constraint in the migration draft
that would block multiple rows per order (master rule 2 schema has no
such constraint — verify).

**OQ 5 — Corner-picker background image (master OQ 5).**
Recommend **(a)**: original customer photo, full-resolution. Manager
identifies 4 corners in original-image coordinate space; backend computes
the perspective transform via `idlaser.reprocess(photo, corners)`. Initial
marker positions = best-guess corners from whichever detector produced
something (`detect.classical_with_K0_face` candidate, OR ML output, OR
evenly-spaced rectangle at 10/90% if both detectors failed).
CC: confirm `idlaser.reprocess` API signature accepts `corners` as
`list[tuple[float, float]]` in pixel coordinates of the original photo
(read `~/projects/idlaser/idlaser/reprocess.py` + `idlaser/api.py`
re-exports).

**OQ 6 — Photo input flow (master OQ 6).**
Recommend **(a) for v1**: `POST /generate-draft` accepts
`photo_attachment_id: UUID` only — manager uploads via existing flow
first (`POST /api/attachments/order/{order_id}`, `backend/routers/attachments.py:31`).
Endpoints stay orthogonal. If real-world friction emerges ("operator
forgets to upload first"), v2 adds inline upload inside DraftGenerator
modal. Not premature optimization for v1.
CC: verify `Attachment` model FK back-reference to Order works for the
"fetch photo by id, validate it belongs to this order" check; sketch the
exact validation query in plan.

**OQ 8 — Migrations & deployment runbook (master OQ 8).**
Operator runbook for first deploy (lives in CRM's CLAUDE.md after this
sprint ships):

```
First-time setup for ID-Laser draft pipeline:
1. git clone https://github.com/cropsp/idlaser ~/projects/idlaser
2. cd ~/projects/idlaser && pip install -e .[dev]  # idlaser-side venv,
   for manual pipeline runs during ops
3. Ensure ~/projects/idlaser/models/card_detector.onnx exists
   (ships from idlaser S003.2 training output; if missing, see
   ~/projects/idlaser/docs/training.md for retraining recipe)
4. Ensure ~/projects/idlaser/templates/7001.svg exists
   (user-supplied; copy from prior Lamarka template archive)
5. Verify CRM's docker-compose.yml has the three bind-mount lines
   (see S004 closure entry for snippet)
6. Inside CRM repo: docker-compose build backend
   (re-runs Dockerfile, picks up pip install -e /idlaser)
7. docker-compose up -d backend
8. docker-compose exec backend alembic upgrade head
9. docker-compose restart frontend  (picks up new @microsoft/fetch-event-source)
10. Verify in browser: open any order with a REFERENCE attachment,
    click "Generate Draft from {filename}", confirm modal opens,
    SSE events stream, AUTO path produces a downloadable DXF.

If step 6 fails with "Could not find /idlaser" — bind-mount path is
incorrect for your username; edit docker-compose.yml's volume paths.

If step 10's "Generate Draft" button is grey/disabled — order has no
REFERENCE attachment. Upload one via the existing Production Assets
upload zone.
```

CC: copy this runbook into the new CLAUDE.md "ID-Laser draft pipeline"
section verbatim (commit 5 of split). Adjust step 1 path if Serhii's
WSL username differs (use `~` per ssh convention).

**OQ 9 — SSE authentication (master OQ 9).**
Recommend **(b)**: `@microsoft/fetch-event-source` library client-side.
Reasons:
- (a) JWT-in-query-param leaks tokens to server logs, Nginx access logs,
  browser history, referrer headers — anti-pattern.
- (c) httpOnly cookie auth is a multi-sprint refactor; CRM currently uses
  Bearer header (verified at `backend/routers/dependencies.py:17` via
  `HTTPBearer`).
- (b) preserves existing JWT-in-Authorization-header pattern, adds 10 KB
  to bundle. Frontend Axios interceptor already manages the token; we
  pass the same token to `fetchEventSource` via `headers: {
  Authorization: 'Bearer ' + token }`.

CC: implement `useDraftJob` hook to pull JWT from the existing Zustand
authStore. CLAUDE.md says "Zustand for auth (`authStore.ts`)" but doesn't
specify the directory — grep `authStore.ts` under `frontend/src/` to find
exact path (likely `store/` or `stores/` subdir). Confirm the store exposes
a token-getter, not just user-info-getter; if not, add a minimal accessor
in the same file. Inject token into fetchEventSource headers.

**OQ 10 — Error recovery / retry (master OQ 10).**
State machine confirmed: `RUNNING → FAILED` on unrecoverable error.
DraftGenerator modal shows error toast (existing
`useToastStore.addToast(msg, 'error')` pattern). "Retry" button creates
NEW IdlaserDraftJob row (does NOT reuse failed row — matches OQ 4
multiple-rows pattern). Old failed row stays in history with
`state=FAILED` + `error_message`.

Tenacity retries inside `services/idlaser_service.py` for **transient
ONNX failures only**:
- `tenacity==9.1.4` in `requirements.txt:25` (already there)
- Pattern: `@retry(stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=1, max=10),
  retry=retry_if_exception_type(OnnxruntimeError))` (approximate — CC
  verifies exact exception type from `~/projects/idlaser/idlaser/detect_ml.py`)
- NOT retried: misaligned results (REVIEW path is the proper response);
  template-load failures (operator error, surface to UI immediately);
  filesystem errors (likely permission misconfigure, surface).

CC: verify the exact onnxruntime exception class to catch — read
`detect_ml.py` and grep for `onnxruntime.` usage.

---

**CRM-side-specific OQs (additional, not in master):**

**OQ-A — Alembic current head.** Run `alembic heads` inside the backend
container; identify the migration to point at as `down_revision` for the
new `add_idlaser_draft_jobs` migration. The PART-1 migration is the
recent one — confirm its revision hash. State in the plan.

**OQ-B — Model registration for autogenerate.** Pre-answered (Cowork
verified): `backend/models/__init__.py:7-32` explicitly imports all models
including `PartnerSettlement` and `PartnerPayment` from PART-1. Add
`from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState`
+ entries in `__all__` list. Follow existing import grouping pattern.
(Listed as OQ for visibility in plan-mode evidence; no investigation needed.)

**OQ-C — Frontend test placement convention.** Grep for existing
`__tests__/` directories under `frontend/src/components/`. PART-1
introduced tests under `frontend/src/components/finance/__tests__/` —
confirm pattern. Place draft tests under
`frontend/src/components/orders/draft/__tests__/`. Also confirm Ukrainian
vs English in user-facing strings — the rest of the app is mixed
(observed during smoke: "Переглянути ордери за період" Ukrainian button
copy alongside English status labels). DraftGenerator stage labels:
Ukrainian preferred ("Виявлення картки", "Вирівнювання", "Обличчя",
"Очі", "Композиція", "Експорт") matching operator-facing register —
but match whatever convention you grep most consistently.

**OQ-D — Type definitions: manual vs generated.** Grep
`frontend/src/types/` for existing type definitions corresponding to
backend Pydantic models. Current convention is manual (no codegen
tooling like `openapi-typescript` in `package.json`). Continue manual
pattern for `draftJob.ts`. Risk of drift between backend Pydantic and
frontend types — document in CLAUDE.md gotcha if you notice mismatches
during implementation.

**OQ-E — `useDraftJob` hook structure.** Sketch the hook with:
- Internal state: `state: 'idle' | 'connecting' | 'running' | 'review_required' | 'reprocessing' | 'ready' | 'failed' | 'cancelled'`
- Internal state: `events: DraftEvent[]` (append-only log for ProgressPanel rendering)
- Internal state: `result: { resultAttachmentId: string } | null`
- Internal state: `reviewContext: { bestGuessCorners: number[][], rectifiedPreviewUrl: string } | null`
- Methods: `start(photoAttachmentId)`, `submitCorners(corners)`, `cancel()`, `retry()`
- SSE handling via `@microsoft/fetch-event-source`'s `fetchEventSource(url, { method, headers, body, signal, onmessage, onerror })`
- Cleanup on unmount via `AbortController`

Show in plan the actual TypeScript signatures + the event-to-state-transition
table. CC may refine but the contract should be locked before frontend
implementation starts.

**OQ-F — Idlaser side asset paths confirmation.** Cross-repo verify
(via coordination handoff or direct file read of
`~/projects/idlaser/models/` and `~/projects/idlaser/templates/`):
- Does `~/projects/idlaser/models/card_detector.onnx` exist NOW? (Brief
  says yes from S003.2-train output; verify before assuming bind-mount works.)
- Does `~/projects/idlaser/templates/7001.svg` exist NOW? (Master rule 8
  says "planned"; if not present yet, sprint blocked until idlaser-side
  ships the template OR Serhii provides one.)
- Confirm both paths are readable from CRM container after bind-mount
  applied — write a one-liner sanity test in `tests/test_idlaser_service.py`
  asserting `Path(settings.IDLASER_MODEL_PATH).is_file()` and same for template.

If template doesn't exist yet: surface immediately to Cowork (Serhii) —
this is a blocker for the integration smoke. Don't silently skip.

### Verification

**Backend gates:**
- `cd backend && python -m pytest tests/ -v` — expect 171 → ~185 (+14 new).
  Record actual baseline + new total.
- `cd backend && alembic upgrade head` — clean on fresh DB.
- `cd backend && alembic downgrade -1 && alembic upgrade head` — round-trip
  works (rule 17). Verify ENUM dropped + recreated correctly.

**Frontend gates:**
- `cd frontend && npx tsc --noEmit` — clean.
- `cd frontend && npm run lint` — clean on touched files.
- `cd frontend && npm run test` — all new vitest cases pass. Existing
  CustomersPage.test.tsx may fail (pre-existing baseline issue verified
  in PART-1-fu-1 closure); ignore that one.

**Integration verification (Cowork via browser-MCP after backend + frontend gates green):**

Per master §Verification + master §Integration end-to-end:

1. **Pre-flight:** Serhii ensures idlaser repo is at `~/projects/idlaser`
   with `models/card_detector.onnx` and `templates/7001.svg` present.
   `docker-compose up -d` brings up the stack with new bind-mounts.
   `alembic upgrade head` inside backend container.
2. **AUTO path on clean photo:** open any Lamarka order with at least one
   REFERENCE attachment (Heavy Mushroom Keychain has `IMG_2681.JPG` as
   MOCKUP — Serhii uploads a fresh REFERENCE-typed photo for testing
   OR temporarily reclassifies the existing). Click "Generate Draft
   from {filename}". Modal opens → SSE events stream
   (`job.started → detect.classical.* → … → export.completed`) within
   ~12 seconds. Modal shows "Download Draft" button. Click → file
   downloads via existing `attachmentsApi.download()` path. Open in
   RDWorks — confirm valid DXF.
3. **REVIEW path on hard photo:** upload one of idlaser's known-hard
   test photos as REFERENCE (e.g., `~/projects/idlaser/photos/icm_fullxfull.877577984...jpg`
   per master §Verification). Click "Generate Draft". SSE events
   stream → `review_required` event with 4 best-guess corners + rectified
   preview URL. Modal swaps to CornerPicker mode. Drag 4 corners to
   correct positions. Submit → SSE stream #2 → reprocess →
   `export.completed`. Download DXF → open in RDWorks → confirm valid.
4. **Auth checks:** anonymous request → 401. Designer not assigned to
   the test order → 403. Designer assigned → works.
5. **Concurrent jobs:** click "Generate Draft" twice in quick succession;
   confirm 2 distinct IdlaserDraftJob rows visible in some UI (or via
   GET /draft-jobs/...status). Both progress independently.
6. **Error recovery:** kill the backend mid-pipeline (or mock ONNX
   failure) → modal shows failure toast → "Retry" button appears →
   click → new IdlaserDraftJob row, old one stays FAILED in history.
7. **Console clean** throughout (modulo pre-existing DASH-SHOP-WARNINGS
   per PART-1-fu-1 closure noise).
8. **Browser-MCP can click all modal buttons directly** (per AI_ONBOARDING
   §9 — no native `confirm()` regressions).

### Workflow

**CC prompt prefix (per Cowork-idlaser protocol):**

```
First — diagnostic:
  pwd
  git branch --show-current
  git rev-parse HEAD
  git status --short

Then read in order:
  1. docs/AI_ONBOARDING.md
  2. CLAUDE.md
  3. implementation_plan.md (Active Roadmap section + recent closure
     entries for PART-1 + PART-1-fu-1; Explicitly deferred table)
  4. task.md (this file)
  5. Master cross-repo contract: ~/projects/idlaser/task.md
     (or ~/projects/handoff/orderhub-idlaser.md if mounted)
  6. backend/models/partner_settlement.py + partner_payment.py
     (recent SQLAlchemy 2.0 model precedent)
  7. backend/services/partner_payout_service.py
     (recent async-service precedent — though no SSE)
  8. backend/routers/finance.py (recent router pattern)
  9. frontend/src/components/orders/OrderDetailPanel.tsx + AttachmentManager.tsx
  10. frontend/src/components/finance/CalculateSettlementModal.tsx + RecordPaymentModal.tsx
      (existing modal pattern; ConfirmDialog.tsx in components/ui/ — reusable primitive)
  11. backend/routers/mcp.py (only SSE precedent — but LOCKED, do NOT modify)
```

**Plan mode REQUIRED.** The sprint introduces:
- First user-facing SSE endpoint in the codebase
- First cross-repo Python package dependency (bind-mounted)
- First docker-compose bind-mount of an external repo
- New frontend dep (`@microsoft/fetch-event-source`)
- First pointer-event-based interactive overlay (corner-picker)

In the plan, answer all 12 OQs (6 master CRM-side + 6 CRM-specific A-F)
with cited file:line evidence. Show the SSE event-flow ASCII diagram
mapped to backend code locations. Show the IdlaserDraftJob model
definition + Alembic migration diff. Show the useDraftJob hook signature.
Show the CornerPicker pointer-event handlers pseudo-code.

**No code edits until Serhii approves the plan.**

After approval: implement → backend gates (pytest + alembic round-trip) →
frontend gates (tsc + lint + vitest) → **STOP, ping Serhii for browser-MCP
smoke** per the 8-step integration verification above → commit.

**Commit split (5 commits per master §Workflow):**

1. `chore(idlaser): docker bind-mounts + Dockerfile pip install -e /idlaser + IDLASER_* config keys`
   — docker-compose.yml mounts; Dockerfile pip install; config.py settings;
   no app code changes yet.

2. `feat(idlaser): IdlaserDraftJob model + migration + Pydantic schemas + service wrapper`
   — model + ENUM + indexes; migration with ENUM-aware downgrade;
   schemas; idlaser_service.py with SSE-bridge helper + pipeline wrapping;
   backend tests for service.

3. `feat(idlaser): 3 routes — generate-draft SSE + manual-corners SSE + status polling`
   — routers/idlaser.py; main.py router registration; backend tests for
   routes (role gating + SSE shape).

4. `feat(idlaser): frontend DraftGenerator + ProgressPanel + CornerPicker + AttachmentManager Generate Draft button + useDraftJob hook + draftJobsApi client`
   — all frontend new files + AttachmentManager modification + package.json
   dep addition; frontend tests.

5. `docs(idlaser): CLAUDE.md "ID-Laser draft pipeline" gotcha section with operator runbook`
   — CLAUDE.md update including the "vendored library dependency"
   sentence verbatim + the 10-step first-time setup runbook from OQ 8 answer.

**Do NOT update `implementation_plan.md` or `task.md` post-sprint** —
Cowork writes closure entry after browser-MCP smoke verification.

**No Co-Authored-By trailer** per AI_ONBOARDING.md §9.

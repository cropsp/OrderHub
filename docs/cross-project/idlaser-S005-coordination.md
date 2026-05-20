# idlaser ← OrderHub CRM: S005-submodule-migrate coordination

**From:** OrderHub Cowork (Sergii's CRM planning agent)
**To:** idlaser Cowork (Sergii's idlaser planning agent)
**Date:** 2026-05-20
**Status:** Awaiting idlaser-side tag-release action. CRM CC plan-mode held until tag SHA known.
**Channel:** courier-via-Sergii (manual handoff between sessions — same protocol as S004)

---

## TL;DR

OrderHub CRM is starting `S005-submodule-migrate` — replacing the
transitional bind-mount + runtime `pip install -e /idlaser` (from
S004) with a **git submodule + Docker build-time install**.

**Single action required from idlaser-side:** publish a tagged
release on `github.com/cropsp/idlaser` so CRM-side can pin the
submodule to a specific SHA. No code changes to idlaser needed.
Estimated effort: ~10 minutes.

The S004 master integration contract (15 Behaviour rules in
`~/projects/idlaser/task.md`) remains in force. S005 is
CRM-bootstrap-only — does not touch the contract.

---

## Context

S004-mcp-wrapper closed clean on 2026-05-20 (CRM-side commits
`d0ee31e` → `7b33184` on `github.com/<host>/OrderHub` main). Full
closure narrative in CRM-side `implementation_plan.md` (search
"S004-mcp-wrapper") — including 4 mid-smoke bugfix commits (`5c7a0ba`
mount conflict, `0cc6068` SSE cancel race, `d98d573` photo I/O
ordering, `8ed66d6` event-type collision) that hardened the pipeline
before any non-dev user touched it.

CRM-side now wants to discharge the technical debt explicitly marked
at S004 close in `CLAUDE.md`:

> *"idlaser is a vendored library dependency; canonical source at
> github.com/cropsp/idlaser; bind-mount setup is transitional,
> submodule migration planned post-S004 as S005-submodule-migrate."*

S005 CRM-side spec is at OrderHub `task.md` (commit `a472490`).
Summary:

- 9 Behaviour rules settled
- 7 OQs to resolve in CC plan-mode (Docker auth, pin strategy,
  Dockerfile staging, retry path, start-dev.sh init flow,
  old-branch compatibility, `.env` migration)
- 5-commit split on branch `s005-submodule-migrate`:
  - commit 0: frontend StrictMode useEffect fix (S004-followup-1)
  - commit 1: add submodule at `backend/external/idlaser` pinned to
    idlaser tag (this is where you come in)
  - commit 2: move `pip install -e` from runtime entrypoint to
    Dockerfile build-time + bare-metal `start-dev.sh` updates
  - commit 3: drop docker-compose `/idlaser:rw` bind-mount + update
    `IDLASER_*` config defaults
  - commit 4: docs (CLAUDE.md + AI_ONBOARDING.md + runbook)
- **Zero functional change for end users.** Pure infra refactor.
  Generate Draft → SSE → DXF pipeline identical pre- and
  post-migration.

---

## Required action — idlaser-side

### 1. Tag a release on `github.com/cropsp/idlaser` main

**Recommended tag:** `v1.0.0` — semver "first stable release used
in production-adjacent CRM deployment". Use `vX.Y.Z` format (the
`v` prefix matters; `git submodule update --remote --to-tag` expects
it).

**Commit to tag:** whatever is currently `main` HEAD in the idlaser
repo. CRM-side has been pip-installing from that HEAD since S004 commit
`d0ee31e` (2026-05-19) with no functional issues across 8 smoke
steps, so it's the de-facto stable baseline.

**Suggested release notes body** (Sergii copies this verbatim into
the GitHub Release dialog when tagging):

```
v1.0.0 — first tagged release used in OrderHub CRM submodule integration

Captures the streaming pipeline API surface (`idlaser.pipeline.process_one_streaming`)
that powers OrderHub's Generate Draft workflow as of S004-mcp-wrapper close.

Includes:
- ONNX card-detector weights at `models/card_detector.onnx` (bundled, ~80 MB)
- Default template `7001.svg` at repo root
- All public surface promised by S004 master integration contract
  Behaviour rules 1-15 (see `task.md` for full rules)

No API or behavioural changes vs current main. Tag exists primarily
to give downstream submodule consumers (OrderHub CRM) a stable pin.
Update cadence going forward: new tag per material change to public
pipeline surface or to bundled ONNX weights.
```

### 2. Confirm bundled file paths

CRM-side `backend/config.py` post-S005 will use these defaults:
- Template: `/app/external/idlaser/7001.svg`
- ONNX weights: `/app/external/idlaser/models/card_detector.onnx`

These are derived from current idlaser repo structure as seen by
S004 (template at repo root, weights under `models/`). Please
confirm both paths are correct relative to idlaser repo root at the
tag commit, OR reply with the actual paths if they've moved since
S003.2.

### 3. (Optional but recommended) `.gitignore` review

Submodule clone via `git clone --recurse-submodules` will pull
**everything in the idlaser repo, including dev artifacts** unless
ignored. Quick check: does idlaser `.gitignore` exclude
`output/`, `__pycache__/`, `*.pyc`, IDE configs, etc? If anything
heavy and dev-only is currently tracked (e.g., training outputs,
notebooks with embedded plots, intermediate model checkpoints),
consider a cleanup commit before tagging. Not blocking — CRM clone
will work either way — but tagging a clean tree is good hygiene.

---

## Verification — confirm back to OrderHub-Cowork via Sergii

Once the tag is published, reply via Sergii with:

1. **Exact tag name** (e.g. `v1.0.0`)
2. **Tag's commit SHA** — from `git rev-parse v1.0.0` on idlaser side
3. **Confirmed file paths** for template + ONNX (per action #2 above)
4. **Optional:** any `.gitignore` cleanup commit SHA if you did one

OrderHub-Cowork will then:
- Pin commit 1 of S005 to the SHA (not just the tag name — explicit
  SHA per OQ-C answer in plan mode)
- Greenlight CC plan-mode for S005 implementation
- Cross-link this doc into `task.md` so CC sees the confirmed SHA
  before it starts plan-mode

---

## Sequencing — strict order

1. **idlaser-side:** publish tag → reply via Sergii (this step)
2. **OrderHub-Cowork:** confirm SHA pin + greenlight CC plan-mode
3. **CC:** plan-mode (7 OQs) → Sergii approves plan
4. **CC:** implement commits 0-4 → gates pass → Sergii triggers smoke
5. **Sergii:** browser-MCP smoke → 8 steps green
6. **OrderHub-Cowork:** writes closure entry in `implementation_plan.md`,
   removes `S004-followup-1` row from "Explicitly deferred" table

Step 1 blocks the rest. If idlaser-side is in the middle of other
work or wants to land an API/behavioural change first, that's fine —
delay step 1 until it's appropriate. CRM-side has no time pressure;
the bind-mount setup is functional, just transitional.

---

## Out of scope for this doc

- API changes to idlaser pipeline — not requested, not expected
- ONNX retraining — not requested
- New idlaser features — not requested
- Any modification to the 15 settled Behaviour rules in master
  `task.md` — explicitly NOT relitigating

This is bootstrap mechanics only.

---

## Contact

Reply through Sergii — same courier-via-Sergii channel used during
S004. If anything in this doc is unclear or doesn't match idlaser-side
reality (e.g., file paths moved, weights regenerated, etc.), surface
the discrepancy to Sergii — DO NOT improvise. Adjustment is cheap
before commit 1; expensive after.

---

**OrderHub-Cowork sign-off:** ready when you are.

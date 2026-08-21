# ID-Laser Draft Pipeline (S004-mcp-wrapper + S005-submodule-migrate)

**Status:** describes the state of `main`. Extracted verbatim from CLAUDE.md on 2026-08-21 (docs restructuring; content unchanged).
**Read this BEFORE touching** the idlaser submodule, `backend/routers/idlaser.py`, the Generate Draft flow, draft-job schemas, or any new user-facing SSE endpoint.

## Overview

idlaser is a vendored library dependency, canonical source at github.com/cropsp/idlaser, integrated as a **git submodule at `backend/external/idlaser`**, pinned to a specific SHA (currently `e5bb5cf`, idlaser tag `v1.0.0`). The submodule is COPYed into the Docker image and editable-installed at build time; bare-metal `start-dev.sh` mirrors the install into the host venv.

The pipeline runs on the customer REFERENCE photo for an order and produces a DXF MOCKUP attachment. It exposes itself as `idlaser.api` — CRM imports only from that surface (never from `idlaser.pipeline` / `idlaser.detect` / etc.); internals may move, the `api` module won't.

Three routes ship under `backend/routers/idlaser.py`, all role-gated to OWNER/MANAGER plus the order's assigned DESIGNER:
- `POST /api/orders/{order_id}/generate-draft` — SSE stream, full pipeline.
- `POST /api/orders/{order_id}/draft-jobs/{job_id}/manual-corners` — SSE stream, resumes after manager picks 4 corners on the original photo.
- `GET  /api/orders/{order_id}/draft-jobs/{job_id}/status` — JSON polling fallback.

Frontend entry point is the "Generate Draft" button in `AttachmentManager.tsx`, enabled iff the order has ≥1 REFERENCE attachment. It opens `DraftGenerator` (modal) which subscribes to the SSE stream via `@microsoft/fetch-event-source` (native EventSource cannot POST nor send Authorization headers).

## Gotchas

- **Submodule, not requirements.txt**: idlaser lives at `backend/external/idlaser` as a git submodule and is editable-installed by the Dockerfile (`COPY ./external/idlaser` + `RUN pip install -e ./external/idlaser`). It is NOT in `backend/requirements.txt` because the path is repo-relative and idlaser is not on PyPI. Adding it to requirements.txt would break bare-metal `pip install -r requirements.txt` runs in fresh clones where the submodule isn't yet initialized. `start-dev.sh` auto-runs `git submodule update --init` if `backend/external/idlaser/pyproject.toml` is missing (see runbook below).
- **Pinning to a SHA, not a branch**: idlaser's default branch is `master`, not `main`. The submodule is pinned to a specific commit SHA, so `--branch` is intentionally absent from `.gitmodules`. To update: `cd backend/external/idlaser && git fetch && git checkout <new-sha> && cd ../../.. && git add backend/external/idlaser && git commit -m "chore: bump idlaser to <new-sha>"`.
- **Bundled ONNX weights**: idlaser's `.gitignore` whitelists `models/card_detector.onnx` (11.6 MB) so the submodule clone arrives ready-to-run. Other weights (`card_detector.pt`, `unet_resnet34_*.pth`) stay ignored — they're training-side only. Template `7001.svg` lives at the idlaser repo root (not in a `templates/` subdir).
- **Type drift risk**: `frontend/src/types/draftJob.ts` is a hand-written mirror of `backend/schemas/idlaser_draft_job.py`. There is no codegen tooling; if you change Pydantic field names/types, update the TS file too.
- **SSE pattern**: this is the codebase's first **user-facing** SSE endpoint and uses `sse_starlette.EventSourceResponse` for auto-heartbeat. The raw `StreamingResponse(media_type="text/event-stream")` in `backend/routers/mcp.py` is the MCP-protocol-specific transport and is locked; **do not treat it as a reference pattern** for new user-facing SSE.
- **Idlaser missing is non-fatal**: lifespan logs a warning if the model or template is absent. The rest of the app keeps working — only Generate Draft is unavailable.
- **`.env` migration (post-S005)**: if your local `backend/.env` predates S005 it may have `IDLASER_TEMPLATE_PATH=/idlaser/7001.svg` and `IDLASER_MODEL_PATH=/idlaser/models/card_detector.onnx` — or host paths like `/home/<user>/projects/idlaser/...` from earlier bare-metal setup. These OVERRIDE the new submodule-layout defaults silently. Entrypoint warns loudly on startup if it detects pre-S005 `/idlaser/*` paths; **host-path overrides like `/home/<user>/projects/idlaser/...` are NOT caught by the warn** and only surface via the lifespan "file missing" log line. Cleanup: unset both vars in `backend/.env` (to pick up new defaults) or update them to `/app/external/idlaser/7001.svg` and `/app/external/idlaser/models/card_detector.onnx`.
- **Pre-S005 branches**: any branch checked out from before S005 merged will lack `backend/external/idlaser/` and will fail `docker compose build` (the COPY line errors). Either re-merge `main` into the branch or temporarily revert the Dockerfile changes for archeological inspection. Operators only — Sergii is single-operator, so this is rarely encountered.

## First-time operator setup runbook

1. Clone CRM with submodules:
   ```bash
   git clone --recurse-submodules https://github.com/cropsp/OrderHub ~/projects/OrderHub
   # OR for an existing clone:
   cd ~/projects/OrderHub && git submodule update --init --recursive
   ```
2. Verify submodule populated:
   ```bash
   ls backend/external/idlaser/7001.svg \
      backend/external/idlaser/models/card_detector.onnx
   # both should print without error
   ```
3. `docker compose build backend`
   (Dockerfile COPYs `backend/external/idlaser` and runs `pip install -e ./external/idlaser` during build — no runtime install step.)
4. `docker compose up -d backend`
5. `docker compose exec backend alembic upgrade head`
6. `docker compose restart frontend` (picks up `@microsoft/fetch-event-source`).
7. Verify in browser: open any order with a REFERENCE attachment, click "Generate Draft from {filename}", confirm modal opens, SSE events stream, AUTO path produces a downloadable DXF.

## Bare-metal (non-Docker) setup

`start-dev.sh` is local-only (intentionally not committed — see `AI_ONBOARDING.md` §9). After cloning + initializing the submodule (steps 1-2 above), add the following block to your local `start-dev.sh` once, immediately after the existing `source venv/bin/activate` block (around line 65):

**If you use start-dev.sh, add locally:**

```bash
# Ensure idlaser submodule is populated and editable-installed in the venv (S005).
# Docker mode installs idlaser via Dockerfile build-time; bare-metal must mirror
# that step here so `import idlaser.api` works in the host venv.
IDLASER_DIR="$PROJECT_DIR/backend/external/idlaser"
if [ ! -f "$IDLASER_DIR/pyproject.toml" ]; then
    log "idlaser submodule empty — running git submodule update --init..."
    cd "$PROJECT_DIR"
    if ! git submodule update --init --recursive backend/external/idlaser; then
        error "git submodule update --init failed for backend/external/idlaser."
        error "Recovery:"
        error "  1. Verify read access to github.com/cropsp/idlaser (the repo is private)."
        error "  2. Configure git auth — either 'gh auth login' or an SSH deploy key."
        error "  3. Re-run: git submodule update --init --recursive"
        error "Generate Draft will be unavailable until the submodule populates."
        exit 1
    fi
    cd "$BACKEND_DIR"
fi
log "Installing idlaser (editable) into backend venv..."
pip install -e "$IDLASER_DIR" -q
```

(`PROJECT_DIR` + `BACKEND_DIR` are already defined at the top of `start-dev.sh`; this block reuses them. `cd "$BACKEND_DIR"` restores the working directory the subsequent `python seed.py` block expects.)

After applying these lines, `./start-dev.sh` handles steps 1-3 automatically on each launch — submodule init if empty + venv editable install. If submodule clone fails (auth/network), the script exits non-zero with the recovery instructions above; configure `gh auth login` or an SSH deploy key and re-run.

If step 3 fails with `COPY failed: forget to populate the submodule?` — run step 1's `git submodule update --init --recursive` first.

If step 7's "Generate Draft" button is hidden — the order has no REFERENCE attachment. Upload one via the existing Production Assets upload zone first.

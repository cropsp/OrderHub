# CLAUDE.md — OrderHub CRM

> **New AI / agent sessions:** read `docs/AI_ONBOARDING.md` first — it covers the three-actor workflow (Sergii / Cowork / CC), tooling + path mapping (UNC vs sandbox), `task.md` writing pattern, and recurring gotchas. Then this file for project rules and conventions, then `implementation_plan.md` for current state and backlog.

## Project Overview

OrderHub is a multi-channel order management CRM for a Ukrainian handcrafted leather goods business. It aggregates orders from Etsy (CSV), Shopify (API sync), and manual entry into a unified pipeline with logistics automation via Nova Poshta.

**Stack**: Python 3.11 + FastAPI (backend), React 18 + TypeScript + Vite (frontend), PostgreSQL + SQLAlchemy + Alembic (DB), JWT auth with token rotation.

## Build & Run

```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install
npm run dev          # dev server on :5173
npm run build        # production build
npm run typecheck    # must pass before committing

# Database
cd backend && alembic upgrade head   # apply migrations
alembic revision --autogenerate -m "description"  # new migration
```

## Test & Verify

```bash
# Backend tests
cd backend && python -m pytest tests/ -v
python -m pytest tests/ -k "test_name"  # single test

# Frontend checks
cd frontend && npx tsc --noEmit        # typecheck
npm run lint                            # eslint
```

**Always run typecheck + lint after frontend changes. Always run pytest after backend changes.**

## Architecture (Key Decisions)

- **Monorepo**: `/backend` and `/frontend` at root level, `/docs` for documentation.
- **Routers**: `backend/routers/` — one file per domain (orders, shops, dashboard, imports, users, auth, shipping, mcp).
- **Services**: `backend/services/` — business logic separated from routes. Shopify sync, Nova Poshta API, Etsy CSV parser, encryption service.
- **Frontend pages**: `frontend/src/pages/` — one page component per route.
- **Component hierarchy**: `components/layout/` (shell, topbar), `components/ui/` (reusable), `components/orders/` (order-specific with `detail/` sub-components).
- **State**: Zustand for auth (`authStore.ts`). React Query for server state. No Redux.
- **API client**: `frontend/src/api/` — Axios with interceptors for JWT refresh and error handling.
- **Styling**: Tailwind CSS with zinc-950 dark theme. No CSS modules.

## Database Conventions

- All models use SQLAlchemy ORM with Alembic migrations. **Never** modify DB schema directly — always create a migration.
- Enums in Python must match DB enum types exactly. When adding a new enum value, create an Alembic migration with `ALTER TYPE`.
- Shop `platform` field uses the `ShopPlatform` enum (DB type `shop_platform`): `SHOPIFY`, `ETSY`, `MANUAL` (there is no `ShopSource` enum). See `models/shop.py`.
- Order status changes AND field mutations are logged in the `order_status_history` table (`models/order.py`) — `update_order` writes a row with `from_status == to_status` and `comment="Fields updated: …"`. There is no `order_audit_history` table.
- Product catalog: `products` → `product_variants` → `packaging_specs`. Order items link via SKU with atomic snapshots.

## Nova Poshta Integration

- All NP API keys are Fernet-encrypted in DB, masked in UI.
- Sender references cached in DB — zero redundant API calls.
- Recipient search uses debounced input with dropdown positioning.
- Dates must be Kyiv timezone (`Europe/Kiev`). Use `ENCRYPTION_KEY` env var.
- TTN (tracking numbers) support create and delete operations.

## Code Style & Conventions

- Backend: snake_case, type hints on all function signatures, Pydantic models for request/response.
- Frontend: PascalCase components, camelCase functions/variables, TypeScript strict mode.
- Imports: group by stdlib → third-party → local, alphabetical within groups.
- Error handling: backend returns structured `{"detail": "..."}` errors. Frontend shows via Toast component.
- No `any` type in TypeScript unless migrating legacy code (mark with `// TODO: type properly`).

## What's Done (Don't Rebuild)

Sprints 1–10 + UI Modernization are complete. This includes: core architecture, DB & auth, full frontend, dashboard analytics, Shopify/Etsy/NP integrations, MCP server with auth guards, attachments/designer workflow, shop management, manual order entry, product catalog with CSV import, parcel calculation service, and all admin UIs. See `implementation_plan.md` for full history.

## What's Pending

Sprint 11 (Production & Deployment): Prometheus/Grafana monitoring.
(SSL/remote access is DONE via Cloudflare Tunnel — see below.
**DB backups are DONE** since 2026-07-13 — systemd timer → `age`-encrypted tarball → Cloudflare R2,
daily, restore tested. Canonical reference: `BACKUP_PLAN.md`. One gap remains: no alerting if a
backup fails or silently stops — tracked as `S11-2-followup-1` in `implementation_plan.md`.)
Performance: route-level chunk splitting (frontend). Testing: smoke tests with Vitest + Playwright.

## Server Deployment (LAN + Cloudflare Tunnel)

The app runs on a single hardened Ubuntu box, `prorder@192.168.31.71` (`ssh orderhub`),
as a Docker Compose stack. **Canonical reference: `SERVER_DEPLOY_PLAN.md` (§1–§10).** Key facts:

- **Server-only overlay files** (NOT in the repo — they live at `/home/prorder/OrderHub/`
  and travel by `scp`, never committed): `docker-compose.prod.yml`, `backend/Dockerfile.deploy`
  + `frontend/Dockerfile.deploy` (idlaser-less builds), and the secret `.env` (`chmod 600`,
  git-ignored). idlaser is **deferred** on the server — Generate Draft is unavailable there; the
  rest of the app is unaffected.
- **Public URL: `https://orderhub.orderapp.uk`** via a **Cloudflare Tunnel** (`cloudflared`
  service in `docker-compose.prod.yml`). **Zero inbound ports** — cloudflared is outbound-only,
  joins the `orderhub_default` network, and reaches the app at `http://frontend:80` (nginx serves
  the SPA + proxies `/api/` → `backend:8000`). The `TUNNEL_TOKEN` lives in the server `.env`.
  Public hostname routing + Cloudflare Access policy are managed in the **Cloudflare dashboard**,
  not in this repo — there is no local ingress/config file.
- **`FRONTEND_URL=https://orderhub.orderapp.uk`** in the server `.env` is the app's **sole CORS
  allow-origin** (`main.py:71`). There is deliberately no `TrustedHostMiddleware`/`ALLOWED_HOSTS`/
  CSRF list — if you add one, also allow the tunnel hostname.
- **Nothing is published to the LAN.** The frontend `80:80` publish was removed; only postgres
  is bound, and only to `127.0.0.1`. **ufw stays SSH-only** — do not open app ports. To reach the
  app, use the HTTPS hostname (not the LAN IP: the prod refresh cookie is `secure=True`, so
  login/refresh won't work over plain `http://192.168.31.71`).
- **Apply config/env changes** with `docker compose -f docker-compose.prod.yml up -d <svc>`
  (recreate to reload `.env`, no rebuild). Timestamped `.bak.*` copies of `.env` /
  `docker-compose.prod.yml` are kept on the server before each change.

## Behavioral Guidelines

1. **Think before coding.** State assumptions explicitly. If multiple approaches exist, present tradeoffs — don't pick silently. If something is unclear, ask before implementing.

2. **Simplicity first.** Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no "flexibility" that wasn't requested.

3. **Surgical changes.** Touch only what the task requires. Don't "improve" adjacent code. Match existing style. If your changes orphan imports/variables, clean those up — but don't delete pre-existing dead code unless asked.

4. **Verify your work.** Define success criteria before implementing. Run tests, typecheck, and lint. For multi-step tasks, state a plan with verification at each step:
   ```
   1. [Step] → verify: [check]
   2. [Step] → verify: [check]
   ```

5. **Respect what exists.** This codebase has 10+ completed sprints of deliberate decisions. Read existing code before proposing changes. Don't refactor working systems without explicit request.

## Gotchas

- The shop platform enum is `ShopPlatform` (`SHOPIFY|ETSY|MANUAL`, DB type `shop_platform`) — there is no `ShopSource` enum and no `ALTER TYPE … ADD VALUE` migration for it (corrected USER-ACCESS-2). No enum value has ever been added post-hoc; `ShopPlatform` shipped complete in the initial schema.
- Order status changes MUST go through the audit logging path (`order_status_history`) — never update status directly in DB.
- Frontend `OrderDetailPanel` was refactored into 8 sub-components in `detail/` — don't re-merge them.
- Nova Poshta refs auto-clear on manual address input — this is intentional, not a bug.
- Backend logs rotate at 25MB cap in `backend/logs/server.log`.
- `CreateOrderPage.tsx` is a full-page form, not a modal — this was a deliberate UX decision.
- **MCP server (rebuilt 2026-07-27, branch `feat/mcp-warehouse`):** the old `backend/routers/mcp.py` was **deleted** (never worked). The current MCP is a **separate local stdio process** at `mcp_server/` — a warehouse/catalog agent that drives the CRM's own REST API as a MANAGER agent user (`agent@orderhub.dev`), so all existing guards cover it; writes audited in `agent_action_log`. Usage + tools: `mcp_server/README.md`. Connection + prod rollout + where creds live: `docs/integrations/mcp-server.md`. It is NOT part of the FastAPI app and has its own venv (SDK needs pydantic ≥2.11; app pinned 2.10.4). Do not re-add an in-app MCP router.
- Shop access (USER-ACCESS-1, supersedes SEC-05): access to a shop is an **explicit grant** in the `user_shop_access` table, resolved by `access_service.get_shop_scope` (returns a `ShopScope` value object — never a None sentinel) and enforced by `assert_shop_access` (shop-id surfaces) / `assert_order_access` (order surfaces) in `routers/dependencies.py`. OWNER is unrestricted (superuser; no grant rows — the resolver short-circuits). MANAGER/DESIGNER see only granted shops. **Assignment wins:** a designer always sees orders assigned to them, and assigning an order to a designer auto-materialises their grant for that shop (hook in `order_service.update_order` + `change_order_status`), so order-level and shop-level access stay coherent.
- Historical correction: SEC-05's original guard (`get_shop_for_user`) reached only **4 catalog endpoints** and derived designer access from order assignments — it did NOT gate "all shop-level endpoints". USER-ACCESS-1 replaced derivation with explicit grants and swept enforcement across orders (list/detail/mutations/CSV export), dashboard aggregates, finance (closed the any-manager-reads-any-P&L hole), shops (list/detail), products (incl. by-id), partner_payouts, imports, overhead receipts, attachments, and shipping TTNs.
- Deliberately unscoped (global, no `shop_id`): materials + packaging catalogs, dashboard low-stock packaging + unallocated (NULL-shop) overhead, and the NP city/warehouse lookup utilities. New shops auto-grant to effectively-unrestricted managers only; new managers default to all shops at creation. See `implementation_plan.md` USER-ACCESS-1 and `tests/test_route_scope_completeness.py` (the classification that fails if a new `{shop_id}` route is left unclassified).
- System user UUID `00000000-0000-0000-0000-000000000001` (`backend/constants.py:SYSTEM_USER_ID`) is referenced by webhook/scheduler audit rows. Never delete; never reuse. Installed by alembic migration `a1b2c3d4e5f6_add_persistent_system_user`.
- Money visibility (USER-ACCESS-2): **capability flags** compose with shop scope. `view_finance` (P&L / dashboard revenue / partner payouts) and `view_costs` (itemised costs: per-order `FINANCIAL_FIELDS` + `computed_production_cost`, product `cost_price` + BOM cost, material/overhead unit costs, finance COGS cards) live in `user_capability` (no row = role default; `models.user.Capability` is a plain String, NOT a PG enum). Resolved by `access_service.get_capabilities` → a `CapabilitySet` value object (`has(cap)`, never a None sentinel); enforced by `assert_capability` / `require_capability` in `routers/dependencies.py`. OWNER holds every capability (resolver short-circuit; no rows). **Backfill preserved today's incoherence:** existing MANAGERs → `view_finance=true, view_costs=false`; new non-owner users default deny-by-default (both false). **Cost censoring is null-in-200 on mixed surfaces** (orders list+detail share `order_service.censor_order_financials`; product `cost_price`/BOM cost nulled) and **403 on cost-only endpoints** (`/products/{id}/bom/cost`, materials/overhead routers). `view_finance`-without-`view_costs` sees revenue + net_profit but the itemised cost cards are stripped (dashboard + finance, OQ-3a: total cost stays inferable from net_profit — accepted). **Completeness is guarded by `tests/test_money_field_completeness.py`** — it fails if a new numeric response field or money route is left unclassified (this is how LEAK 1/2 would now be caught). Grant/revoke of both shop access and capabilities is recorded in the `access_audit` table (actor defaults to `SYSTEM_USER_ID` for automated writes).
- **Partner payouts (PARTNER-CONFIG-1, merged + deployed 2026-08-07):** partners are a **global entity** (`partners`) + per-shop config in `shop_partner_config` (percent, basis, settlement currency), edited in the shop editor's Partners tab, **OWNER-only**. Settlement bases: `TURNOVER` and `PROFIT` — both net of discounts, both deduct refunds **dated in the period** (Model 2), and both **exclude shipping economics entirely** (`docs/design/profit-definition.md` §6; PROFIT ≠ the Finance-page net profit, which nets shipping — see `NETPROFIT-RECONCILE`). Legacy enum values `REVENUE_ITEMS_MINUS_FEES` / `NET_PROFIT_PRODUCT_ONLY` deserialise but are not selectable for new configs. Settlements/payments stay **immutable post-create**; overlapping periods per (shop, partner) are **hard-blocked server-side** (`_overlap_predicate`, closed-interval); negative bases produce negative settlements by design. UAH terms (in practice: allocated overhead) convert via `fx_service.resolve()` at Calculate time and the rate freezes onto `PartnerSettlement.fx_rate_used` — no usable rate is a loud 422, never a dropped term. Unallocated (NULL-shop) overhead never enters a partner base. Partner-config changes audit to **`partner_config_audit`** (NOT `access_audit` — its `target_user_id` means "whose access changed"; a partner is not a user), and partner entities must not be hard-deleted while audit rows reference them. `PartnerSettlementFormula` is a **PG enum**; the PARTNER-CONFIG-1 migration docstring carries a standing rule that no future migration may write the two new values in its own transaction (PG16 same-transaction restriction — hence no `server_default`/CHECK on `shop_partner_config.basis`). Fee backfill: `POST /api/shops/{shop_id}/backfill-platform-fees` (OWNER-only, `dry_run` first, never overwrites a non-NULL fee, skips CANCELLED, reports `overlapping_settlements`).

## ID-Laser draft pipeline (S004-mcp-wrapper + S005-submodule-migrate)

idlaser is a vendored library dependency, canonical source at github.com/cropsp/idlaser, integrated as a **git submodule at `backend/external/idlaser`**, pinned to a specific SHA (currently `e5bb5cf`, idlaser tag `v1.0.0`). The submodule is COPYed into the Docker image and editable-installed at build time; bare-metal `start-dev.sh` mirrors the install into the host venv.

The pipeline runs on the customer REFERENCE photo for an order and produces a DXF MOCKUP attachment. It exposes itself as `idlaser.api` — CRM imports only from that surface (never from `idlaser.pipeline` / `idlaser.detect` / etc.); internals may move, the `api` module won't.

Three routes ship under `backend/routers/idlaser.py`, all role-gated to OWNER/MANAGER plus the order's assigned DESIGNER:
- `POST /api/orders/{order_id}/generate-draft` — SSE stream, full pipeline.
- `POST /api/orders/{order_id}/draft-jobs/{job_id}/manual-corners` — SSE stream, resumes after manager picks 4 corners on the original photo.
- `GET  /api/orders/{order_id}/draft-jobs/{job_id}/status` — JSON polling fallback.

Frontend entry point is the "Generate Draft" button in `AttachmentManager.tsx`, enabled iff the order has ≥1 REFERENCE attachment. It opens `DraftGenerator` (modal) which subscribes to the SSE stream via `@microsoft/fetch-event-source` (native EventSource cannot POST nor send Authorization headers).

**Gotchas:**

- **Submodule, not requirements.txt**: idlaser lives at `backend/external/idlaser` as a git submodule and is editable-installed by the Dockerfile (`COPY ./external/idlaser` + `RUN pip install -e ./external/idlaser`). It is NOT in `backend/requirements.txt` because the path is repo-relative and idlaser is not on PyPI. Adding it to requirements.txt would break bare-metal `pip install -r requirements.txt` runs in fresh clones where the submodule isn't yet initialized. `start-dev.sh` auto-runs `git submodule update --init` if `backend/external/idlaser/pyproject.toml` is missing (see runbook below).
- **Pinning to a SHA, not a branch**: idlaser's default branch is `master`, not `main`. The submodule is pinned to a specific commit SHA, so `--branch` is intentionally absent from `.gitmodules`. To update: `cd backend/external/idlaser && git fetch && git checkout <new-sha> && cd ../../.. && git add backend/external/idlaser && git commit -m "chore: bump idlaser to <new-sha>"`.
- **Bundled ONNX weights**: idlaser's `.gitignore` whitelists `models/card_detector.onnx` (11.6 MB) so the submodule clone arrives ready-to-run. Other weights (`card_detector.pt`, `unet_resnet34_*.pth`) stay ignored — they're training-side only. Template `7001.svg` lives at the idlaser repo root (not in a `templates/` subdir).
- **Type drift risk**: `frontend/src/types/draftJob.ts` is a hand-written mirror of `backend/schemas/idlaser_draft_job.py`. There is no codegen tooling; if you change Pydantic field names/types, update the TS file too.
- **SSE pattern**: this is the codebase's first **user-facing** SSE endpoint and uses `sse_starlette.EventSourceResponse` for auto-heartbeat. The raw `StreamingResponse(media_type="text/event-stream")` in `backend/routers/mcp.py` is the MCP-protocol-specific transport and is locked; **do not treat it as a reference pattern** for new user-facing SSE.
- **Idlaser missing is non-fatal**: lifespan logs a warning if the model or template is absent. The rest of the app keeps working — only Generate Draft is unavailable.
- **`.env` migration (post-S005)**: if your local `backend/.env` predates S005 it may have `IDLASER_TEMPLATE_PATH=/idlaser/7001.svg` and `IDLASER_MODEL_PATH=/idlaser/models/card_detector.onnx` — or host paths like `/home/<user>/projects/idlaser/...` from earlier bare-metal setup. These OVERRIDE the new submodule-layout defaults silently. Entrypoint warns loudly on startup if it detects pre-S005 `/idlaser/*` paths; **host-path overrides like `/home/<user>/projects/idlaser/...` are NOT caught by the warn** and only surface via the lifespan "file missing" log line. Cleanup: unset both vars in `backend/.env` (to pick up new defaults) or update them to `/app/external/idlaser/7001.svg` and `/app/external/idlaser/models/card_detector.onnx`.
- **Pre-S005 branches**: any branch checked out from before S005 merged will lack `backend/external/idlaser/` and will fail `docker compose build` (the COPY line errors). Either re-merge `main` into the branch or temporarily revert the Dockerfile changes for archeological inspection. Operators only — Sergii is single-operator, so this is rarely encountered.

**First-time operator setup runbook:**

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

**Bare-metal (non-Docker) setup:** `start-dev.sh` is local-only (intentionally not committed — see `AI_ONBOARDING.md` §9). After cloning + initializing the submodule (steps 1-2 above), add the following block to your local `start-dev.sh` once, immediately after the existing `source venv/bin/activate` block (around line 65):

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
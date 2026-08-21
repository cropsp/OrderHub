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
npm run dev          # dev server on :3000 (vite.config.ts:16 — NOT Vite's default 5173)
npm run build        # tsc -b && vite build — ЧЕРВОНИЙ на main, див. § Test & Verify
npx tsc -p tsconfig.app.json --noEmit   # typecheck — див. § Test & Verify

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
cd frontend && npx tsc -p tsconfig.app.json --noEmit   # typecheck — THE REAL ONE
npm run lint                                            # eslint
```

> ⚠️ **`npx tsc --noEmit` — це no-op. Не використовуй її.** Кореневий `tsconfig.json` є solution-файлом з `"files": []`, тож команда перевіряє **нуль** файлів із `src/` і завжди виходить із кодом 0. Перевірено `--listFiles` тричі (останній раз 2026-08-17). Агенти регулярно доповідають «typecheck чисто», виконавши саме її — рівно тому, що ця інструкція раніше стояла тут.
>
> Справжній тайпчек — `npx tsc -p tsconfig.app.json --noEmit`. **Станом на 2026-08-17 він дає 21 помилку на `main`** (див. `TYPECHECK-1` в `implementation_plan.md`): 1 справжній дефект (`RevenueChart.tsx:63`), 7 implicit-any, 8 мертвих імпортів/змінних, 5 конфігурних. Це успадкований борг, не твоя регресія — але **порівнюй свій результат із цим числом**, а не з нулем.
>
> `npm run build` (`tsc -b && vite build`) червоний з тієї ж причини. Прод це не ламає: `frontend/Dockerfile.deploy` збирає через `npx vite build`, який тайпчек не запускає взагалі (`PROD-BUILD-NO-TYPECHECK`). Наслідок, який варто тримати в голові: **на шляху до продакшену типи не перевіряє ніхто, крім тебе вручну.**

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
- Backend logs rotate at 25MB cap in `backend/logs/server.log` (dev). **On prod the durable log is `/home/prorder/orderhub-logs/server.log`** — `backend/logs/` inside the container is ephemeral (PROD-LOGS-EPHEMERAL, 2026-08-06).
- `CreateOrderPage.tsx` is a full-page form, not a modal — this was a deliberate UX decision.
- **MCP server (rebuilt 2026-07-27, branch `feat/mcp-warehouse`):** the old `backend/routers/mcp.py` was **deleted** (never worked). The current MCP is a **separate local stdio process** at `mcp_server/` — a warehouse/catalog agent that drives the CRM's own REST API as a MANAGER agent user (`agent@orderhub.dev`), so all existing guards cover it; writes audited in `agent_action_log`. Usage + tools: `mcp_server/README.md`. Connection + prod rollout + where creds live: `docs/integrations/mcp-server.md`. It is NOT part of the FastAPI app and has its own venv (SDK needs pydantic ≥2.11; app pinned 2.10.4). Do not re-add an in-app MCP router.
- **Access control (USER-ACCESS-1/2):** shop access is an **explicit grant** (`user_shop_access`, resolved by `access_service.get_shop_scope`, enforced in `routers/dependencies.py`); money visibility is **capability flags** (`view_finance` / `view_costs`) composing with shop scope; OWNER short-circuits both. Completeness is executable: `tests/test_route_scope_completeness.py` + `tests/test_money_field_completeness.py` fail on unclassified new routes/fields. **Before touching any endpoint that reads shops, orders, money, or costs — read `docs/design/access-control.md`** (full model, censoring rules, unscoped surfaces, defaults, audit).
- System user UUID `00000000-0000-0000-0000-000000000001` (`backend/constants.py:SYSTEM_USER_ID`) is referenced by webhook/scheduler audit rows. Never delete; never reuse. Installed by alembic migration `a1b2c3d4e5f6_add_persistent_system_user`.
- **Partner payouts (PARTNER-CONFIG-1, deployed 2026-08-07):** OWNER-only per-shop config; bases `TURNOVER`/`PROFIT` (net of discounts, deduct period-dated refunds, exclude shipping entirely; PROFIT ≠ the Finance-page net profit — `NETPROFIT-RECONCILE`); settlements immutable post-create, overlapping periods hard-blocked, negative bases produce negative settlements by design. **Before touching partners, settlements, or platform fees — read `docs/design/partner-config-current.md`**; authoritative history: `implementation_plan.md` → PARTNER-CONFIG-1.
- **Warehouse (WH-1 + WH-2, 2026-08):** every packaging box is 1:1 paired with a `Material` (paired lifecycle is `catalog_service`-only); packaging is consumed **once per parcel at SHIPPED**, never per product, and is deliberately not a BOM line; TTN operations no longer touch stock; `packaging_stock_movements` is frozen; the consumption block may never raise (NP label already minted). **Before touching materials, packaging, BOM, consumption/receipts, or the SHIPPED path — read `docs/warehouse/warehouse-invariants.md`** (why it's built this way: `docs/warehouse/DESIGN-inventory-architecture.md`).

## ID-Laser draft pipeline

idlaser is a vendored **git submodule at `backend/external/idlaser`** (pinned to a SHA, not a branch), editable-installed at build time; CRM imports **only** from `idlaser.api`. Generate Draft runs on an order's REFERENCE photo and produces a DXF MOCKUP via SSE routes in `backend/routers/idlaser.py` (role-gated: OWNER/MANAGER + assigned DESIGNER). Missing idlaser is non-fatal — only Generate Draft is unavailable (deliberately so on prod). **Before touching the submodule, draft pipeline, draft-job schemas, or adding any user-facing SSE endpoint — read `docs/integrations/idlaser.md`** (all gotchas, operator runbook, bare-metal setup).
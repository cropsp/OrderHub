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
- Shop `source` field uses `ShopSource` enum: `SHOPIFY`, `ETSY`, `MANUAL`.
- Order status mutations are logged in `order_audit_history` table.
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

Sprint 11 (Production & Deployment): SSL/nginx, DB backup jobs, Prometheus/Grafana monitoring.
Performance: route-level chunk splitting (frontend). Testing: smoke tests with Vitest + Playwright.

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

- `ShopSource.MANUAL` enum was added via migration — if you see enum conflicts, check Alembic history first.
- Order status changes MUST go through the audit logging path — never update status directly in DB.
- Frontend `OrderDetailPanel` was refactored into 8 sub-components in `detail/` — don't re-merge them.
- Nova Poshta refs auto-clear on manual address input — this is intentional, not a bug.
- Backend logs rotate at 25MB cap in `backend/logs/server.log`.
- `CreateOrderPage.tsx` is a full-page form, not a modal — this was a deliberate UX decision.
- MCP server development is paused — do not modify `backend/routers/mcp.py` unless explicitly asked. See `docs/integrations/mcp-server.md` for context.
- Designer shop access (SEC-05): a designer is granted access to a shop only if they have at least one order in that shop assigned to them. A designer with zero assignments gets 403 on every shop-scoped endpoint — onboarding must assign at least one order before the designer can use the system.
- Designer access is shop-scoped, not order-scoped: a designer with any assigned order in shop X can access all shop-level endpoints (products, packaging, config) for that shop. Fine-grained order-level checks only apply in orders and attachments routers.
- System user UUID `00000000-0000-0000-0000-000000000001` (`backend/constants.py:SYSTEM_USER_ID`) is referenced by webhook/scheduler audit rows. Never delete; never reuse. Installed by alembic migration `a1b2c3d4e5f6_add_persistent_system_user`.
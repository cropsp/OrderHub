# OrderHub CRM - Implementation Plan

## How To Use This File

This file is the operational execution plan for the repository.

Use it for:

- sprint scope
- task status
- next implementation steps
- known mismatches between plan and actual codebase
- verification checkpoints

Do not duplicate stable architecture here. Stable project logic belongs in `ORDERHUB_CONTEXT.md`.

## Status Snapshot

Last reviewed: `2026-04-20`

- Active sprint: `Sprint 4 - Core Frontend`
- Sprint 1 status: `DONE`
- Sprint 2 status: `DONE`
- Sprint 3 status: `DONE`
- Sprint 4 status: `NOT STARTED`
- Sprint 5 status: `NOT STARTED`
- Sprint 6 status: `NOT STARTED`

## Actual Repository Snapshot

Verified against the current tree before editing this file.

Backend present now:

- app bootstrap and config
- models, schemas, routers, services
- Alembic migration setup
- seed script

Frontend present now:

- `main.tsx`
- `App.tsx` with protected route shell
- auth API layer
- orders and shops API modules
- auth store and hook
- orders and shops React Query hooks
- `pages/` with login, dashboard and shell placeholders
- `components/layout/` with sidebar, topbar and app layout
- `components/auth/RouteGuards.tsx`
- base UI primitives in `components/ui`

Frontend not present yet:

- `src/components/orders/`
- `src/components/dashboard/`
- full feature pages for sprint 4/5

Planned backend files not present yet:

- `backend/mcp_server.py`
- `backend/services/shopify_sync.py`
- `backend/services/scheduler.py`
- `backend/services/email_service.py`
- `backend/services/nova_poshta.py`

## Plan Corrections

These were inaccurate in the previous version of the plan and are now normalized:

1. The old plan mixed current filesystem state with target structure. This file now separates actual repository state from planned work.
2. `Sprint 3 / Task 3.7` was marked `TODO`, but base UI primitives already exist in `frontend/src/components/ui`.
3. The plan used `kanban`, `pipeline`, and `board` inconsistently. The canonical UI language is now:
   `smart table` as primary view, `pipeline board` as secondary view.
4. Final verification still mentioned drag-and-drop, but drag-and-drop was previously removed from scope. Verification now checks inline status changes instead.
5. `Task 3.6` referenced React Query hooks under `frontend/src/api/`, while the intended split is API clients in `api/` and React Query hooks in `hooks/`.
6. The old structure section listed files like `tailwind.config.ts` and multiple page modules as if they already existed. They do not exist yet in the current repository.

## Working Rules

- When a task is finished, update its status in this file immediately.
- When a sprint assumption becomes false, add it to `Plan Corrections` before continuing.
- Keep task IDs stable so future updates can reference them unambiguously.
- Every sprint should end with at least one concrete verification step.

## Sprint 1 - Foundation

Goal: boot the project in Docker with database, auth, migrations, and seed data.

Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S1-1 | Environment and Compose setup | root config | DONE |
| S1-2 | Backend container setup | `backend/` | DONE |
| S1-3 | App settings and database setup | `backend/config.py`, `backend/database.py` | DONE |
| S1-4 | Core database models and migration | `backend/models/`, `backend/alembic/` | DONE |
| S1-5 | FastAPI app skeleton | `backend/main.py` | DONE |
| S1-6 | Auth endpoints and token services | `backend/routers/auth.py`, `backend/services/auth_service.py` | DONE |
| S1-7 | User CRUD | `backend/routers/users.py` | DONE |
| S1-8 | Encryption helpers | `backend/services/encryption_service.py` | DONE |
| S1-9 | Seed data | `backend/seed.py` | DONE |
| S1-10 | Frontend bootstrap | `frontend/` | DONE |
| S1-11 | Frontend dev and prod containers | `frontend/Dockerfile*`, `frontend/nginx.conf` | DONE |

Verification:

- `docker compose -f docker-compose.dev.yml up` should start backend, frontend, and PostgreSQL.

## Sprint 2 - Core Backend API

Goal: complete the business API for shops, orders, imports, customers, attachments, and dashboard stats.

Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S2-1 | Pydantic schemas for current models | `backend/schemas/` | DONE |
| S2-2 | Shop CRUD with encrypted secret handling | `backend/routers/shops.py` | DONE |
| S2-3 | Customer upsert logic | `backend/services/customer_service.py` | DONE |
| S2-4 | Orders CRUD with filters and pagination | `backend/routers/orders.py` | DONE |
| S2-5 | Order status transition validation and history | `backend/services/order_service.py` | DONE |
| S2-6 | Etsy CSV parser | `backend/services/etsy_parser.py` | DONE |
| S2-7 | Etsy import endpoint | `backend/routers/imports.py` | DONE |
| S2-8 | Attachment storage and endpoints | `backend/services/file_storage.py`, `backend/routers/attachments.py` | DONE |
| S2-9 | Customer endpoints | `backend/routers/customers.py` | DONE |
| S2-10 | Dashboard stats API | `backend/routers/dashboard.py` | DONE |
| S2-11 | CSV export | `backend/routers/orders.py` | DONE |

Verification:

- backend endpoints should be manually testable through `/docs`

## Sprint 3 - Frontend Shell

Goal: establish auth flow, route shell, layout shell, and reusable frontend structure.

Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S3-1 | Axios client with token refresh interceptor | `frontend/src/api/client.ts` | DONE |
| S3-2 | Auth store and `useAuth` hook | `frontend/src/store/`, `frontend/src/hooks/` | DONE |
| S3-3 | Login page module | `frontend/src/pages/LoginPage.tsx` | DONE |
| S3-4 | App layout modules: sidebar, topbar, shell | `frontend/src/components/layout/` | DONE |
| S3-5 | Protected route configuration | `frontend/src/App.tsx`, `frontend/src/components/auth/` | DONE |
| S3-6 | Orders and shops data hooks with React Query | `frontend/src/api/`, `frontend/src/hooks/` | DONE |
| S3-7 | Base UI primitives | `frontend/src/components/ui/` | DONE |

Notes:

- Protected route guards redirect unauthenticated users to `/login`.
- Role-based route guards are active for owner/manager sections.
- React Query is wired in `frontend/src/main.tsx` and used by shops/orders hooks.

Verification:

- login route should render a real page module
- unauthorized users should be redirected correctly
- authenticated shell should resolve through protected routes

## Sprint 4 - Core Frontend

Goal: implement actual order workflows in the UI.

Status: `NOT STARTED`

| ID | Task | Scope | Status |
|---|---|---|---|
| S4-1 | Status tabs for grouped order states | `StatusTabs.tsx` | TODO |
| S4-2 | Smart orders table | `OrdersTable.tsx` | TODO |
| S4-3 | Pipeline board | `PipelineBoard.tsx` | TODO |
| S4-4 | List and board view toggle | `ViewToggle.tsx` | TODO |
| S4-5 | Per-shop orders page | `ShopOrdersPage.tsx` | TODO |
| S4-6 | Order detail panel | `OrderDetailPanel.tsx` | TODO |
| S4-7 | CSV import page | `ImportPage.tsx` | TODO |
| S4-8 | Customers page | `CustomersPage.tsx` | TODO |

Verification:

- import CSV -> orders appear in UI
- smart table and pipeline board use the same order data source
- status changes happen through inline controls, not drag-and-drop
- order details expose items, notes, history, and attachments

## Sprint 5 - Dashboard, Archive, Management

Goal: finish analytics, archival view, and management screens.

Status: `NOT STARTED`

| ID | Task | Scope | Status |
|---|---|---|---|
| S5-1 | Dashboard stat cards | `DashboardPage.tsx` | TODO |
| S5-2 | Revenue chart | `RevenueChart.tsx` | TODO |
| S5-3 | Shop breakdown chart | `ShopBreakdownChart.tsx` | TODO |
| S5-4 | Attention list | `AttentionList.tsx` | TODO |
| S5-5 | Recent activity block | `DashboardPage.tsx` | TODO |
| S5-6 | Archive page | `ArchivePage.tsx` | TODO |
| S5-7 | Shops management page | `ShopsPage.tsx` | TODO |
| S5-8 | User management page | `UsersPage.tsx` | TODO |
| S5-9 | Settings page | `SettingsPage.tsx` | TODO |

Verification:

- dashboard renders stats from backend APIs
- archive supports filtering and CSV export path
- management pages enforce role restrictions

## Sprint 6 - Integrations and MCP

Goal: add external integrations and expose CRM operations through MCP.

Status: `NOT STARTED`

| ID | Task | Scope | Status |
|---|---|---|---|
| S6-1 | Nova Poshta API client | `backend/services/nova_poshta.py` | TODO |
| S6-2 | Shopify sync service | `backend/services/shopify_sync.py` | TODO |
| S6-3 | Scheduler for sync jobs | `backend/services/scheduler.py` | TODO |
| S6-4 | Manual sync trigger | `backend/routers/shops.py` | TODO |
| S6-5 | Email service | `backend/services/email_service.py` | TODO |
| S6-6 | Nova Poshta connection test endpoint | `backend/routers/shops.py` | TODO |
| S6-7 | MCP server read tools | `backend/mcp_server.py` | TODO |
| S6-8 | MCP server write tools | `backend/mcp_server.py` | TODO |
| S6-9 | MCP auth and role checks | `backend/mcp_server.py` | TODO |
| S6-10 | Integration and MCP documentation | `README.md` | TODO |

Verification:

- MCP client can read CRM data
- MCP client can perform controlled write operations
- external integrations respect encrypted credentials and role restrictions

## Next Action

Primary next implementation step:

- `S4-1` Build status tabs for grouped order states

Follow-up after that:

- `S4-2` Build smart orders table
- `S4-3` Build pipeline board

## Final Verification Checklist

- [ ] Owner, manager, and designer auth flows work
- [ ] Etsy CSV import produces orders visible in the UI
- [ ] Orders can change status through inline UI controls
- [ ] Order details show items, notes, attachments, and history
- [ ] Per-shop orders view works
- [ ] Dashboard renders analytics from backend data
- [ ] Archive supports export flow
- [ ] MCP integration works for read and write operations
- [ ] Designer access is limited to assigned work

## Worklog

- `2026-04-20` Rewrote plan structure to separate stable context from execution state.
- `2026-04-20` Normalized terminology around `smart table` and `pipeline board`.
- `2026-04-20` Corrected outdated references to drag-and-drop and current filesystem state.
- `2026-04-20` Completed Sprint 3 tasks S3-3 to S3-6 and verified frontend build.
- `2026-04-20` Starting S4-6. Note: Editing of internal notes, TTN, and customer info in the Detail Panel is deferred to Sprint 5. S4-6 remains read-only for now (viewing items, shipping, and history).

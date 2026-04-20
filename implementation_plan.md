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

- Sprint 1 status: `DONE`
- Sprint 2 status: `DONE`
- Sprint 3 status: `DONE`
- Sprint 4 status: `DONE`
- Sprint 5 status: `DONE`
- Sprint 6 status: `DONE`
- Sprint 7 status: `DONE` (Restoration & Stability)

## Actual Repository Snapshot

Verified against the current tree:

**Backend:**
- Fully implemented routers for all modules (Orders, Shops, Dashboard, Imports, Users, Auth, Shipping, MCP).
- Services for Shopify Sync, Nova Poshta, Encryption, and Etsy parsing are active.
- Database models and migrations are stable.

**Frontend:**
- Completed all primary feature pages (Orders, Dashboard, Customers, Imports, Archive, Shops, Users, Settings).
- Full component set for Orders (Table, Board, Detail Panel, Status Tabs).
- Analytics components (Revenue, Shop charts, attention list, recent activity) are integrated.
- Build stability verified via Vite.

## Sprint 4 - Core Frontend
Goal: implement actual order workflows in the UI.
Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S4-1 | Status tabs for grouped order states | `StatusTabs.tsx` | DONE |
| S4-2 | Smart orders table | `OrdersTable.tsx` | DONE |
| S4-3 | Pipeline board | `PipelineBoard.tsx` | DONE |
| S4-4 | List and board view toggle | `ViewToggle.tsx` | DONE |
| S4-5 | Per-shop orders page | `/shops/:shopId/orders` | DONE |
| S4-6 | Order detail panel | `OrderDetailPanel.tsx` | DONE |
| S4-7 | CSV import page | `ImportsPage.tsx` | DONE |
| S4-8 | Customers integration | `frontend/src/api/customers.ts`, `CustomersPage.tsx` | DONE |

## Sprint 5 - Dashboard, Archive, Management
Goal: finish analytics, archival view, and management screens.
Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S5-1 | Dashboard stat cards | `StatCards.tsx` | DONE |
| S5-2 | Revenue chart | `RevenueChart.tsx` | DONE |
| S5-3 | Shop breakdown chart | `ShopChart.tsx` | DONE |
| S5-4 | Transition logic fixes | frontend/backend | DONE |
| S5-5 | Recent activity block | `DashboardPage.tsx` | DONE |
| S5-6 | Archive page | `ArchivePage.tsx` | DONE |
| S5-7 | Shops management page | `ShopsPage.tsx` | DONE |
| S5-8 | User management page | `UsersPage.tsx` | DONE |
| S5-9 | Settings page | `/settings` | DONE |

## Sprint 6 - Integrations and MCP
Goal: add external integrations and expose CRM operations through MCP.
Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S6-1 | Nova Poshta API client | `backend/services/nova_poshta.py` | DONE |
| S6-2 | Shopify sync service | `backend/services/shopify_sync.py` | DONE |
| S6-3 | Scheduler for sync jobs | `backend/scheduler.py` | DONE |
| S6-4 | Manual sync trigger | `backend/routers/shops.py` | DONE |
| S6-5 | MCP server infrastructure | `backend/routers/mcp.py` | DONE |
| S6-6 | Shipping routers | `backend/routers/shipping.py` | DONE |

## Sprint 7 - Restoration & Stability (Current)
Goal: recover from "White Screen" and fix UI functional bugs.
Status: `DONE`

| ID | Task | Scope | Status |
|---|---|---|---|
| S7-1 | Fix frontend build errors | `frontend/` imports | DONE |
| S7-2 | Fix shop platform casing bug | `ImportsPage`, `ShopsPage` | DONE |
| S7-3 | Relax status transition rules | `order_service.py` | DONE |
| S7-4 | Project Skill Migration | `skills/code-review` | DONE |
| S7-5 | Remote Repository Sync | Git push | DONE |

## Next Action
Primary next implementation step:
- Proceed with performance hardening (route-level chunk splitting), add smoke test coverage, and production deployment validation.

## Worklog
- `2026-04-20` Fixed critical "White Screen" by resolving broken API imports and Vite resolution issues.
- `2026-04-20` Resolved "Etsy Import Inactive" bug caused by case-sensitive platform filtering (`ETSY` vs `etsy`).
- `2026-04-20` Relaxed status transitions for Owner/Manager to allow flexible manual management.
- `2026-04-20` Migrated `code-review` skill to project root and pushed all changes to `main`.
- `2026-04-20` [By Codex] Project Transformation & Testing:
    - Implemented `CustomersPage`, `SettingsPage`, and `ShopOrdersPage`.
    - Added testing infrastructure using Vitest and React Testing Library.
    - Enhanced `DashboardPage` with real charts (`recharts`) and attention feeds.
    - Implemented full CRUD dialogs for `UsersPage` and `ShopsPage`.
    - Fixed Nova Poshta `DateTime` generation.
    - Enabled Lazy Loading for all major routes.

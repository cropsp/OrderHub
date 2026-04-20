28: - Sprint 8 status: `DONE` (Full Persistence)
29: - Sprint 9 status: `DONE` (Attachments & Designer Workflow)
30: - Sprint 10 status: `DONE` (Shop Management & Manual Entry)
31: - Sprint 11 status: `NOT STARTED`
32: 
33: ## Actual Repository Snapshot
34: 
35: Verified against the current tree:
36: 
37: **Backend:**
38: - Fully implemented routers for all modules (Orders, Shops, Dashboard, Imports, Users, Auth, Shipping, MCP).
39: - Services for Shopify Sync, Nova Poshta, Encryption, and Etsy parsing are active.
40: - Database models and migrations are stable.
41: 
42: **Frontend:**
43: - Completed all primary feature pages (Orders, Dashboard, Customers, Imports, Archive, Shops, Users, Settings).
44: - Full component set for Orders (Table, Board, Detail Panel, Status Tabs).
45: - Analytics components (Revenue, Shop charts, attention list, recent activity) are integrated.
46: - Build stability verified via Vite.
47: 
48: ## Sprint 4 - Core Frontend
49: Goal: implement actual order workflows in the UI.
50: Status: `DONE`
51: 
52: | ID | Task | Scope | Status |
53: |---|---|---|---|
54: | S4-1 | Status tabs for grouped order states | `StatusTabs.tsx` | DONE |
55: | S4-2 | Smart orders table | `OrdersTable.tsx` | DONE |
56: | S4-3 | Pipeline board | `PipelineBoard.tsx` | DONE |
57: | S4-4 | List and board view toggle | `ViewToggle.tsx` | DONE |
58: | S4-5 | Per-shop orders page | `/shops/:shopId/orders` | DONE |
59: | S4-6 | Order detail panel | `OrderDetailPanel.tsx` | DONE |
60: | S4-7 | CSV import page | `ImportsPage.tsx` | DONE |
61: | S4-8 | Customers integration | `frontend/src/api/customers.ts`, `CustomersPage.tsx` | DONE |
62: 
63: ## Sprint 5 - Dashboard, Archive, Management
64: Goal: finish analytics, archival view, and management screens.
65: Status: `DONE`
66: 
67: | ID | Task | Scope | Status |
68: |---|---|---|---|
69: | S5-1 | Dashboard stat cards | `StatCards.tsx` | DONE |
70: | S5-2 | Revenue chart | `RevenueChart.tsx` | DONE |
71: | S5-3 | Shop breakdown chart | `ShopChart.tsx` | DONE |
72: | S5-4 | Transition logic fixes | frontend/backend | DONE |
73: | S5-5 | Recent activity block | `DashboardPage.tsx` | DONE |
74: | S5-6 | Archive page | `ArchivePage.tsx` | DONE |
75: | S5-7 | Shops management page | `ShopsPage.tsx` | DONE |
76: | S5-8 | User management page | `UsersPage.tsx` | DONE |
77: | S5-9 | Settings page | `/settings` | DONE |
78: 
79: ## Sprint 6 - Integrations and MCP
80: Goal: add external integrations and expose CRM operations through MCP.
81: Status: `DONE`
82: 
83: | ID | Task | Scope | Status |
84: |---|---|---|---|
85: | S6-1 | Nova Poshta API client | `backend/services/nova_poshta.py` | DONE |
86: | S6-2 | Shopify sync service | `backend/services/shopify_sync.py` | DONE |
87: | S6-3 | Scheduler for sync jobs | `backend/scheduler.py` | DONE |
88: | S6-4 | Manual sync trigger | `backend/routers/shops.py` | DONE |
89: | S6-5 | MCP server infrastructure | `backend/routers/mcp.py` | DONE |
90: | S6-6 | Shipping routers | `backend/routers/shipping.py` | DONE |
91: 
92: ## Sprint 7 - Restoration & Stability (Current)
93: Goal: recover from "White Screen" and fix UI functional bugs.
94: Status: `DONE`
95: 
96: | ID | Task | Scope | Status |
97: |---|---|---|---|
98: | S7-1 | Fix frontend build errors | `frontend/` imports | DONE |
99: | S7-2 | Fix shop platform casing bug | `ImportsPage`, `ShopsPage` | DONE |
100: | S7-3 | Relax status transition rules | `order_service.py` | DONE |
101: | S7-4 | Project Skill Migration | `skills/code-review` | DONE |
102: | S7-5 | Remote Repository Sync | Git push | DONE |
103: 
104: ## Next Action
105: Primary next implementation step:
106: - Proceed with performance hardening (route-level chunk splitting), add smoke test coverage, and production deployment validation.
107: 
108: - `2026-04-20` Migrated `code-review` skill to project root and pushed all changes to `main`.
109: - `2026-04-20` [By Codex] Project Transformation & Testing.
110: - `2026-04-20` Starting Sprint 8: Full Persistence. Refactoring Order Detail view from Sheet to Dialog.
111: 
112: ## Sprint 8 - Full Persistence & Deep Editing
113: Goal: ensure every change in the UI is persisted to the database.
114: Status: `DONE`
115: 
116: | ID | Task | Scope | Status |
117: |---|---|---|---|
118: | S8-1 | Refactor Order Panel to Dialog | `OrderDetailPanel.tsx` | DONE |
119: | S8-2 | User Preferences persistence | `backend/models/user.py` | DONE |
120: | S8-3 | Settings API persistence | `backend/routers/users.py` | DONE |
121: | S8-4 | Order Metadata Editing | `OrderDetailPanel.tsx` | DONE |
122: | S8-5 | Interaction logic (Status/Refetch) | frontend | DONE |
123: 
124: ## Sprint 9 - Attachments & Designer Workflow
125: Goal: enable designers to upload completed files and automate status changes.
126: Status: `DONE`
127: 
128: | ID | Task | Scope | Status |
129: |---|---|---|---|
130: | S9-1 | Local File Storage System | `backend/uploads/` | DONE |
131: | S9-2 | Attachment Upload UI (Drag & Drop) | `AttachmentManager.tsx` | DONE |
132: | S9-3 | Manual File Handling Logic | frontend | DONE |
133: 
134: ## Sprint 10 - Shop Management & Manual Entry
135: Goal: full management UI and manual order entry with multi-currency support.
136: Status: `DONE`
137: 
138: | ID | Task | Scope | Status |
139: |---|---|---|---|
140: | S10-1 | Shop Edit/Create & NP Credentials | `ShopsPage.tsx` | DONE |
141: | S10-2 | Manual Order Dialog (Multi-item) | `NewOrderDialog.tsx` | DONE |
142: | S10-3 | Multi-currency (USD/UAH/EUR) | frontend/backend | DONE |
143: 
144: ## Sprint 11 - Production & Deployment
145: Goal: finalize operational readiness and launch.
146: Status: `NOT STARTED`
147: 
148: | ID | Task | Scope | Status |
149: |---|---|---|---|
150: | S11-1 | SSL & Domain Configuration | nginx | TODO |
151: | S11-2 | Database Backup Jobs | cron | TODO |
152: | S11-3 | Performance Monitoring | prometheus/grafana | TODO |
153: - `2026-04-20` [By Codex] Project Transformation & Testing:
154:     - Implemented `CustomersPage`, `SettingsPage`, and `ShopOrdersPage`.
155:     - Added testing infrastructure using Vitest and React Testing Library.
156:     - Enhanced `DashboardPage` with real charts (`recharts`) and attention feeds.
157:     - Implemented full CRUD dialogs for `UsersPage` and `ShopsPage`.
158:     - Fixed Nova Poshta `DateTime` generation.
159:     - Enabled Lazy Loading for all major routes.
160: - `2026-04-20` [Finalization Session]:
161:     - Completed Sprint 8 (Persistence): Fixed status updates and interaction propagation.
162:     - Completed Sprint 9 (Designer Workflow): Added file uploads and attachment management.
163:     - Completed Sprint 10 (Logistics): Built New Order dialog and advanced shop editing.

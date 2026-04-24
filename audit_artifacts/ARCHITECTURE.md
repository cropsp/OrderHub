# OrderHub CRM - Architecture Document

> Generated: 2026-04-24 | Read-only audit - no code changes

---

## 1. Directory Tree & Module Purposes

```
OrderHub/
├── backend/                        # Python 3.11 + FastAPI backend
│   ├── main.py                     # App entrypoint: FastAPI instance, CORS, lifespan, router registration
│   ├── config.py                   # Pydantic Settings — env vars, DB URL, secrets, feature flags
│   ├── database.py                 # Async SQLAlchemy engine, session factory, get_db dependency
│   ├── logger.py                   # Rotating file + console logging setup (5MB x 5 backups)
│   ├── scheduler.py                # APScheduler — periodic Shopify sync (every 15 min)
│   ├── seed.py                     # Database seeding script
│   ├── entrypoint.sh               # Docker entrypoint (Alembic migrate + uvicorn)
│   ├── Dockerfile                  # Backend container image
│   │
│   ├── models/                     # SQLAlchemy ORM models (DeclarativeBase)
│   │   ├── base.py                 #   Base class, TimestampMixin, UUIDPrimaryKeyMixin
│   │   ├── user.py                 #   User (owner/manager/designer roles), preferences JSON
│   │   ├── shop.py                 #   Shop — multi-platform (Etsy/Shopify/Manual), NP sender config
│   │   ├── customer.py             #   Customer — upserted by email, NP address refs
│   │   ├── order.py                #   Order, OrderItem, OrderStatusHistory, status transition matrix
│   │   ├── product.py              #   Product & ProductVariant — catalog with physical dimensions
│   │   ├── packaging.py            #   PackagingBox — BOX/ENVELOPE types for parcel calculation
│   │   └── attachment.py           #   Attachment — file uploads (mockup/reference/other)
│   │
│   ├── schemas/                    # Pydantic request/response schemas
│   │   ├── auth.py                 #   Login, token response
│   │   ├── user.py                 #   User CRUD schemas
│   │   ├── shop.py                 #   Shop create/update/response
│   │   ├── customer.py             #   Customer schemas
│   │   ├── order.py                #   Order CRUD, filters, status change, item schemas
│   │   ├── product.py              #   Product & variant schemas
│   │   ├── packaging.py            #   Packaging box schemas
│   │   ├── parcel.py               #   ParcelEstimate response
│   │   ├── dashboard.py            #   Dashboard aggregation schemas
│   │   ├── attachment.py           #   Attachment schemas
│   │   ├── import_preview.py       #   CSV import preview/result
│   │   └── common.py              #   PaginatedResponse[T], ImportResult
│   │
│   ├── routers/                    # FastAPI APIRouter modules (one per domain)
│   │   ├── dependencies.py         #   Auth: get_current_user, require_role, get_shop_for_user
│   │   ├── auth.py                 #   POST /api/auth/login, /refresh, /logout
│   │   ├── users.py                #   CRUD /api/users (owner-only)
│   │   ├── shops.py                #   CRUD /api/shops (owner-only), Shopify sync trigger
│   │   ├── customers.py            #   CRUD /api/customers
│   │   ├── orders.py               #   CRUD /api/orders, status transitions, item mgmt, CSV export
│   │   ├── imports.py              #   POST /api/imports/etsy-csv — Etsy CSV file upload
│   │   ├── attachments.py          #   File upload/download /api/attachments
│   │   ├── dashboard.py            #   GET /api/dashboard — aggregated stats
│   │   ├── products.py             #   CRUD /api/products, CSV import
│   │   ├── packaging.py            #   CRUD /api/packaging
│   │   ├── shipping.py             #   Nova Poshta: city/warehouse search, TTN create/delete
│   │   ├── webhooks.py             #   POST /api/webhooks/shopify/{shop_id} — real-time order sync
│   │   └── mcp.py                  #   MCP server over SSE — AI agent tool interface
│   │
│   ├── services/                   # Business logic layer
│   │   ├── auth_service.py         #   JWT create/decode, bcrypt hash/verify, password generation
│   │   ├── encryption_service.py   #   Fernet encrypt/decrypt for API tokens, token masking
│   │   ├── order_service.py        #   Order CRUD, status transitions with audit, item snapshots
│   │   ├── customer_service.py     #   Customer upsert by email
│   │   ├── catalog_service.py      #   Product catalog operations
│   │   ├── import_service.py       #   Import orchestration
│   │   ├── etsy_parser.py          #   Etsy CSV parsing — groups rows by Sale ID, upserts orders
│   │   ├── shopify_sync.py         #   Shopify GraphQL sync — pulls orders, deduplicates
│   │   ├── nova_poshta.py          #   Nova Poshta API client — cities, warehouses, TTN, counterparties
│   │   ├── parcel_calculator.py    #   Auto-selects packaging (envelope-first), computes weight/volume
│   │   └── file_storage.py         #   Local file storage for attachments
│   │
│   ├── alembic/                    # Database migrations
│   │   ├── env.py                  #   Alembic environment config (async)
│   │   └── versions/               #   5 migration files (initial → product catalog)
│   │
│   ├── tests/                      # Backend tests
│   │   └── test_parcel_calculator.py
│   │
│   └── logs/                       # Rotating log files (server.log + 5 backups)
│
├── frontend/                       # React 19 + TypeScript + Vite
│   ├── index.html                  # SPA entry point
│   ├── vite.config.ts              # Vite config — React plugin, Tailwind, /api proxy to :8000
│   ├── tsconfig.json               # TypeScript project references config
│   ├── eslint.config.js            # ESLint flat config
│   ├── vitest.config.ts            # Vitest test config
│   ├── Dockerfile                  # Production nginx container
│   ├── Dockerfile.dev              # Development container
│   ├── nginx.conf                  # Production reverse proxy config
│   │
│   └── src/
│       ├── main.tsx                # React entry — BrowserRouter, QueryClientProvider
│       ├── App.tsx                 # Route definitions, lazy loading, role-based guards
│       ├── index.css               # Global styles
│       │
│       ├── api/                    # Axios-based API client layer
│       │   ├── client.ts           #   Axios instance, JWT interceptor, silent 401 refresh queue
│       │   ├── auth.ts             #   Login, refresh, logout calls
│       │   ├── orders.ts           #   Order CRUD, status, items, export
│       │   ├── shops.ts            #   Shop CRUD, sync trigger
│       │   ├── customers.ts        #   Customer CRUD
│       │   ├── products.ts         #   Product catalog API
│       │   ├── packaging.ts        #   Packaging CRUD
│       │   ├── shipping.ts         #   NP city/warehouse search, TTN create/delete
│       │   ├── imports.ts          #   Etsy CSV upload
│       │   ├── attachments.ts      #   File upload/download
│       │   └── users.ts            #   User management API
│       │
│       ├── store/                  # Client-side state
│       │   └── authStore.ts        #   Zustand store — user, isAuthenticated, isLoading
│       │
│       ├── hooks/                  # React Query hooks (server state)
│       │   ├── useAuth.ts          #   Login, logout, refresh mutations
│       │   ├── useOrders.ts        #   Order list, detail, mutations
│       │   ├── useShops.ts         #   Shop queries/mutations
│       │   ├── useCustomers.ts     #   Customer queries
│       │   ├── useProducts.ts      #   Product catalog queries
│       │   ├── usePackaging.ts     #   Packaging queries
│       │   ├── useShipping.ts      #   NP search hooks
│       │   ├── useDashboard.ts     #   Dashboard stats query
│       │   ├── useImports.ts       #   CSV import mutation
│       │   ├── useAttachments.ts   #   File upload/download hooks
│       │   ├── useUsers.ts         #   User management hooks
│       │   └── useDebounce.ts      #   Generic debounce utility
│       │
│       ├── pages/                  # Route-level page components
│       │   ├── LoginPage.tsx       #   Authentication form
│       │   ├── DashboardPage.tsx   #   Analytics overview (lazy)
│       │   ├── OrdersPage.tsx      #   Order list with table/pipeline views (lazy)
│       │   ├── OrderDetailPage.tsx #   Single order detail (lazy)
│       │   ├── CreateOrderPage.tsx #   Manual order creation form (lazy, full-page)
│       │   ├── CustomersPage.tsx   #   Customer list
│       │   ├── ShopsPage.tsx       #   Shop management (owner-only, lazy)
│       │   ├── ShopOrdersPage.tsx  #   Filtered orders for a specific shop
│       │   ├── ImportsPage.tsx     #   Etsy CSV import (manager+)
│       │   ├── ProductsPage.tsx    #   Product catalog management (manager+, lazy)
│       │   ├── PackagingPage.tsx   #   Packaging inventory (manager+, lazy)
│       │   ├── UsersPage.tsx       #   User management (owner-only, lazy)
│       │   ├── ArchivePage.tsx     #   Completed/cancelled orders (manager+)
│       │   ├── SettingsPage.tsx    #   User preferences (lazy)
│       │   ├── ShellPage.tsx       #   App shell/layout wrapper
│       │   └── FeaturePlaceholderPage.tsx  # Placeholder for unbuilt features
│       │
│       ├── components/
│       │   ├── auth/
│       │   │   └── RouteGuards.tsx #   RequireAuth, RequireRole outlet wrappers
│       │   ├── layout/
│       │   │   ├── AppLayout.tsx   #   Main app shell (sidebar + content area)
│       │   │   ├── Sidebar.tsx     #   Navigation sidebar
│       │   │   └── Topbar.tsx      #   Top navigation bar
│       │   ├── dashboard/
│       │   │   ├── MetricCard.tsx  #   Individual metric display
│       │   │   ├── StatCards.tsx   #   Dashboard stat card grid
│       │   │   ├── RevenueChart.tsx#   Revenue trend chart (Recharts)
│       │   │   └── ShopChart.tsx   #   Per-shop breakdown chart
│       │   ├── orders/
│       │   │   ├── OrdersLayout.tsx       # Orders page layout wrapper
│       │   │   ├── OrdersTable.tsx        # Table view of orders
│       │   │   ├── PipelineBoard.tsx      # Kanban/pipeline view
│       │   │   ├── PipelineCard.tsx       # Individual pipeline card
│       │   │   ├── StatusTabs.tsx         # Status filter tabs
│       │   │   ├── ViewToggle.tsx         # Table/pipeline view switch
│       │   │   ├── OrderDetailPanel.tsx   # Side panel for order detail
│       │   │   ├── OrderDetailView.tsx    # Full order detail view
│       │   │   ├── CreateOrderView.tsx    # Order creation form component
│       │   │   ├── OrderItemsEditor.tsx   # Inline item editing
│       │   │   ├── AttachmentManager.tsx  # File upload/preview
│       │   │   ├── ProductVariantSelector.tsx  # SKU/variant picker
│       │   │   ├── useOrderForm.ts        # Form state hook
│       │   │   └── detail/                # Order detail sub-components
│       │   │       ├── BentoCard.tsx       #   Card wrapper
│       │   │       ├── DetailHeader.tsx    #   Order header + actions
│       │   │       ├── DetailCustomer.tsx  #   Customer info section
│       │   │       ├── DetailItems.tsx     #   Line items section
│       │   │       ├── DetailFinance.tsx   #   Financial breakdown
│       │   │       ├── DetailLogistics.tsx #   Shipping/TTN section
│       │   │       ├── DetailNotes.tsx     #   Notes section
│       │   │       └── DetailTimeline.tsx  #   Status history timeline
│       │   ├── inventory/
│       │   │   ├── ProductForm.tsx         # Product create/edit form
│       │   │   ├── PackagingForm.tsx       # Packaging box form
│       │   │   ├── CSVImportModal.tsx      # Product CSV import dialog
│       │   │   └── ShopSelector.tsx        # Shop filter for inventory
│       │   └── ui/                         # Reusable UI primitives (shadcn/ui based)
│       │       ├── badge.tsx, button.tsx, card.tsx, dialog.tsx,
│       │       │   dropdown-menu.tsx, input.tsx, scroll-area.tsx,
│       │       │   select.tsx, separator.tsx, sheet.tsx, skeleton.tsx,
│       │       │   table.tsx, tabs.tsx, textarea.tsx
│       │       ├── StatusBadge.tsx         # Order status colored badge
│       │       ├── EmptyState.tsx          # Empty state placeholder
│       │       └── Toast.tsx              # Toast notification system
│       │
│       ├── types/                  # TypeScript type definitions
│       │   ├── order.ts, shop.ts, customer.ts, user.ts,
│       │   │   shipping.ts, dashboard.ts, attachment.ts,
│       │   │   inventory.ts, common.ts
│       │
│       ├── lib/                    # Shared utilities
│       │   ├── constants.ts        #   App-wide constants (status labels, colors)
│       │   ├── order-status.ts     #   Status display helpers
│       │   └── utils.ts            #   cn() utility (clsx + tailwind-merge)
│       │
│       └── utils/                  # Additional utilities
│           ├── avatar.ts           #   Avatar generation
│           └── shopTheme.ts        #   Per-shop color theming
│
├── docs/                           # Project documentation
│   ├── integrations/nova-poshta.md
│   ├── inventory/product-catalog.md
│   ├── audit/REPORT_2026_04_21.md
│   └── UI_IMPROVEMENT_PLAN.md
│
├── agents/skills/                  # AI agent skills (MCP/Codex)
│   ├── code-review/               #   PR review skill with language-specific checklists
│   ├── crm-start/                  #   Startup orchestrator skill
│   ├── np-audit/                   #   Nova Poshta integration audit skill
│   └── orderdb/                    #   Database query skill
│
├── audit_artifacts/                # Static analysis reports
├── scratch/                        # Development scratch files
├── tools/mcp-browser/              # MCP browser testing tools
├── orderhub_data/uploads/          # Persistent file upload storage
│
├── docker-compose.yml              # Production: postgres + backend + frontend (nginx)
├── docker-compose.dev.yml          # Development overrides
├── .env / .env.example             # Environment configuration
├── CLAUDE.md                       # AI assistant project instructions
├── implementation_plan.md          # Sprint history and roadmap
└── task.md                         # Current task tracking
```

---

## 2. Data Flow Diagrams

### 2.1 Standard API Request Flow

```
Browser (React SPA)
  │
  ├─ Axios client (src/api/client.ts)
  │   ├─ Attaches Bearer JWT to Authorization header
  │   └─ On 401 → silent refresh via /api/auth/refresh (cookie-based)
  │
  ▼
Vite dev proxy (:3000 → :8000)  /  nginx reverse proxy (prod)
  │
  ▼
FastAPI (main.py :8000)
  ├─ CORS middleware (allow FRONTEND_URL origin)
  ├─ Exception handlers (404, 500 → {"detail": "..."})
  │
  ▼
Router (routers/*.py)
  ├─ Depends(get_current_user)  →  decode JWT → fetch User from DB
  ├─ Depends(require_role(...)) →  RBAC check (owner/manager/designer)
  ├─ Depends(get_db)            →  async session from pool
  │
  ▼
Service Layer (services/*.py)
  ├─ Business logic, validation, audit logging
  ├─ External API calls (Nova Poshta, Shopify GraphQL)
  │
  ▼
SQLAlchemy ORM (models/*.py)
  ├─ Async session with selectinload for relationships
  ├─ flush() within service → commit() at router level (via get_db)
  │
  ▼
PostgreSQL 16 (via asyncpg)
  ├─ Pool: 10 connections + 20 overflow, pre-ping enabled
  └─ Alembic migrations for schema changes
```

### 2.2 Order Creation Flow (Manual)

```
CreateOrderPage.tsx
  │  form submit
  ▼
POST /api/orders  (OrderCreate schema)
  │
  ▼
orders router → create_new_order()
  │  RBAC: designer blocked
  ▼
order_service.create_order()
  ├─ customer_service.upsert_customer(email)  →  find-or-create Customer
  ├─ Create Order (status=NEW)
  ├─ For each item:
  │   ├─ Create OrderItem
  │   └─ If product_variant_id → _apply_variant_snapshot() (copy dims)
  ├─ Create OrderStatusHistory (from="none", to="new")
  └─ flush() → get_order_detail() with eager loads
  │
  ▼
Router commits → returns OrderResponse
```

### 2.3 Etsy CSV Import Flow

```
ImportsPage.tsx → file upload
  │
  ▼
POST /api/imports/etsy-csv  (multipart file + shop_id)
  │
  ▼
imports router
  │
  ▼
etsy_parser.parse_etsy_csv()
  ├─ Decode CSV, group rows by Sale ID
  ├─ Failure threshold: abort if >20% rows have format errors
  ├─ For each Sale ID:
  │   ├─ Skip if Order with (external_id, shop_id) exists
  │   ├─ upsert_customer(email)
  │   ├─ Create Order + OrderItems + OrderStatusHistory
  │   └─ Catch per-order errors
  └─ flush() → ImportResult {imported, skipped, errors}
```

### 2.4 Shopify Sync Flow (Two Paths)

```
Path A: Scheduled (every 15 min)              Path B: Webhook (real-time)
─────────────────────────────                  ─────────────────────────────
APScheduler → run_shopify_sync()               POST /api/webhooks/shopify/{shop_id}
  │                                              │
  ├─ Find all active Shopify shops               ├─ HMAC verification (SHA256)
  ├─ For each shop:                               ├─ Parse JSON payload
  │   ├─ Decrypt access_token                     ├─ Deduplicate by external_id
  │   ├─ GraphQL query (last 50 orders)           └─ create_order() or skip
  │   ├─ Deduplicate by external_id
  │   └─ create_order() for new ones
  └─ Update shop.last_synced_at
```

### 2.5 Nova Poshta TTN Creation Flow

```
OrderDetailView → "Create TTN" button
  │
  ▼
POST /api/shipping/np-ttn/{order_id}
  │  RBAC: owner or manager only
  ▼
shipping router
  ├─ Validate: order exists, no existing TTN, has NP config
  ├─ Validate: shipping address + city_ref + warehouse_ref present
  │
  ├─ Resolve Sender:
  │   ├─ Use cached shop.np_sender_ref/np_sender_contact_ref
  │   └─ Or fetch from NP API → cache in shop record
  │
  ├─ Resolve Recipient:
  │   ├─ Search by phone → use existing counterparty
  │   └─ Or create new counterparty via NP API
  │
  ├─ Build InternetDocument payload (Kyiv timezone)
  ├─ np_client.create_internet_document()
  │
  ├─ Save TTN number to order.ttn_number
  ├─ Auto-transition: IN_PRODUCTION → SHIPPED (with audit)
  └─ Commit
```

### 2.6 Authentication Flow

```
LoginPage.tsx
  │  POST /api/auth/login {email, password}
  ▼
auth router
  ├─ auth_service.authenticate_user() → bcrypt verify
  ├─ create_access_token() (JWT, 15 min, HS256)
  ├─ create_refresh_token() (JWT, 30 days, separate key)
  ├─ Set refresh_token as httpOnly cookie
  └─ Return {access_token, user}

Client stores access_token in memory (authStore)
  │
  ▼
On 401 response:
  ├─ Queue failed requests
  ├─ POST /api/auth/refresh (cookie-based)
  ├─ Get new access_token → replay queued requests
  └─ On refresh failure → redirect to /login
```

---

## 3. Key Dependencies & Versions

### 3.1 Backend (Python)

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| **Core** | fastapi | 0.115.6 | Web framework |
| | uvicorn[standard] | 0.34.0 | ASGI server |
| | pydantic[email] | 2.10.4 | Schema validation |
| | pydantic-settings | 2.7.1 | Environment config |
| | python-multipart | 0.0.20 | File uploads |
| **Database** | sqlalchemy[asyncio] | 2.0.36 | Async ORM |
| | asyncpg | 0.30.0 | PostgreSQL driver |
| | alembic | 1.14.1 | Schema migrations |
| | greenlet | 3.1.1 | Async support for SQLAlchemy |
| **Auth** | passlib[bcrypt] | 1.7.4 | Password hashing |
| | bcrypt | 4.0.1 | bcrypt backend |
| | python-jose[cryptography] | 3.3.0 | JWT encoding/decoding |
| | cryptography | 44.0.0 | Fernet encryption |
| **HTTP** | httpx | 0.28.1 | Async HTTP client (Shopify, NP) |
| | aiosmtplib | 3.0.2 | Async email (unused currently) |
| | email-validator | 2.2.0 | Email validation |
| | apscheduler | 3.10.4 | Background task scheduling |
| **Other** | python-dotenv | 1.0.1 | .env file loading |
| | aiofiles | 23.2.1 | Async file I/O |
| | mcp | 1.2.1 | Model Context Protocol server |
| | sse-starlette | 2.2.1 | Server-Sent Events |

*Note: `tenacity` is used in nova_poshta.py and shopify_sync.py but NOT listed in requirements.txt.*

### 3.2 Frontend (Node.js / React)

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| **Core** | react | ^19.2.4 | UI framework |
| | react-dom | ^19.2.4 | React DOM renderer |
| | react-router-dom | ^7.14.1 | Client-side routing |
| **State** | zustand | ^5.0.12 | Auth state management |
| | @tanstack/react-query | ^5.99.2 | Server state / caching |
| **HTTP** | axios | ^1.15.0 | HTTP client |
| **UI** | tailwindcss | ^4.2.2 | Utility-first CSS |
| | radix-ui | ^1.4.3 | Accessible UI primitives |
| | shadcn | ^4.3.0 | Component library |
| | lucide-react | ^1.8.0 | Icon library |
| | recharts | ^3.8.1 | Charting library |
| | class-variance-authority | ^0.7.1 | Component variant styling |
| | clsx | ^2.1.1 | Conditional classNames |
| | tailwind-merge | ^3.5.0 | Tailwind class deduplication |
| **Utilities** | date-fns | ^4.1.0 | Date formatting |
| | date-fns-tz | ^3.2.0 | Timezone support |
| | lodash-es | ^4.18.1 | Utility functions |
| | react-dropzone | ^15.0.0 | File drag-and-drop |
| **Build** | vite | ^8.0.4 | Build tool / dev server |
| | typescript | ~6.0.2 | Type checking |
| | vitest | ^2.1.9 | Test framework |
| | jsdom | ^26.1.0 | DOM emulation for tests |
| | eslint | ^9.39.4 | Linting |

### 3.3 Infrastructure

| Component | Version | Purpose |
|-----------|---------|---------|
| PostgreSQL | 16-alpine | Primary database |
| Docker Compose | 3.9 spec | Container orchestration |
| nginx | (in frontend Dockerfile) | Production reverse proxy |

---

## 4. Potential Architectural Issues

### 4.1 Missing Dependency: `tenacity`

`backend/services/nova_poshta.py` and `backend/services/shopify_sync.py` both import `tenacity` for retry logic (`@retry` decorator), but `tenacity` is **not listed in `requirements.txt`**. This works only if tenacity is installed as a transitive dependency. It should be explicitly pinned.

### 4.2 Deprecated JWT Library: `python-jose`

`python-jose` is [no longer actively maintained](https://github.com/mpdavis/python-jose/issues/310). The community has largely moved to `PyJWT` or `joserfc`. This is a supply chain risk for a production deployment.

### 4.3 Session Commit in `get_db` Dependency — Double Commit Risk

`database.py:get_db()` auto-commits at session teardown. However, several router endpoints also call `await db.commit()` explicitly before the response (e.g., `orders.py:create_new_order`, `shipping.py:create_np_ttn`). This leads to **double commits** — the explicit one in the router and the implicit one in the `get_db` finally block. While not a data corruption risk today (the second commit is a no-op if nothing changed), it creates confusion about which layer owns the transaction boundary. Worse, `order_service.delete_order_item()` calls `db.commit()` inside the service layer itself, breaking the convention that the router commits.

### 4.4 No Multi-Tenant Isolation

`routers/dependencies.py:get_shop_for_user()` has a TODO noting that **any authenticated user can access any shop**. There is no ownership relationship between users and shops. In a multi-tenant scenario, a designer from Shop A could potentially see Shop B's data. The current setup is safe only for a single-business deployment.

### 4.5 System User Hack in Scheduler and Webhooks

`scheduler.py` creates a fake `User` object in memory (not persisted to DB) with a hardcoded UUID `00000000-...` to satisfy the `create_order` signature. `webhooks.py` does `select(User).limit(1)` to grab any user as the "system user." If the database has no users, webhooks silently produce `None` as the acting user, which could cause null reference errors in audit history.

### 4.6 Eager Loading on All Relationships (N+1 Inverse Problem)

The `Shop.orders` relationship uses `lazy="selectin"`, meaning **every time a Shop is loaded, all its orders are loaded too**. As the order count grows, loading a single shop will pull its entire order history into memory. Similarly, `Customer.orders` uses `lazy="selectin"`. This is an inverse N+1 problem — fetching too much data.

### 4.7 Shopify Sync Only Fetches Last 50 Orders

`shopify_sync.py` queries `first: 50` orders from Shopify GraphQL without pagination. If more than 50 orders are created between sync intervals (15 min), the older ones will never be synced. There is no cursor-based pagination implemented.

### 4.8 CSV Export Has No Pagination Guard

`orders.py:export_orders_csv()` fetches up to 10,000 orders into memory and generates the CSV in a `StringIO` buffer. For large datasets, this could exhaust server memory. There is no streaming CSV generation.

### 4.9 MCP Server: Single Global SSE Transport

`routers/mcp.py` uses a single global `sse_transport` variable. If two AI agents connect simultaneously, the second connection overwrites the first's transport reference, breaking the first agent's session. The MCP endpoint also bypasses the service layer and queries the database directly.

### 4.10 No Rate Limiting

There is no rate limiting middleware on any endpoint. The Nova Poshta API calls (city search, warehouse search) are user-triggered with debounce on the frontend, but nothing prevents a malicious client from hammering these endpoints and exhausting NP API quotas.

### 4.11 Inconsistent Error Handling in `create_np_ttn`

The shipping router's `create_np_ttn` endpoint references `body.parcel_override`, `body.length`, `body.width`, and `body.height` — but the `CreateTTNRequest` schema only defines `weight`, `description`, `volume`, `cash_on_delivery`, and `cod_amount`. These missing fields would cause `AttributeError` at runtime if the code paths executing them are reached.

### 4.12 SQLite Database File in Backend Directory

`backend/orderhub.db` exists in the repository — a leftover SQLite file that is not used (the app runs on PostgreSQL). This could cause confusion and should be in `.gitignore`.

### 4.13 Log File Size Mismatch with Documentation

`CLAUDE.md` states logs rotate at "25MB cap", but `logger.py` configures `maxBytes=5 * 1024 * 1024` (5MB per file, 5 backups = 25MB total). The per-file cap is 5MB, not 25MB. This is a documentation ambiguity rather than a bug.

### 4.14 Webhook Update Path Is a No-Op

`webhooks.py` handles the `orders/updated` Shopify topic but only logs "skipping update for now" if the order already exists. Updated order data from Shopify (price changes, address corrections, cancellations) is silently dropped.

### 4.15 Frontend Test Coverage Is Minimal

Only two test files exist: `CustomersPage.test.tsx` and `DashboardPage.test.tsx`. There are no tests for critical flows like order creation, authentication, or the token refresh interceptor. Backend has only `test_parcel_calculator.py`.

### 4.16 Hardcoded Shopify API Version

`shopify_sync.py` uses `SHOPIFY_API_VERSION = "2024-04"`. This is a 2-year-old API version that may be deprecated by Shopify. There is no mechanism to update this without a code change.

### 4.17 `volume_cm3` Calculation Inconsistency

`OrderItem.volume_cm3` divides by 1000.0 (mm^3 → cm^3 would be 1,000,000), while `ProductVariant.volume_cm3` also divides by 1000.0 with a comment saying it should divide by 1,000,000. Both use the same incorrect divisor, so they are consistent with each other, but the actual values are 1000x too large compared to true cm^3.

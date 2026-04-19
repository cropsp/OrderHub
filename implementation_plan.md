# OrderHub CRM — Implementation Plan

## Огляд проєкту

**OrderHub** — self-hosted CRM для управління замовленнями handmade бізнесу шкіряних виробів. Замінює workflow Etsy CSV → Google Sheets → Trello єдиним веб-додатком з підтримкою AI-агентів через MCP протокол.

### Ключові рішення (зафіксовані)

| Рішення | Деталі |
|---------|--------|
| AI Agent | MCP Server замість вбудованого чату (Phase 6) |
| Сторінки магазинів | Окрема сторінка для кожного магазину + "All Orders" |
| Візуалізація замовлень | Hybrid: Smart Table (primary) + Pipeline Board (secondary), toggle кнопка |
| Адреса доставки | Поля shipping address на моделі Order |
| Docker | Окремі dev/prod конфігурації для frontend |
| Alembic | Інтегровано в entrypoint.sh |
| Валюти | Revenue per currency, без автоконвертації |
| Order fields | `quantity` та `item_price` видалені з Order (є в OrderItem) |
| Drag-and-drop | Видалено. Статус змінюється через inline dropdown. @dnd-kit прибрано |

---

## Зміни відносно оригінальної специфікації

> [!IMPORTANT]
> **Видалено** (спрощення через MCP-підхід):
> - `AgentSession`, `AgentAction` моделі
> - `agent_runner.py`, `llm_provider.py`
> - `/api/agent/*` ендпоінти
> - `AgentChat.tsx`, `AgentMessage.tsx`, `ToolCallPreview.tsx`, `ConfirmAction.tsx`
> - `ANTHROPIC_API_KEY` з `.env`

> [!IMPORTANT]
> **Додано**:
> - `mcp_server.py` — MCP сервер з усіма CRM-інструментами
> - Shipping address поля на Order
> - `ShopOrdersPage.tsx` — окрема сторінка для кожного магазину
> - `CustomersPage.tsx` — сторінка клієнтів
> - `entrypoint.sh` — startup script з alembic + seed
> - `Dockerfile.dev` для frontend (vite dev server)
> - `platform_fee` поле на Order

---

## Оновлена структура проєкту

```
OrderHub/
├── docker-compose.yml              # production
├── docker-compose.dev.yml          # development overrides
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh               # alembic upgrade + optional seed
│   ├── requirements.txt
│   ├── main.py                     # FastAPI app, CORS, lifespan
│   ├── config.py                   # Settings from env
│   ├── database.py                 # async SQLAlchemy engine + session
│   ├── seed.py                     # seed data script
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                 # Base model with id, created_at
│   │   ├── user.py
│   │   ├── shop.py
│   │   ├── order.py                # Order + OrderItem + OrderStatusHistory
│   │   ├── customer.py
│   │   └── attachment.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── shop.py
│   │   ├── order.py
│   │   ├── customer.py
│   │   ├── dashboard.py
│   │   └── common.py              # pagination, error schemas
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── shops.py
│   │   ├── orders.py
│   │   ├── imports.py
│   │   ├── customers.py
│   │   ├── attachments.py
│   │   └── dashboard.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── encryption_service.py   # Fernet encrypt/decrypt
│   │   ├── order_service.py        # status transitions, CRUD
│   │   ├── customer_service.py     # upsert logic
│   │   ├── shopify_sync.py
│   │   ├── etsy_parser.py
│   │   ├── scheduler.py            # APScheduler (single worker)
│   │   ├── file_storage.py
│   │   ├── email_service.py
│   │   └── nova_poshta.py          # NP API client
│   │
│   ├── mcp_server.py               # [NEW] MCP server
│   │
│   └── alembic/
│       ├── alembic.ini
│       ├── env.py
│       └── versions/
│
└── frontend/
    ├── Dockerfile                   # production (multi-stage + nginx)
    ├── Dockerfile.dev               # development (vite dev server)
    ├── nginx.conf
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── index.html
    │
    └── src/
        ├── main.tsx
        ├── App.tsx                  # routes
        │
        ├── api/
        │   ├── client.ts            # axios + interceptors
        │   ├── auth.ts
        │   ├── orders.ts
        │   ├── shops.ts
        │   ├── customers.ts
        │   ├── imports.ts
        │   ├── attachments.ts
        │   └── dashboard.ts
        │
        ├── components/
        │   ├── layout/
        │   │   ├── Sidebar.tsx
        │   │   ├── Topbar.tsx
        │   │   └── AppLayout.tsx
        │   ├── orders/
        │   │   ├── OrdersTable.tsx        # Primary view: smart table with inline status
        │   │   ├── PipelineBoard.tsx      # Secondary view: visual pipeline columns
        │   │   ├── PipelineCard.tsx        # Card for pipeline view
        │   │   ├── StatusTabs.tsx          # Tab bar grouping statuses
        │   │   ├── ViewToggle.tsx          # [List] [Board] toggle button
        │   │   └── OrderDetailPanel.tsx    # Slide-over panel
        │   ├── import/
        │   │   ├── CsvDropzone.tsx
        │   │   └── ImportResult.tsx
        │   ├── dashboard/
        │   │   ├── StatCard.tsx
        │   │   ├── RevenueChart.tsx
        │   │   ├── ShopBreakdownChart.tsx
        │   │   └── AttentionList.tsx
        │   └── ui/                  # shadcn/ui components
        │
        ├── pages/
        │   ├── LoginPage.tsx
        │   ├── DashboardPage.tsx
        │   ├── OrdersPage.tsx       # All Orders — Kanban
        │   ├── ShopOrdersPage.tsx   # [NEW] Per-shop Kanban
        │   ├── OrderDetailPage.tsx
        │   ├── ImportPage.tsx
        │   ├── ShopsPage.tsx        # Shop management (owner)
        │   ├── CustomersPage.tsx    # [NEW] Customer list
        │   ├── ArchivePage.tsx
        │   ├── UsersPage.tsx
        │   └── SettingsPage.tsx     # Profile, password change
        │
        ├── hooks/
        │   ├── useAuth.ts
        │   ├── useOrders.ts
        │   └── useShops.ts
        │
        ├── store/
        │   └── authStore.ts
        │
        ├── types/
        │   ├── order.ts
        │   ├── shop.ts
        │   ├── user.ts
        │   └── common.ts
        │
        └── lib/
            ├── constants.ts         # status colors, transitions
            └── utils.ts             # date formatting, etc.
```

---

## Оновлена модель Order (з виправленнями)

```python
Order:
  - id (UUID, PK)
  - external_id (string)
  - shop_id (FK → Shop, indexed)
  - customer_id (FK → Customer, indexed)
  - UNIQUE constraint: (external_id, shop_id)
  - status: enum('new','waiting_info','info_received','design_pending',
                  'design_ready','in_production','shipped','completed','cancelled')
  - title (text)                    # перший item або "Multiple items (N)"
  - total_price: Numeric(10,2)     # Order Total з платформи
  - currency: varchar(3)
  - production_cost: Numeric(10,2), nullable
  - shipping_np_cost: Numeric(10,2), nullable
  - platform_fee: Numeric(10,2), nullable        # [NEW] комісія Etsy/Shopify
  
  # [NEW] Shipping address fields
  - shipping_name (text, nullable)
  - shipping_phone (varchar 20, nullable)
  - shipping_street_1 (text, nullable)
  - shipping_street_2 (text, nullable)
  - shipping_city (text, nullable)
  - shipping_state (text, nullable)
  - shipping_zip (varchar 20, nullable)
  - shipping_country (varchar 2, nullable)
  
  # Assignment & production
  - assigned_designer_id (FK → User, nullable)
  - assigned_at (timestamp, nullable)
  - ttn_number (varchar 20, nullable)
  - ttn_created_at (timestamp, nullable)
  - ttn_printed (bool, default False)
  
  # Notes
  - customer_note (text, nullable)
  - custom_info (text, nullable)
  - internal_note (text, nullable)
  
  # Timestamps
  - ordered_at (timestamp)
  - shipped_at (timestamp, nullable)
  - completed_at (timestamp, nullable)
  - created_at, updated_at

  # ВИДАЛЕНО: quantity, item_price (є в OrderItem)
```

---

## Спрінти

### Sprint 1 — Foundation 🏗️ [DONE]
> Мета: проёкт запускається в Docker, є БД, авторизація, seed дані

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 1.1 | `.env.example` + `docker-compose.yml` + `docker-compose.dev.yml` | root | Проста | [DONE] |
| 1.2 | Backend Dockerfile + `entrypoint.sh` + `requirements.txt` | backend/ | Проста | [DONE] |
| 1.3 | `config.py` — Pydantic Settings з .env | backend/ | Проста | [DONE] |
| 1.4 | `database.py` — async engine, session, Base | backend/ | Проста | [DONE] |
| 1.5 | Всі DB моделі (User, Shop, Order, OrderItem, OrderStatusHistory, Customer, Attachment) | backend/models/ | Проста | [DONE] |
| 1.6 | Alembic init + initial migration | backend/alembic/ | Складна | [DONE] |
| 1.7 | `main.py` — FastAPI app skeleton (CORS, lifespan, exception handlers) | backend/ | Проста | [DONE] |
| 1.8 | Auth: JWT service + login/refresh/logout endpoints | backend/routers/auth.py, services/auth_service.py | Проста | [DONE] |
| 1.9 | User CRUD (owner only) | backend/routers/users.py | Проста | [DONE] |
| 1.10 | `encryption_service.py` — Fernet helpers | backend/services/ | Проста | [DONE] |
| 1.11 | `seed.py` — 3 users, 3 shops, 15 orders | backend/ | Проста | [DONE] |
| 1.12 | Frontend: Vite + React + TS + TailwindCSS + shadcn/ui init | frontend/ | Складна | [DONE] |
| 1.13 | Frontend Dockerfile.dev + nginx.conf + prod Dockerfile | frontend/ | Проста | [DONE] |

**Результат**: `docker compose -f docker-compose.dev.yml up` → backend на :8000, frontend на :3000, PostgreSQL на :5432, seed data в БД, login працює.

---

### Sprint 2 — Core Backend API 📦 [DONE]
> Мета: всі бізнес-ендпоінти працюють, CSV імпорт, статуси

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 2.1 | Pydantic schemas для всіх моделей | backend/schemas/ | Проста | [DONE] |
| 2.2 | Shop CRUD + encrypt/decrypt API tokens | backend/routers/shops.py | Проста | [DONE] |
| 2.3 | Customer service (upsert by email) | backend/services/customer_service.py | Проста | [DONE] |
| 2.4 | Order CRUD + фільтри (status, shop_id, search, pagination) | backend/routers/orders.py | Складна | [DONE] |
| 2.5 | `order_service.py` — status transition validation + history logging | backend/services/ | Складна | [DONE] |
| 2.6 | Etsy CSV parser (BOM strip, grouping by Order ID, multi-item) | backend/services/etsy_parser.py | Складна | [DONE] |
| 2.7 | Import endpoint (POST /api/imports/etsy) | backend/routers/imports.py | Проста | [DONE] |
| 2.8 | File storage service + attachment endpoints (auth-protected) | backend/services/file_storage.py | Проста | [DONE] |
| 2.9 | Customer endpoints | backend/routers/customers.py | Проста | [DONE] |
| 2.10 | Dashboard stat endpoints (revenue per currency) | backend/routers/dashboard.py | Складна | [DONE] |
| 2.11 | CSV export endpoint (owner only) | backend/routers/orders.py | Проста | [DONE] |

**Результат**: повний REST API, тестований через Swagger UI на :8000/docs.

---

### Sprint 3 — Frontend Shell 🖼️
> Мета: авторизація, layout, навігація, базові сторінки

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 3.1 | Axios client + token refresh interceptor | frontend/src/api/client.ts | Проста | [DONE] |
| 3.2 | Auth store + useAuth hook | frontend/src/store/, hooks/ | Проста | [DONE] |
| 3.3 | Login page (premium UI) | frontend/src/pages/LoginPage.tsx | Складна | [TODO] |
| 3.4 | App layout: Sidebar (role-aware, shops list) + Topbar | frontend/src/components/layout/ | Складна | [TODO] |
| 3.5 | React Router config (protected routes) | frontend/src/App.tsx | Складна | [TODO] |
| 3.6 | API hooks (React Query) для orders, shops | frontend/src/api/ | Складна | [TODO] |
| 3.7 | Базові shadcn/ui компоненти (Button, Card, Badge, Input, Dialog, etc.) | frontend/src/components/ui/ | Проста | [TODO] |

**Результат**: login → redirect to dashboard, sidebar з навігацією per shop, protected routes по ролях.

---

### Sprint 4 — Core Frontend 🎯
> Мета: Orders views, деталі замовлення, імпорт CSV

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 4.1 | Status Tabs — групування 9 статусів у 5 табів | StatusTabs.tsx | Проста | [TODO] |
| 4.2 | Orders Table (primary view) — smart table | OrdersTable.tsx | Складна | [TODO] |
| 4.3 | Pipeline Board (secondary view) — канбан | PipelineBoard.tsx | Складна | [TODO] |
| 4.4 | View Toggle — [📋 List] [◻️ Board] | ViewToggle.tsx | Проста | [TODO] |
| 4.5 | Shop Orders Page — per-shop view | ShopOrdersPage.tsx | Проста | [TODO] |
| 4.6 | Order Detail Panel (slide-over) | OrderDetailPanel.tsx | Складна | [TODO] |
| 4.7 | CSV Import page | ImportPage.tsx | Складна | [TODO] |
| 4.8 | Customers page | CustomersPage.tsx | Проста | [TODO] |

**Результат**: повний workflow: import CSV → table/board view → inline status change → view details → upload mockup.

---

### Sprint 5 — Dashboard, Archive & Management 📊
> Мета: аналітика, архів, адмін-панелі

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 5.1 | Dashboard: stat cards | DashboardPage.tsx | Проста | [TODO] |
| 5.2 | Dashboard: revenue chart | RevenueChart.tsx | Складна | [TODO] |
| 5.3 | Dashboard: shop breakdown | ShopBreakdownChart.tsx | Проста | [TODO] |
| 5.4 | Dashboard: attention needed list | AttentionList.tsx | Проста | [TODO] |
| 5.5 | Dashboard: recent activity | DashboardPage.tsx | Проста | [TODO] |
| 5.6 | Archive page | ArchivePage.tsx | Проста | [TODO] |
| 5.7 | Shops management | ShopsPage.tsx | Проста | [TODO] |
| 5.8 | User management | UsersPage.tsx | Проста | [TODO] |
| 5.9 | Settings page | SettingsPage.tsx | Проста | [TODO] |

**Результат**: повна CRM без AI — ready to use.

---

### Sprint 6 — Integrations & MCP 🔌
> Мета: зовнішні інтеграції + MCP server для AI-агента

| # | Задача | Файли | Складність | Статус |
|---|--------|-------|------------|--------|
| 6.1 | Nova Poshta API client | backend/services/nova_poshta.py | Складна | [TODO] |
| 6.2 | Shopify sync service + scheduler | backend/services/shopify_sync.py | Складна | [TODO] |
| 6.3 | Manual sync trigger | backend/routers/shops.py | Проста | [TODO] |
| 6.4 | Email service (aiosmtplib) | backend/services/email_service.py | Проста | [TODO] |
| 6.5 | NP "Test connection" endpoint | backend/routers/shops.py | Проста | [TODO] |
| 6.6 | MCP Server — read tools | backend/mcp_server.py | Складна | [TODO] |
| 6.7 | MCP Server — NP tools | backend/mcp_server.py | Складна | [TODO] |
| 6.8 | MCP Server — write tools | backend/mcp_server.py | Складна | [TODO] |
| 6.9 | MCP auth & role checking | backend/mcp_server.py | Складна | [TODO] |
| 6.10 | README.md — документація | root | Проста | [TODO] |

**Результат**: Hermes (або будь-який MCP-клієнт) підключається до CRM і виконує операції. Shopify auto-sync працює. NP TTN створюються.

---

## Верифікація

### Після кожного спрінту
- Backend: Swagger UI manual testing
- Frontend: візуальна перевірка в браузері
- Docker: `docker compose up` працює без помилок

### Фінальна верифікація
- [ ] Login/logout всіх трьох ролей
- [ ] Import Etsy CSV → замовлення з'являються на Kanban
- [ ] Drag-and-drop зміна статусу з перевіркою дозволів
- [ ] Order detail: всі секції, upload файлу, status history
- [ ] Per-shop Kanban фільтрація
- [ ] Dashboard: графіки, stats, attention list
- [ ] Archive: таблиця, CSV export
- [ ] MCP: підключення агента, виконання read/write tools
- [ ] Role restrictions: designer бачить тільки свої замовлення

---

## Поточний стан (Last Sync)

> **Активний Спрінт**: Sprint 3 — Frontend Shell

**Щойно завершено (Sprint 2 & Початок Sprint 3):**
*   **Core Backend API (Sprint 2) виконано на 100%**. Працюють всі ендпоінти: orders, shops, customers, Etsy CSV imports, dashboard stats, file storage.
*   Виправлені зауваження після Code Review: N+1 query (`customers.py`), безпека шляхів (`file_storage.py`), парсинг дат та підрахунок `total_price` (`etsy_parser.py`).
*   **Відкрито Sprint 3 (Задачі 3.1 & 3.2)**: Налаштовано Axios клієнт (`client.ts`) для silent JWT token refresh. Реалізовано глобальний стейт через `zustand` (`authStore.ts`) та хук `useAuth`. Typescript збирається без помилок.

**Наступні кроки для старту:**
*   **Task 3.3**: Побудова `LoginPage.tsx` (Premium дизайн, Tailwind v4 + shadcn/ui).
*   **Task 3.4**: Створення App Layout (`Sidebar.tsx`, `Topbar.tsx`, `AppLayout.tsx`).

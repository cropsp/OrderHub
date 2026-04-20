# OrderHub CRM - Core Project Context

## Purpose

This file stores the stable project context for OrderHub:

- product scope
- architecture decisions
- domain rules and invariants
- security model
- shared terminology

This file should change rarely. Day-to-day execution status belongs in `implementation_plan.md`.

## Product Summary

OrderHub is a self-hosted CRM for managing orders in a handmade leather goods business.

Primary workflow being replaced:

`Etsy CSV -> Google Sheets -> Trello -> manual follow-up`

Target outcome:

`single web app -> tracked orders -> controlled status workflow -> attachments -> analytics -> external AI access through MCP`

## Current Delivery Snapshot

Last reviewed: `2026-04-20`

- Backend foundation and core REST API are present in the repository.
- Frontend infrastructure is present, but the product UI is still in early shell state.
- Authentication plumbing exists on both backend and frontend.
- AI integration is intended through an MCP server, but the MCP implementation is not yet in the repository.

## Technical Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 async, PostgreSQL 16
- Frontend: React 19, TypeScript, Vite, TailwindCSS v4, React Router, React Query, Zustand
- Infrastructure: Docker, Docker Compose, Alembic
- AI integration strategy: MCP server, not embedded chat UI

## Architecture Decisions

### 1. AI integration

OrderHub does not embed a first-party chat UI or direct LLM provider runner inside the CRM.

Instead:

- the backend exposes CRM capabilities as MCP tools
- external AI agents connect to the CRM through MCP
- CRM business logic stays independent from model vendor logic

### 2. Order visualization

The intended UI is hybrid:

- primary view: smart table with inline status changes
- secondary view: pipeline board for visual overview

Drag-and-drop is intentionally out of scope. Status changes should happen through explicit controls, not card dragging.

### 3. Financials

- currencies are stored as original values
- no automatic FX conversion in MVP
- revenue is tracked per currency
- platform fees are stored explicitly on the order

### 4. Customer and address modeling

- customer identity is lightweight and primarily keyed by contact data
- shipping address belongs to the order, not only to the customer
- customer grouping is historical and based on upsert-by-email behavior

## Domain Invariants

### Users

- roles: `owner`, `manager`, `designer`
- `owner` has full access
- `manager` has restricted access to sensitive financial and integration data
- `designer` should only see assigned operational work
- the system must not allow deactivating the last active owner

### Shops

- supported platforms: `etsy`, `shopify`
- third-party secrets must be encrypted at rest
- decrypted tokens should exist only in backend memory

### Orders

- primary key: UUID
- uniqueness: `(external_id, shop_id)`
- `quantity` and `unit_price` belong to `OrderItem`, not `Order`
- `platform_fee` is a first-class financial field on `Order`
- shipping recipient data is stored directly on `Order`
- status changes must be validated server-side
- every status transition must be written to immutable history

### Order statuses

Canonical statuses:

- `new`
- `waiting_info`
- `info_received`
- `design_pending`
- `design_ready`
- `in_production`
- `shipped`
- `completed`
- `cancelled`

Logical UI grouping:

- `New`
- `Awaiting`
- `Design`
- `Production`
- `Shipping`

The grouped labels are a UI concern. The canonical status values above are the source of truth.

## Security Model

### Authentication

- access token: JWT in `Authorization` header
- refresh token: `httpOnly` cookie
- refresh token rotation is required
- frontend silently refreshes and replays queued requests on `401`

### Passwords

- passwords are hashed with `bcrypt`
- temporary passwords may be returned once at user creation time

### Sensitive data

- shop tokens and carrier credentials must be encrypted at rest
- role checks must be enforced in backend handlers and services

## Backend Boundaries

Current backend scope already present in the repository:

- auth
- users
- shops
- orders
- imports
- customers
- attachments
- dashboard

Planned but not yet present in the repository:

- `mcp_server.py`
- `shopify_sync.py`
- `scheduler.py`
- `email_service.py`
- `nova_poshta.py`

## Frontend Boundaries

Current frontend scope already present in the repository:

- app bootstrap
- router shell
- auth API client
- auth store and hook
- base UI primitives

Planned but not yet present in the repository:

- dedicated page modules
- app layout modules
- orders table and pipeline views
- import workflow UI
- dashboard UI
- archive and management pages

## Terminology

Use these terms consistently:

- `smart table` for the primary orders view
- `pipeline board` for the secondary visual board
- `inline status change` for status updates from UI controls
- `per-shop orders page` instead of `per-shop kanban`
- `order detail panel` for the slide-over order details UI

Avoid mixing `kanban`, `board`, and `pipeline` as if they are separate planned features unless the distinction matters.

## Documentation Rules

### `ORDERHUB_CONTEXT.md`

Keep only stable truth here:

- architecture
- product rules
- security model
- domain invariants
- terminology

### `implementation_plan.md`

Keep operational data there:

- sprint breakdown
- task status
- next actions
- known gaps between plan and codebase
- verification notes

### If a third document is later added

Recommended optional additions:

- `DECISIONS.md` or `docs/adr/` for important architecture decisions
- `worklog.md` for dated progress notes
- `risks.md` for technical debt and known implementation risks

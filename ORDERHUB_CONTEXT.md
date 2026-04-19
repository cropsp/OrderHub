# OrderHub CRM — Core Project Context

This document provides a comprehensive overview of the OrderHub project architecture, technical stack, core business logic, and fundamental design decisions. It serves as the primary context source for any developer or AI agent working on the codebase.

---

## 1. Project Overview & Tech Stack

**OrderHub** is a self-hosted Order Management CRM tailored for a handmade leather goods e-commerce business. It replaces a fragmented workflow (Etsy CSV → Google Sheets → Trello) with a unified, automated web application.

*   **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16.
*   **Frontend**: React 19, TypeScript, Vite, TailwindCSS v4, React Router, React Query.
*   **Infrastructure**: Dockerized environment with dedicated `docker-compose.yml` (production via Nginx) and `docker-compose.dev.yml` (with volumes and HMR). Database migrations are handled automatically via Alembic on container startup (`entrypoint.sh`).

---

## 2. Key Architectural Decisions

1.  **AI Integration via MCP (Model Context Protocol)**
    *   *Decision*: We fundamentally rejected the idea of embedding an AI Chat UI and LLM runner directly inside the CRM.
    *   *Implementation*: The API exposes an **MCP Server**. All CRM operations (changing statuses, creating shipping labels, reading orders) are exposed as standard MCP Tools. Any external AI Agent (like a local Hermes model via llama.cpp or Claude Desktop) connects to this server. This strictly separates the CRM business logic from the AI provider layer.

2.  **Hybrid Order Visualization UI**
    *   *Decision*: A traditional 9-column Kanban board was deemed too bulky for daily operations.
    *   *Implementation*: The UI relies on a **Hybrid View**.
        *   **Primary View**: A Smart Data Table with inline status dropdowns.
        *   **Secondary View**: A Pipeline Board (visual columns, no drag-and-drop).
        *   The 9 distinct order statuses are grouped into **5 logical tabs/filters**: `New`, `Awaiting`, `Design`, `Production`, and `Shipping`.

3.  **Financials & Revenue Tracking**
    *   *Decision*: No automatic currency conversion MVP.
    *   *Implementation*: Original currencies (`USD`, `EUR`, `GBP`) are preserved throughout the database. Revenue dashboards render separate charts/totals per currency. Order logic includes a custom `platform_fee` to accurately track Etsy/Shopify deductions.

4.  **Customer & Address Data Model**
    *   *Decision*: Address data changes frequently and belongs to the purchase, not just the user.
    *   *Implementation*: Shipping addresses and recipient phone numbers are denormalized and stored directly on the `Order` model. The `Customer` model is kept lightweight (primarily used for contact linking and historical grouping via email upserts).

---

## 3. Database Schema & Business Logic

All entities use `UUID` primary keys and include `created_at`/`updated_at` timestamps.

*   **User**: Roles dictate access (`owner` has full access, `manager` cannot see financials/API keys, `designer` only sees assigned items). Safety guards prevent deactivating the last active `owner`.
*   **Shop**: Integrates with `etsy` and `shopify`. 
    *   *Security*: All third-party secrets (Shopify Tokens, Nova Poshta API Keys) are encrypted at rest in PostgreSQL using the **Fernet** algorithm. They are decrypted only in backend memory.
*   **Order & OrderItem**: 
    *   `quantity` and `unit_price` exist solely on `OrderItem` (as Etsy orders may contain multiple distinct items). 
    *   Orders are strictly unique by the composite constraint: `UNIQUE(external_id, shop_id)`.
*   **Status Workflow**: 
    *   The backend enforces a strict transition matrix: `new` → `waiting_info` / `info_received` / `design_pending` / `in_production` → `shipped` → `completed`. Orders can be transitioned to `cancelled` at any stage.
*   **OrderStatusHistory**: An immutable audit log table tracks every status change, recording the user who made the change and the timestamp.

---

## 4. Authentication & Security Model

The system uses a robust, cookie-based JWT strategy:

*   **Passwords**: Hashed via `bcrypt`. Owners can create users and an auto-generated temporary password is returned exactly once in the API response.
*   **Access Token**: 15-minute expiration, sent in the `Authorization: Bearer <token>` header.
*   **Refresh Token**: 30-day expiration. Stored and transmitted **strictly via `httpOnly` secure cookies** with `SameSite=Strict`. This eliminates the risk of XSS token theft.
*   **Token Rotation**: Every time a refresh token is used, a new one is issued and the old one is invalidated via cookie replacement. 
*   **Axios Interceptor**: The frontend uses a custom Axios client that catches `401 Unauthorized` responses, queues any parallel requests, silently refreshes the token using the cookie, and then replays the queued requests seamlessly.

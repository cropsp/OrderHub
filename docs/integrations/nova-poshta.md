# Nova Poshta Integration Module

Detailed technical documentation for the Nova Poshta shipping integration in OrderHub CRM.

## 1. Overview
The Nova Poshta module allows managers to manage logistics directly from the OrderHub interface. It supports city/warehouse search, recipient management, and automatic waybill (TTN) generation with support for Cash-on-Delivery (COD).

## 2. Architecture

### Backend (`backend/`)
- **API Client** (`services/nova_poshta.py`): A robust, asynchronous client for the NP JSON API v2.0. Features include:
    - **Automatic Retries**: Uses `tenacity` for transient HTTP errors.
    - **Explicit Error Handling**: `NovaPoshtaAPIError` for business-level failures (invalid API key, missing fields) which prevents unnecessary retries.
- **Shipping Router** (`routers/shipping.py`): FastAPI routes for search and TTN lifecycle management.
- **Security** (`services/encryption_service.py`): All NP API keys are encrypted using **Fernet symmetric encryption** before being stored in the database.

### Frontend (`frontend/`)
- **UI Components**:
    - `DetailLogistics.tsx`: The main shipping editor with integrated search and TTN display.
- **Hooks**:
    - `useShipping.ts`: React Query hooks for fetching cities/warehouses and creating TTNs.
    - `useDebounce.ts`: Custom hook to optimize API calls during search.

## 3. Key Features

### Sender Caching
To reduce NP API latency, the system caches `SenderRef` and `ContactSenderRef` in the `Shop` model.
- **First Call**: Fetches references from NP API and saves them to the DB.
- **Subsequent Calls**: Uses cached references, saving 2 API calls per TTN.

### Data Integrity
- **Reference Management**: When a user manually edits a city name, the system automatically clears the stored `CityRef` and `WarehouseRef` to prevent data mismatches.
- **Timezones**: All TTN dates are explicitly set to `Europe/Kiev` to ensure NP server compliance regardless of server location.

### UX Optimizations
- **Search Debounce**: City search is debounced (350ms) to prevent API rate limiting.
- **Smart Dropdowns**: Dropdowns automatically close on outside clicks and use `relative` positioning for layout stability.
- **Click-to-Copy**: TTN numbers can be copied with a single click with toast feedback.

## 4. Security
API keys are never stored in plain text.
- **Key Storage**: `Shop.np_api_key_encrypted`.
- **Environment**: The master encryption key is managed via `ENCRYPTION_KEY` in `.env`.
- **Masking**: Keys are masked in responses (`****abcd`) to prevent exposure in the UI.

## 5. Deployment & Configuration
- **Prerequisites**: Ensure `ENCRYPTION_KEY` is set in the production `.env`.
- **Migrations**: Database updates are managed via Alembic (e.g., `990470ad5d99`).

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
- **Environment**: The master encryption key is managed via `ENCRYPTION_KEY` in `.env` (supports `FERNET_KEY` as a legacy alias via `AliasChoices`).
- **Masking**: Keys are masked in responses (`****abcd`) to prevent exposure in the UI.

## 5. Deployment & Configuration
- **Prerequisites**: 
    - Ensure `ENCRYPTION_KEY` is set in the production `.env`.
    - **Backward Compatibility**: The system still supports `FERNET_KEY` as a legacy alias via Pydantic's `AliasChoices`. If `ENCRYPTION_KEY` is missing, it will automatically fall back to `FERNET_KEY`.
- **Migrations**: Database updates are managed via Alembic (e.g., `990470ad5d99`).

## 6. Automated Logistics & Parcel Calculation

### Packaging Registry
The system maintains a registry of available packaging types specifically for Nova Poshta:
- **BOX**: Rigid packaging for most items.
- **ENVELOPE**: Soft packaging with a `max_thickness_mm` constraint.
- **Tare Weight**: Each packaging type includes its own weight, which is added to the total parcel weight.

### Parcel Calculator Service
A dedicated service (\`services/logistics_service.py\`) automates parcel dimension estimation:
1. **Aggregation**: Sums the dimensions and weights of all linked variants in an order.
2. **Packing Factor**: Applies a safety multiplier (default 1.25x) to account for protective materials.
3. **Packaging Selection**: Automatically selects the smallest compatible Box or Envelope from the registry.
4. **Volumetric Logic**: Calculates total volume and volumetric weight (\$LxWxH / 4000\$) to determine the chargeable weight.

### UI Integration (Logistics Panel)
The Order Detail view includes an enhanced **Logistics Panel**:
- **Automatic Pre-fill**: Dimensions are automatically populated based on the calculation service.
- **Manual Overrides**: Users can override calculated values; the system stores both \`parcel_override\` and the original \`calculated_parcel\` data.
- **Smart Badges**: Displays \`Calculated\` badge when using automated data and \`Manual\` when overridden.

## 7. Configuration Summary (Logistics)
- **Shop Scoping**: Logistics settings (\`parcel_settings\`) are managed per shop.
- **Kiev Timezone**: All delivery dates are forced to \`Europe/Kiev\` for API compatibility.
- **Volumetric weight**: \$cm^3\$ to \$kg\$ conversion follows NP's standard formula.

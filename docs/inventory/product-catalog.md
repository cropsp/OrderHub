# Product Catalog & Inventory Foundation

This module serves as the structural foundation for product management within OrderHub. While initially implemented to support logistics automation, it is designed to be the base for future warehouse and stock management features.

## 1. Overview
The Product Catalog allows users to maintain a source of truth for their products' physical specifications, independent of external platforms (Etsy, Shopify). It supports multi-variant products and bulk management.

## 2. Core Models (Database)

### Products & Variants
- **Product**: Represents a top-level item (e.g., "Handmade Wallet").
- **ProductVariant**: Represents specific versions (e.g., "Brown / Small"). Stores:
    - **SKU**: The unique identifier used for matching with external orders.
    - **Dimensions**: Length, Width, Height (in mm).
    - **Weight**: Actual weight in grams.
    - **Volume**: Automatically calculated $cm^3$ for logistics estimations.

### Order Integration
- **Atomic Snapshots**: When an order is imported, the system captures a "snapshot" of the product's dimensions. This ensures historical data integrity if product specs change in the future.
- **SKU Matching**: Internal logic that automatically links `OrderItem` to `ProductVariant` based on the SKU provided by the external platform.

## 3. Key Features

### Two-Step CSV Import
To ensure data integrity, bulk management uses a safe two-step workflow:
1. **Preview**: User uploads a CSV. The system parses it, validates all rows, and returns a 5-row preview along with an `import_token`.
2. **Confirmation**: The user reviews the preview and errors. Upon clicking "Confirm", the system uses the token to commit the changes to the database.

### Role-Based Access
Catalog management is restricted to administrative roles:
- **OWNER**: Full access to create, edit, and bulk import.
- **MANAGER**: Full access to catalog management.
- **DESIGNER**: Read-only access or restricted view (depending on shop scope).

## 4. API & Integration
- **Internal API**: Scoped by `shop_id` and filtered for `MANUAL` platforms to avoid conflicts with automated external syncs.
- **Extensibility**: The schema is prepared for future additions like `stock_quantity`, `warehouse_location`, and `supplier_id`.

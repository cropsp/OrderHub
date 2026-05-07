# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current sprint:** PC-B.1 — Shopify-style inline editing (no modal)
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## Sprint PC-A ✅ DONE — Foundation: Pricing, Cost & Stock

---

## Sprint PC-B ✅ DONE — Product Detail Page

---

## Sprint PC-B.1 — Shopify-style Inline Editing

**Goal:** Replace modal-based editing with Shopify/Airtable-style inline editing.
`/products/:id` becomes an always-editable page — all fields are inputs from the moment
you open it. No modal, no edit/view toggle.

**What changes:**

1. `ProductDetailPage.tsx` — full rewrite as an edit form:
   - Title and description become editable inputs (styled to look natural, not form-like)
   - Variant table rows become rows of compact inputs (all fields editable inline)
   - Volume and Margin % remain computed/read-only
   - "Save Changes" + "Cancel" buttons appear in the header only when something has changed
   - "Add Variant" button to add a new empty row to the table
   - Archive/Restore button stays as-is
   - Remove: Edit button, ProductForm modal, isEditOpen state

2. `ProductsPage.tsx` — pencil icon navigates to `/products/:id` instead of opening a modal.
   ProductForm modal stays only for "Add Product" (create flow).

3. `backend/services/catalog_service.py` — small fix: when a variant patch has no `id`,
   create it as a new variant instead of skipping it (currently `if not v_id: continue`).
   This is needed so "Add Variant" on the detail page actually persists to DB.

**Out of scope for this sprint:** deleting individual variants from DB (local removal only, with TODO comment).

---

## Sprint PC-B.2 — Column Visibility Picker (NOT STARTED)

Goal: user can toggle which columns are visible in the ProductsPage table via a column picker
(checkboxes). Preference saved to `localStorage` per browser session.

# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current sprint:** PC-B.2 — Column visibility picker
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## Sprint PC-A ✅ DONE — Foundation: Pricing, Cost & Stock

---

## Sprint PC-B ✅ DONE — Product Detail Page

---

## Sprint PC-B.1 ✅ DONE — Shopify-style Inline Editing

`/products/:id` is now an always-editable inline form. Title/description are
inputs, variant rows are rows of inputs, Volume/Margin % stay computed.
Save Changes / Cancel only appear when the draft diverges from the loaded
product. Add Variant appends a new row that persists on save (backend
`update_product` now creates variants whose patch has no `id`); trash icon
does local-only removal (DB-level deletion deferred). Pencil icon on the
list page navigates to the detail page; modal kept only for "Add Product".

---

## Sprint PC-B.2 ✅ DONE — Column Visibility Picker

ProductsPage gained a **Columns** dropdown (right of the search bar) with a
checkbox per toggleable column: Variants, SKUs, Weight Range, Price Range,
Stock, Status. Title and Actions are always visible. Selection persists in
`localStorage` under `orderhub:productsTable:columnVisibility`, hydrated with
merge-over-defaults so future column additions appear by default. Empty-state
`colSpan` derives from the live visible-column count.

Commit: `46783bf` feat(catalog): Sprint PC-B.2 — column visibility picker on ProductsPage

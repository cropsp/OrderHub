# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current sprint:** PC-B — Product Detail Page
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## Sprint PC-A — Foundation: Pricing, Cost & Stock ✅ DONE

All steps completed. Key fix applied post-sprint: `update_product` service now applies variant patches
(price, cost_price, stock_quantity) by variant id. `ProductUpdate` schema extended with
`variants: Optional[List[ProductVariantPatch]]`. `create_product` also fixed to persist new fields.

---

## Sprint PC-B — Product Detail Page

**Goal:** Replace modal-only flow with a full-page product view at `/products/:id`.

### Step 1 — Frontend: Route + Page scaffold
- [ ] Add route `/products/:id` in `frontend/src/App.tsx` (or router config)
- [ ] Create `frontend/src/pages/ProductDetailPage.tsx` — basic shell with back navigation

### Step 2 — Frontend: Page header
- [ ] Title (product.title), shop badge, status badge (Active / Archived)
- [ ] Archive / Restore button (calls PATCH `is_active`)
- [ ] Edit button → opens `ProductForm` modal pre-filled with product data

### Step 3 — Frontend: Variants table
- [ ] Table with columns: SKU, Name, Weight, Dimensions, Volume, Price, Cost, Stock, Margin %
- [ ] Margin % = `((price - cost) / price * 100)` — show only when both > 0
- [ ] Color-coded stock (green ≥5, amber 1–4, red 0)

### Step 4 — Frontend: Navigation wire-up
- [ ] Row click in `ProductsPage.tsx` navigates to `/products/:id` (replaces modal open trigger)
- [ ] Keep Edit button in row actions as fallback (or remove — decide in impl)

### Step 5 — Backend: Archive/Restore endpoint
- [ ] Verify `PATCH /products/{id}` with `{ is_active: false/true }` works (already exists via `update_product`)
- [ ] If not exposed properly, add dedicated endpoint

### Verification
- [ ] Click product row in list → navigates to `/products/:id`
- [ ] Header shows title, shop badge, status
- [ ] Archive button toggles status; page reflects change
- [ ] Variants table shows all fields including price, cost, stock, margin

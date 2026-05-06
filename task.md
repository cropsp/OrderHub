# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current sprint:** PC-C — (next sprint, TBD)
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## Sprint PC-A — Foundation: Pricing, Cost & Stock ✅ DONE

All steps completed. Key fix applied post-sprint: `update_product` service now applies variant patches
(price, cost_price, stock_quantity) by variant id. `ProductUpdate` schema extended with
`variants: Optional[List[ProductVariantPatch]]`. `create_product` also fixed to persist new fields.

---

## Sprint PC-B — Product Detail Page ✅ DONE

Full-page product view at `/products/:id` shipped. Notes:
- Route guard is `RequireAuth` (not `RequireRole`), matching backend `GET /products/{id}` which uses `get_current_user` — designers with shop access can view.
- `useUpdateProduct` is called with explicit `shopId: product.shop_id` for both Archive/Restore and Edit save handlers.
- New `useProduct(id)` hook (key `['product', id]`); `useUpdateProduct` now invalidates both `['products', shopId]` and `['product', id]`.
- Missing type aliases (`ProductRead`, `ProductCreate`, `ProductUpdate`, `ProductVariantCreate`, `ProductVariantPatch`) added to `frontend/src/types/inventory.ts` — they were already imported but never defined.
- Backend: no changes — `PATCH /products/{id}` with `{ is_active }` and variant patches already worked from PC-A.
- Row click in `ProductsPage` navigates to detail; row Edit/Delete buttons stop propagation.

# OrderHub CRM — Technical Debt Audit

> Generated: 2026-04-24 | Read-only audit — no code changes
> Sources: ruff (65 errors), eslint (120 errors), tsc (1), mypy (33), git history (6mo), manual code inspection

---

## Executive Summary

The codebase ships working features for 10 sprints but carries accumulating debt. Linter noise is **dominated by two classes of problem**: unused imports across the backend (~45 of 65 ruff errors) and pervasive `any` types on the frontend (~90 of 120 eslint errors). Beneath the noise there are real structural issues: a handful of functions in the 100–170 line range, near-identical duplication between `OrderDetailPanel` / `OrderDetailView` and between `useProducts` / `usePackaging`, two `User`/`UserRole` type definitions that disagree, and 33 mypy errors that include at least one latent runtime bug (`CreateTTNRequest` missing attributes referenced by the router).

The hot files (OrderDetailPanel, DetailLogistics, OrdersLayout, App, DashboardPage) are exactly the files with the most `any` usage and the most `set-state-in-effect` violations — churn is concentrated where type safety and React-effect discipline are weakest.

---

## HIGH Priority

### H1. 120 frontend `@typescript-eslint/no-explicit-any` violations — type safety is effectively opt-in

- **Pattern**: Every React Query mutation uses `(error: any) => { addToast(error.response?.data?.detail || ..., 'error') }`. Every update hook has `payload: any`. All Nova Poshta API responses (`city: any`, `warehouse: any`, `w: any`) are untyped.
- **Hotspots** (by count of `any` errors):
  - `frontend/src/components/orders/detail/DetailLogistics.tsx` — 6 `any` + setState-in-effect bug (547-line component, #2 hot file)
  - `frontend/src/components/inventory/CSVImportModal.tsx` — 9 `any` + 4 unused imports
  - `frontend/src/components/inventory/ProductForm.tsx` / `PackagingForm.tsx` — 5 `any` each
  - `frontend/src/pages/ShopsPage.tsx` — 6 `any` (616-line component, owner-only UI)
  - `frontend/src/hooks/use{Products,Packaging,Shipping,Users,Shops,Orders}.ts` — `any` on every `onError` handler and most payloads
  - `frontend/src/types/common.ts:165` — `errors: any[]` on `ImportResult` (the shared type itself is loose)
- **Why it matters**: The project's own CLAUDE.md says "No `any` type in TypeScript unless migrating legacy code." The codebase is violating its own rule 120 times. Axios already exports `AxiosError` and the backend already returns `{"detail": "..."}` — a single `ApiError` type and a `MutationError` helper would kill ~60 of these errors at once. Right now, a typo in a mutation payload field name is caught nowhere.

### H2. 6 `react-hooks/set-state-in-effect` violations — cascading re-renders on initial mount

- **Files**: `PackagingForm.tsx:49`, `ProductForm.tsx:49`, `ProductVariantSelector.tsx:77`, `DetailLogistics.tsx:48`, `DetailNotes.tsx:14,50`, `SettingsPage.tsx:50`.
- **Pattern**: `useEffect(() => { setX(initialData.x) }, [initialData])` to sync props→state. React 19's new rule flags this because it triggers a second render on every prop change.
- **Why it matters**: All six are in forms that are mounted inside a modal/panel after data loads — so every time the user opens a form, React renders twice before it paints. Combined with the two `react-hooks/use-memo` errors on `DetailNotes` (debounce wrapped in `useCallback` with inline-function expectation violated), the order detail flow is doing real extra work per keystroke. Frontend performance work is already on the sprint-11 roadmap; these are cheaper wins than chunk splitting.

### H3. Duplicated `OrderDetailPanel` ↔ `OrderDetailView` — same logic, two containers

- **Files**: `frontend/src/components/orders/OrderDetailPanel.tsx` (174 lines, **#1 hot file — 12 changes in 6mo**) and `frontend/src/components/orders/OrderDetailView.tsx` (247 lines, #10 hot file — 7 changes).
- **What's duplicated**: The same 7 imports of `Detail*` sub-components, identical `handleUpdate`, identical `handleGenerateTTN`, identical `handleDeleteTTN`, identical `onStatusChange` inline handler, identical role/permission derivation, identical `createTTN`/`deleteTTN` wiring. The only real difference is the outer chrome (Dialog wrapper vs. full-page div with back-nav).
- **Why it matters**: Both files were edited 7–12 times in 6 months, and they drift — `OrderDetailPanel` has debug `console.log` lines in `onStatusChange` that `OrderDetailView` lacks. Any status-transition bug has to be fixed twice. An `useOrderDetailController(orderId)` hook returning `{ order, handleUpdate, handleGenerateTTN, ... }` would eliminate ~80 lines of duplication and end the drift.

### H4. `create_np_ttn` is 169 lines — a monolithic router handler doing everything

- **File**: `backend/routers/shipping.py:88-256`.
- **What it does**: NP key decryption, validation (order exists, no existing TTN, has config, has address + refs), sender resolution with caching, recipient counterparty search-or-create, InternetDocument payload construction, API call, order status transition, audit logging, commit.
- **Why it matters**: This is the single most fragile endpoint in the system — it touches encryption, two external API round-trips, and the audit pipeline. The architecture doc already flagged that it references `body.parcel_override`, `body.length`, `body.width`, `body.height` — **attributes that don't exist on `CreateTTNRequest`** (mypy confirms: `routers/shipping.py:107,108,197,199`). That is a latent `AttributeError` at runtime for any code path that hits those lines. The 169-line function hides the bug; extracting sender-resolution, recipient-resolution, and payload-building into the `nova_poshta` service would make the schema mismatch obvious.

### H5. Duplicate `User`/`UserRole` type definitions with different shapes

- **Files**: `frontend/src/types/common.ts` (lines 7, 26–34) defines `UserRole` as a string union `'owner' | 'manager' | 'designer'` and `User` *without* a `preferences` field. `frontend/src/types/user.ts` (lines 1–18) defines `UserRole` as a `const` object with a separate `UserRoleType` alias and `User` *with* `preferences: Record<string, any>`.
- **Why it matters**: Consumers pick one or the other semi-arbitrarily — `authStore` and most components import from `user.ts`, but `order.ts`, `shop.ts`, etc. inherit `User` indirectly through `common.ts`. `SettingsPage.tsx` depends on `preferences`; if a component imports the wrong `User`, TypeScript lets it through because the names collide only at import time. This is exactly the kind of ambient type-soup that produces hard-to-debug runtime surprises after a refactor. One canonical definition, re-exported, closes the issue.

### H6. mypy reports 33 type errors including latent runtime bugs

- **File**: `audit_artifacts/mypy_report.txt`.
- **Most serious** (beyond H4):
  - `models/order.py:228` — arithmetic on `None` (`int * None`) in an unguarded expression.
  - `services/customer_service.py:68` and `routers/customers.py:98` — access `Customer.order_count` which doesn't exist on the model.
  - `routers/shipping.py:212` — accesses `order.order_number` which doesn't exist (mypy suggests `external_id`).
  - `routers/webhooks.py:112` — passes `User | None` where `User` is required (the "system user" fallback in webhook handler returns `None` on empty DB — already called out in ARCHITECTURE.md §4.5).
  - `services/shopify_sync.py:165` — passes `customer_note` to `OrderCreate`, which has no such field.
- **Why it matters**: These aren't stylistic — they're "this line will raise at runtime if it executes." Some are behind rarely-taken branches (empty DB, specific CSV shapes) which is why they haven't surfaced. Each should be triaged: fix the bug or fix the types.

---

## MEDIUM Priority

### M1. 45 unused-import errors in backend (ruff F401)

- **Pattern**: Every router file has 1–3 dead imports. Particularly bad: `routers/webhooks.py` (3 dead imports — `ShopPlatform`, `call_shopify_graphql`, `update_order`), `routers/shipping.py` (4 dead imports including `List`, `status`, `Order`), `services/parcel_calculator.py` (4 dead `typing` imports + `math` + `OrderItem`).
- **Why it matters**: Low-severity on its own, but they signal cargo-culted copy-paste from boilerplate. The `update_order` import in `webhooks.py` is a tell — the webhook update path is a no-op (ARCHITECTURE.md §4.14) and the import is what's left of the abandoned implementation. Dead imports are a reliable proxy for dead code paths. `ruff --fix` removes 40 of them mechanically.

### M2. 3 large functions in the service layer (>100 lines each)

- `services/etsy_parser.py:parse_etsy_csv` — 148 lines. Handles CSV decoding, failure threshold, per-order grouping, duplicate check, customer upsert, order creation, item creation, status history, and error catching all in one.
- `services/parcel_calculator.py:calculate_parcel_estimate` — 129 lines. Mixes box selection, weight/volume aggregation, and response construction.
- `services/shopify_sync.py:sync_shop_orders` — 108 lines. GraphQL query assembly, retry config, dedup, order translation.
- **Why it matters**: Each is a known-risky integration. `parse_etsy_csv` silently commits half an import on errors (catches per-order exceptions). `calculate_parcel_estimate` is new code (Sprint 10) that already has an inconsistent `volume_cm3` divisor (ARCHITECTURE.md §4.17). Splitting into `_parse_rows` → `_group_by_sale_id` → `_persist_order` would make each piece individually testable — currently only `test_parcel_calculator.py` exists and backend test coverage is minimal (ARCHITECTURE.md §4.15).

### M3. `useProducts.ts` and `usePackaging.ts` are copy-paste mirrors

- Both files are ~80 lines, structure-identical: `useList`, `useCreate`, `useUpdate`, `useDelete`, `useBulkImportConfirm`. Same query-key pattern, same toast-on-success, same `(error: any)` onError, same invalidation logic. The only difference is `products` vs. `packaging` and the DTO types.
- **Why it matters**: Any fix to error handling (e.g., typing the error, adding retry, structured logging) must be applied twice — and will be applied twice more when a fourth resource gets its own hooks file. A `createResourceHooks<T, Create, Update>(resourceName, api)` factory — or at minimum a shared `useMutationWithToast` wrapper — would kill the duplication. Same pattern will recur if the codebase adds hooks for other shop-scoped entities.

### M4. 4 frontend page components are 400–616 lines

- `pages/ShopsPage.tsx` — 616 lines (owner-only shop CRUD + NP config + Shopify config inline).
- `components/orders/detail/DetailLogistics.tsx` — 547 lines (address form + city search + warehouse search + parcel editor + TTN actions all in one).
- `pages/UsersPage.tsx` — 493 lines.
- `components/orders/CreateOrderView.tsx` — 460 lines.
- **Why it matters**: `OrderDetailPanel` was already broken out into 8 `detail/` sub-components (CLAUDE.md calls this a deliberate past refactor — "don't re-merge them"). The same split hasn't happened for these four. `DetailLogistics` especially is the #2 hot file (11 changes/6mo) and has the setState-in-effect bug, 6 `any` types, and the parcel-calculator integration inside it. Breaking `ShopsPage` into `ShopList` + `ShopForm` + `NPConfigSection` would make each of the 6 `any` usages localized and fixable.

### M5. Repeated SQLAlchemy query pattern + 7 `== True` / `!= None` ruff errors

- Pattern `select(Shop).where(Shop.is_active == True)` appears at `routers/imports.py:32`, `routers/shops.py:32,97,189`, `scheduler.py:32`. Variant `Shop.np_api_key_encrypted != None` at `routers/shipping.py:46,70`. `User.is_active == True` at `routers/users.py:114`.
- **Why it matters**: Two layers of debt. (a) The `== True` / `!= None` pattern is a ruff warning (E711/E712) — it happens to work with SQLAlchemy's operator overloading, but ruff's fix (`.where(Shop.is_active)`) would also work and is the documented idiom. (b) The same 3-line "fetch active shop by id" block is copy-pasted 5 times — a `get_active_shop(db, shop_id)` helper in `routers/dependencies.py` (next to the existing `get_shop_for_user`) would also naturally be where multi-tenant isolation (ARCHITECTURE.md §4.4) eventually lives.

### M6. E701 multi-statement lines in service layer (10 occurrences)

- `services/customer_service.py:32–36` (5x) and `services/order_service.py:280–283` (4x): `if x in data: dict[y] = data[x]` one-liners.
- **Why it matters**: The pattern is conditional field-copying — the exact sort of code that should use `.update()` with a dict-comprehension or a mapping table. It's not a bug, but it's brittle: adding a new shipping field requires touching both files identically. A shared `SHIPPING_FIELD_MAP` dict plus `customer_updates = {dst: data[src] for src, dst in MAP.items() if src in data}` collapses 10 lines to 2.

### M7. 5 `react-refresh/only-export-components` warnings in UI primitives

- `components/ui/Toast.tsx`, `badge.tsx`, `button.tsx`, `tabs.tsx`, `textarea.tsx` export both components and non-component helpers (variant constants, hooks). Vite HMR falls back to full reload on edits.
- **Why it matters**: Developer-experience tax — every tweak to a button variant reloads the whole page. The fix is mechanical: split constants into `badge.variants.ts`, etc. `textarea.tsx:5` additionally has an empty interface (`interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}`) which should be a type alias.

### M8. Logging uses `console.*` on the frontend (9 occurrences)

- `frontend/src/components/orders/OrderDetailPanel.tsx:107,111,115` — `console.log`/`error` with `[StatusChange]` tags (clearly left from debugging).
- Also in `ProductVariantSelector.tsx`, `AttachmentManager.tsx`, `OrderDetailView.tsx`, `ShopsPage.tsx`.
- **Why it matters**: Production builds ship `console.log`s with order IDs to end-user devtools. Either strip via Vite config or introduce a `logger.ts` gated on `import.meta.env.DEV`. The `OrderDetailPanel` ones look like live debugging that got committed — compare with the twin `OrderDetailView` where they're absent.

---

## LOW Priority

### L1. `tsconfig.json` deprecation warning

- Single tsc error: `Option 'baseUrl' is deprecated and will stop functioning in TypeScript 7.0`.
- **Why it matters**: Blocks a future TS 7 upgrade; trivial fix (`"ignoreDeprecations": "6.0"` or remove `baseUrl` in favor of `paths` alone).

### L2. E402 in `services/shopify_sync.py` — imports below module-level code

- Lines 15–23 import after `logger = logging.getLogger(__name__)` on line 13.
- **Why it matters**: Cosmetic ordering issue, but also drops `fastapi.HTTPException` as unused. The file history says imports were reshuffled during a refactor — easy cleanup.

### L3. Stray files in repo root

- `backend/orderhub.db` — leftover SQLite file (ARCHITECTURE.md §4.12), not in `.gitignore`.
- `backend/check_db_users.py` — ad-hoc script with unused `uuid` import (ruff F401).
- `scratch/` directory contains 12 one-off MCP/test scripts that show up as "most-changed" in the pre-generated `hot_files.txt` and skew the stats.
- `verify_etsy_fix.py`, `mcp_debug_tools.py`, `mcp_client_verification.py` — scratch scripts referenced in `hot_files.txt` that were added and deleted (the report shows both the `+41` and `-41` entries).
- **Why it matters**: Confuses new contributors and distorts churn metrics. A `scratch/` entry in `.gitignore` and a one-time cleanup commit fixes all of it.

### L4. `shopId` parameter unused in `usePackaging`/`useProducts` delete hooks

- `frontend/src/hooks/usePackaging.ts:36,53` and `useProducts.ts:36,53`: `{ id, shopId }` is destructured, but the `mutationFn` only uses `id`. `shopId` is only used in `onSuccess` for cache invalidation.
- **Why it matters**: Minor — it's intentional (used for invalidation key), but ESLint flags it as "defined but never used" because the destructure pattern confuses the rule. Either rename to `_shopId` in the mutationFn signature or thread it through.

### L5. Hot-file `hot_files.txt` artifact is noisy

- The pre-generated `hot_files.txt` lists scratch scripts (`verify_etsy_fix.py`, `mcp_debug_tools.py`) and file-add/delete pairs as "hot," making the top of the list meaningless. `git log --since=6mo --name-only | sort | uniq -c` produces a more truthful list (used in this report).
- **Why it matters**: Not code debt, but the audit tooling itself is lying. Worth regenerating with `.git` pathspec exclusion for scratch/ + filtering to files that still exist.

---

## Hot-File Instability Inspection (Top 5 by 6-month change count)

Regenerated from `git log --since="6 months ago" --name-only` (pre-generated `hot_files.txt` was distorted by scratch scripts).

| Rank | File | Changes | Size | Notable debt |
|------|------|---------|------|--------------|
| 1 | `frontend/src/components/orders/OrderDetailPanel.tsx` | 12 | 174 | Duplicated with `OrderDetailView` (H3). `handleUpdate: any`. Debug `console.log`s (M8). |
| 2 | `frontend/src/components/orders/detail/DetailLogistics.tsx` | 11 | **547** | Single 547-line function. 6 `any` types. setState-in-effect bug (H2). #2 hot file × biggest file — instability×complexity. |
| 3 | `frontend/src/components/orders/OrdersLayout.tsx` | 10 | 135 | 2 `any` types. Healthy size — churn is likely feature-driven, not debt-driven. |
| 4 | `frontend/src/App.tsx` | 10 | 138 | 10× repeated `<Suspense fallback={<RouteLoadingFallback />}>` wrapper — a `<LazyRoute>` helper would cut the file in half. |
| 5 | `frontend/src/pages/DashboardPage.tsx` | 8 | 277 | No linter findings; churn is healthy feature iteration. |

**Instability signal**: ranks #1 and #2 overlap exactly with the worst linter findings (H2, H3) and the two largest pieces of duplicated/monolithic code in the frontend. Fixing H3 and breaking up `DetailLogistics` would stabilize both — every future edit to the order-detail flow currently has a blast radius of two files and one 547-line component.

---

## Recommended Remediation Order

1. **Auto-fixable now** (hour-scale): `ruff --fix` removes 40 unused imports; `eslint --fix` handles some unused vars; strip `console.*` debug logs in `OrderDetailPanel.tsx` (M8). No semantic risk.
2. **Type consolidation** (day-scale): unify `User`/`UserRole` (H5); introduce `ApiError` + `useMutationWithToast` to kill ~60 `any`s (H1); fix the mypy errors that indicate real bugs (`order_number`, `order_count`, `customer_note`, `parcel_override/length/width/height`) (H6, H4).
3. **Structural refactors** (sprint-scale): extract `useOrderDetailController` from H3; split `create_np_ttn` (H4); split `DetailLogistics` and `ShopsPage` into sub-components (M4); create `createResourceHooks` factory (M3).
4. **Ongoing discipline**: add eslint `no-explicit-any` and `react-hooks/set-state-in-effect` to CI to stop regression. The project's own CLAUDE.md already forbids `any`; the rule just isn't enforced.

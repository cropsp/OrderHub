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

### M9. `tenacity` missing from `backend/requirements.txt` — scheduler import would crash on a clean rebuild ✅ DONE (2026-04-25)

- `services/shopify_sync.py:11` imports `tenacity`, but the package is not declared. Surfaced 2026-04-25 (Session 4) when running pytest in a freshly built backend image — collection failed with `ModuleNotFoundError: No module named 'tenacity'`. Fix: add `tenacity==X.Y` next to `apscheduler` in `requirements.txt`. Trigger: any image rebuild from a clean state, or any CI pipeline that installs from `requirements.txt`.
- **Resolution**: Added `tenacity==9.1.4` to `backend/requirements.txt`.

### M10. `routers/__init__.py` chains every router import — fans out transitive dependencies into any test that imports `routers.*`

- The package's `__init__.py` re-exports all router modules, so `from routers.dependencies import X` triggers the entire router tree (and thus every transitive dep, including `tenacity`, `mcp`, `apscheduler`). Surfaced 2026-04-25 (Session 4) — `tests/test_designer_shop_scoping.py` collection imported the whole tree just to reach one helper. Fix: drop the eager re-exports in `routers/__init__.py` and have `main.py` import each router module by name. Trigger: when adding more backend tests, or alongside M9.

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

### L6. Default currency per shop (model column + migration + auto-fill on order creation)

- Currently currency is only on `Order`/`OrderItem`. There is no per-shop default, so every order entry path has to specify currency explicitly. Surfaced 2026-04-25 when adding KoraKlenu to seed: a shop is conceptually a single-currency storefront (KoraKlenu = UAH), but the model can't express that.
- **Why it matters**: Minor — orders work fine without it. But manual order entry and CSV import both have to either hardcode a currency or fall back to `BASE_CURRENCY`. A `Shop.default_currency` column would let the order creation path auto-fill and let the UI show shop-appropriate currency. Fix: add `default_currency: Mapped[str]` to `Shop` model, alembic migration, and thread it through `OrderCreate` defaulting in `services/orders` + manual entry form.

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

---

## Deferred Security Hardening (2026-04-24 audit remediation)

This section records items identified during the Sprint 11 security audit (`SECURITY_REPORT.md`) that were intentionally deferred during the 2026-04-24 remediation pass. Each item was scoped out because either (a) the safe implementation requires a data migration or rollout we can't justify in early-stage development, (b) the simple implementation has production-breaking failure modes (mass logout, session-nuke races, workflow blockage), or (c) it's a robustness concern below the bar for this pass. Items are grouped by priority when we revisit.

The 2026-04-24 pass implemented: SEC-01 (backward-compat), SEC-03 (prod-only guard), SEC-04 forward-fix only, SEC-05, SEC-06, SEC-07 (backend only), SEC-08 (size cap + Content-Disposition only), SEC-09, SEC-10, plus tech-debt items H1 (hooks only), H2, H3, H4 schema fix, H5, H6.

### Security — High priority to revisit

**SEC-02 (CRITICAL as audited) — Server-side refresh token revocation**
The 2026-04-24 pass implemented only SEC-01 (independent `REFRESH_SECRET_KEY` via a backward-compat fallback). The full remediation — a `refresh_tokens` table with token-family rotation and reuse detection — was deferred because (a) naive rollout invalidates every refresh token in the wild on deploy (mass logout), and (b) "nuke all sessions on reuse-detection" combined with an SPA that can race two tabs through `/refresh` causes cascading re-logout loops. A production-safe rollout needs both a grace-period decode path AND a serialized refresh interceptor on the frontend.
Trigger: first real user population beyond the core team, OR any incident where a refresh token is suspected stolen (no revocation path exists today). When picking this up, also read `frontend/src/api/client.ts` and confirm refresh calls are serialized via a single in-flight promise before enabling reuse-detection.

**SEC-04 — Orphan `order_status_history` repair after system-user migration**
The 2026-04-24 pass inserts a persistent system user and points webhooks + scheduler at it for all *future* history rows. Confirmed state: the Shopify scheduler HAS run in production, so any rows whose `changed_by_id` points at the old hard-coded UUID `00000000-0000-0000-0000-000000000000` or at a non-deterministic `select(User).limit(1)` user (from webhooks) are not repaired. Those rows remain FK-valid but attribute audit events to the wrong or ghost actor.
Trigger: any audit/compliance requirement that historical `changed_by_id` be accurate. Remediation sketch: (1) `SELECT DISTINCT changed_by_id FROM order_status_history WHERE changed_by_id NOT IN (SELECT id FROM users WHERE is_active);` to find affected rows; (2) `UPDATE order_status_history SET changed_by_id = :system_user_id WHERE changed_by_id IN (:known_bad_uuids);`. Lossy — requires explicit operator sign-off before running.

**SEC-06 — MCP session-keyed transports + `handle_post_message` signature fix**
Status: Deferred. MCP server is not the current priority. The project needs a solid core (orders, logistics, catalog) before expanding AI agent capabilities.
Bad pattern: `backend/routers/mcp.py` keeps a single module-global `sse_transport: SseServerTransport | None` (around line 31) that any new SSE connection overwrites at the connect site (around line 106-107). A second concurrent agent session silently steals the first agent's transport — messages can be routed to the wrong session and the first session quietly breaks. Same file's `handle_post_message` POST handler also has a mypy signature mismatch against the upstream SDK (called out in `audit_artifacts/mypy_report.txt`).
Fix sketch: replace the global with a `Dict[str, SseServerTransport]` keyed by session ID (or use the MCP SDK's built-in session manager if it's matured since the original implementation), and update `handle_post_message`'s signature to match the SDK's expected `(scope, receive, send)` shape so mypy stops flagging it.
References: full audit context in `audit_artifacts/SECURITY_REPORT.md` SEC-06; vision/roadmap and the explicit "do not touch" status in `docs/integrations/mcp-server.md`.
Trigger: when MCP server development resumes (per the freeze noted in `CLAUDE.md` Gotchas).

**SEC-08 residual — File upload MIME allow-list + magic-number validation**
The 2026-04-24 pass shipped the size cap (10 MB) and `Content-Disposition: attachment` on downloads — enough to neutralize stored-XSS via inline HTML/SVG and disk-exhaustion DoS. The MIME allow-list was deferred because the designer workflow uses source files (`.ai`, `.psd`, `.eps`, potentially `.zip`) that a naive image/PDF whitelist would block on day one.
Trigger: before exposing uploads to users beyond the core team. First step: `find uploads/ -type f | awk -F. '{print $NF}' | sort -u` to ground-truth actual extensions, then confirm the allow-list with the designer team. Implement magic-number check against a per-extension signature map; do not trust client-supplied `Content-Type`. SVG remains a landmine — exclude unless there's a concrete need.

**SEC-01 residual — Remove backward-compat derivation fallback in `auth_service.py`**
The 2026-04-24 pass made `REFRESH_SECRET_KEY` independent *if set in env*; if unset, it falls back to `settings.SECRET_KEY + "-refresh"` with a startup warning. This preserves existing refresh tokens (no deploy-day logout) but keeps the original SEC-01 vulnerability latent until the fallback is removed.
Trigger: rotate the refresh secret once (set `REFRESH_SECRET_KEY` in all `.env` files, accept the one-time logout) then remove the fallback branch. Safe during any user-facing maintenance window.

**SEC-03 residual — Remove hardcoded secret defaults from `config.py`**
The 2026-04-24 pass added a production-only guard (fail-fast if `ENVIRONMENT=production` and secrets start with `change-me`). Dev defaults are intentionally retained so onboarding a new contributor doesn't require generating secrets to boot the app. The vulnerability is latent only if the production guard is bypassed (e.g., `ENVIRONMENT` misconfigured).
Trigger: when a production deployment checklist exists, replace the runtime guard with a hard requirement (no default at all). Pair with SEC-20 (same class of issue).

**SEC-15 — Rate limiting**
No rate limiting on any endpoint. Highest-risk targets: `/api/auth/login` (brute force), `/api/shipping/cities|warehouses` (burn NP API key across the org), `/api/imports/etsy` (memory DoS via large CSV), `/api/orders/action/export` (memory DoS via 10k-order in-memory CSV).
Trigger: first public-ish deployment OR a recorded abuse event. Recommended: `slowapi` with per-IP `/auth/login` limit (5/min) and per-user limits on expensive endpoints. No dependency on other deferred items.

**SEC-16 — PII-redacted logging in `routers/shipping.py`**
`logger.info(f"Creating NP TTN with payload: {payload}")` at line 235 logs full customer name, phone, address, sender details. Log rotation caps at 25 MB (`backend/logs/server.log`) so PII is bounded but not absent. Not touched in the 2026-04-24 pass because SEC-07 already required editing this file — both should be done in one pass next time.
Trigger: any log export to a shared monitoring system, or a privacy review. Fix: log `order_id` + `shop_id` + `ttn_status` only; drop the payload dict.

**SEC-11 — Migrate from `python-jose` to `PyJWT`**
`python-jose` is unmaintained; future JWT CVEs won't be patched. Not done in 2026-04-24 because (a) auth service was already in flux (SEC-01) and (b) migration touches every `decode_token`/`create_*_token` callsite plus error handling (`JWTError` → `PyJWTError`).
Trigger: a published CVE against `python-jose`, OR the next intentional auth service refactor. `PyJWT` is near drop-in for HS256.

### Security — Medium priority to revisit

**SEC-07 residual — Frontend string-matching on error `detail`**
The 2026-04-24 pass sanitized server-side `detail=str(e)` sites but left the frontend audit undone per explicit decision. `// TODO(SEC-07)` comments were added at changed backend sites noting that callers pattern-matching on specific error text may now see a generic message.
Trigger: first user report of "flow X used to show a specific message and now shows a generic one." Remediation: `grep -rn 'error?\.response?\.data?\.detail' frontend/src/`, decide per-case whether to preserve the specific backend message (via a typed error-code enum) or change the frontend to use HTTP status + generic message.

**SEC-12 — Import preview token binding + Redis-backed storage**
Import preview tokens are plain UUIDs stored in a process-memory dict (`services/import_service.py`). Any authenticated user with a valid token can confirm another user's import. In multi-worker deployments (gunicorn `-w N`) the confirm call can hit a different worker than the preview — silent failure. Single-process `uvicorn --reload` avoids this today.
Trigger: before switching to `workers > 1`. Fix: bind `user_id` into the preview record and check on confirm; for multi-worker, move `_storage` to Redis or a DB table.

**SEC-13 — Seed script production guard**
`backend/seed.py` creates `owner123`/`manager123`/`designer123` accounts if the users table is empty, with no `ENVIRONMENT` check. Low immediate risk (no one runs `seed.py` against production on purpose) but no code-level safety.
Trigger: first production deployment. One-liner: `if settings.ENVIRONMENT == "production": sys.exit(...)` at the top of `main()`.

**SEC-17 — Tighten CORS `allow_methods` / `allow_headers`**
`main.py:47-53` allows all methods and headers; origin is already restricted to `FRONTEND_URL`. Tightening is defense-in-depth only.
Trigger: any CORS-related incident or external security review. Replace with explicit lists (`GET, POST, PATCH, DELETE, OPTIONS` and `Authorization, Content-Type`).

**SEC-19 — Disable SQL echo in development by default**
`database.py:21` uses `echo=settings.is_development`, so every query (including user emails and bcrypt hashes on INSERT) streams to stdout. Developer-convenience tradeoff.
Trigger: standardized logging setup OR any shared-dev-environment deployment. Fix: `echo="debug"` or opt-in via `settings.SQL_ECHO`.

**SEC-20 — Remove default DB credentials**
`POSTGRES_USER="crm"` / `POSTGRES_PASSWORD="crm_pass"` hardcoded in `config.py` and `.env.example`. Same class as SEC-03; only blocks naive production deploys.
Trigger: pair with SEC-03 production-deployment-checklist work. Fail-fast on missing DB creds when `ENVIRONMENT=production`.

**SEC-21 — Password change endpoint**
No `POST /api/auth/change-password`. Temp passwords from user creation are permanent. Acceptable for the core team but users can't rotate compromised credentials without DB access.
Trigger: first non-team user OR the first "I leaked my password in Slack" incident. Pair with SEC-02 when both ship (change-password should invalidate all refresh tokens for that user).

### Security — Low priority to revisit

**SEC-22 — ILIKE wildcard injection in search** (`customers.py:43-44`, `order_service.py:54`)
`%` and `_` in search terms aren't escaped. SQL injection is not possible (SQLAlchemy parameterizes); pattern-probe info disclosure is. One-liner per callsite: `escaped = search.replace("%", "\\%").replace("_", "\\_")`.
Trigger: free cycle in a search-related PR, or a pattern-probe security report.

**SEC-23 — Path traversal check off-by-one** (`file_storage.py:50`)
`if uploads_dir not in abs_path.parents` misses the edge case of a file directly inside `UPLOADS_DIR`. Current upload logic always nests under `order_id/` so not exploitable. Replace with `abs_path.is_relative_to(uploads_dir)`.
Trigger: any refactor of `file_storage.py`.

**SEC-24 — OpenAPI docs gated only by environment flag** (`main.py:43-44`)
`/docs` and `/redoc` hidden when `ENVIRONMENT != development`. Defense-in-depth would add an auth guard so a misconfigured `ENVIRONMENT` doesn't leak the API surface.
Trigger: pair with SEC-20 production-checklist work.

**SEC-25 — Shopify retry catches all exceptions** (`shopify_sync.py:67`)
`retry_if_exception_type((httpx.HTTPError, Exception))` retries on auth failures, parse errors, and data bugs. Wastes calls; can contribute to rate-limit lockout. Drop `Exception`.
Trigger: next Shopify sync investigation or any `tenacity` library change.

**SEC-26 — Misleading 403 wording on orphan attachment access** (`backend/routers/attachments.py` download handler)
The SEC-10 designer-access check returns 403 "Not assigned to this order" when the parent order has been deleted but the attachment row + file still exist. For a designer the wording is wrong (the order doesn't exist; it's not an authorization failure), and for owner/manager the orphan is still served. Risk is cosmetic + low data-exposure — the actual remediation depends on whether `Attachment.order_id` has a cascading delete in the SQLAlchemy model. Surfaced during Phase 2.2 SEC-10 review.
Trigger: any attachment-cleanup work, OR a user report about confusing 403s after order deletion. Fix sketch: check order existence first and return 404 if missing; orphan cleanup belongs in a separate maintenance task.

**SEC-27 — Zero-byte uploads silently accepted** (`backend/services/file_storage.py:save_file`)
The streaming save loop exits immediately on an empty `UploadFile` (the `while content := await ...read(...)` walrus stops on `b""`), creating a 0-byte file on disk and a DB row with `file_size=0`. No minimum-size check exists. Surfaced during Phase 2.2 SEC-08 review.
Trigger: free cycle, OR a user report of "blank attachment" rows. Fix: reject `file_size == 0` in the upload handler with 400, OR enforce in `save_file` and return a typed error like `FileTooLargeError`.

**SEC-18** — Resolved by H4 in the 2026-04-24 pass (`CreateTTNRequest` schema now matches the handler). Included for audit completeness.

### Tech debt — not shipped in this pass

**H1 residual — ~60 remaining `any` types outside `frontend/src/hooks/`**
The 2026-04-24 pass introduced `ApiError` + `useMutationWithToast` and migrated mutation-hook error handlers, killing ~60 `any` lint errors. Remaining ~60 are in Nova Poshta response handlers (`DetailLogistics.tsx`, 6), CSV import UIs (`CSVImportModal.tsx`, 9), form components (`ProductForm.tsx`, `PackagingForm.tsx`, 5 each), and `ShopsPage.tsx` (6). These need NP response types and form-payload types — more than 2–3 hours of work per hotspot.
Trigger: either the next feature touching each file (natural place to type local state) or a dedicated typing pass. Add eslint `no-explicit-any` as `error` (not `warn`) to CI at that time to prevent regression.

**H4 residual — `create_np_ttn` function split**
The 2026-04-24 pass fixed the `CreateTTNRequest` schema mismatch (latent `AttributeError`) and the `order.order_number` → `external_id` bug. The 169-line monolith at `routers/shipping.py:88-256` remains. Recommended extraction: sender resolution, recipient resolution, payload building → `services/nova_poshta.py`; router handler drops to ~30 lines.
Trigger: next bug in the TTN flow, or any change to the NP payload structure. Schema cleanup that just landed makes this materially easier.

**H6 residual — `Customer.order_count` real column vs. computed**
The 2026-04-24 pass fixed the mypy error at the two callsites by switching to a subquery count. If this is read on hot paths it's an N+1 risk.
Trigger: first p95 regression on customer-list endpoints, or a profiling pass. Options: `@hybrid_property` with matching subquery expression, or a materialized column updated via SQLAlchemy event listener.

### Deploy-day risks flagged during remediation (preserved for memory)

These are not items to implement — they are risks surfaced while choosing the remediation scope. Recorded so the context isn't lost if someone later asks "why didn't we just do X":

- **Mass-logout on secret rotation**: any change to `REFRESH_SECRET_KEY` invalidates all refresh tokens in browsers. The 2026-04-24 pass avoids this by keeping the derived fallback; any future removal (SEC-01 residual) must be paired with a maintenance window.
- **SPA reuse-detection race**: if SEC-02 is implemented with "revoke token family on reuse" and the frontend interceptor doesn't serialize refresh calls, two tabs racing `/refresh` will nuke the user's sessions. Frontend `api/client.ts` must be audited first.
- **Designer starvation on SEC-05**: a newly-created designer with zero assigned orders will get 403 on every shop-scoped endpoint. Documented as intended behavior; onboarding must assign at least one order before the designer can see a shop.
- **Workflow block on MIME whitelist**: a naive `{png,jpeg,pdf}` allow-list blocks `.ai`/`.psd`/`.eps` — the actual file types a leather-goods design workflow uses. Ground-truth the upload directory before shipping any whitelist.

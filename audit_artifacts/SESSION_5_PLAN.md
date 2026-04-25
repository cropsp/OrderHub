# Session 5 — Execution Plan

> Source: `audit_artifacts/TECH_DEBT.md` (MEDIUM section, items M1–M10)
> Generated: 2026-04-25 — read-only planning artifact, no code changes

This session focuses on the MEDIUM tier. Sessions 1–4 cleared the CRITICAL/HIGH security tier and the structural HIGH tech-debt items (H1 hooks, H2, H3, H4 schema, H5, H6). What remains in MEDIUM is a mix of one-line infra fixes that gate everything else, mechanical Python/TS hygiene, and three real refactors (service-layer splits, hooks factory, page-component splits).

---

## All MEDIUM items, grouped by type

### Infra / build / tooling

| ID | Item | Effort | Notes |
|----|------|--------|-------|
| **M9** | `tenacity` missing from `backend/requirements.txt` | **small** (1 line) | Blocks any clean rebuild; surfaced when running pytest in a fresh image. |
| **M10** | `routers/__init__.py` re-exports the entire router tree | **small** | Drop eager re-exports; have `main.py` import each router by name. Unblocks targeted backend tests. |
| **M1** | 45 unused-import errors (ruff F401) | **small** | `ruff --fix` handles ~40 mechanically. Webhooks.py needs a manual look (`update_order` is the abandoned-implementation tell). |

### Backend (Python)

| ID | Item | Effort | Notes |
|----|------|--------|-------|
| **M5** | Repeated `== True` / `!= None` SQLAlchemy + `get_active_shop` helper | **small** | Two parts: (a) ruff E711/E712 fixes (~7 sites), (b) extract `get_active_shop(db, shop_id)` next to `get_shop_for_user` in `routers/dependencies.py`. |
| **M6** | 10 × E701 multi-statement lines in `customer_service.py` / `order_service.py` | **small** | Replace ad-hoc `if x in data: dict[y] = data[x]` blocks with a shared `SHIPPING_FIELD_MAP` and a dict-comprehension. |
| **M2** | 3 large service-layer functions (>100 lines) | **medium-to-large** (3 separate refactors) | `etsy_parser.parse_etsy_csv` (148 lines, silently commits half-imports), `parcel_calculator.calculate_parcel_estimate` (129 lines, has the `volume_cm3` divisor inconsistency from ARCHITECTURE.md §4.17), `shopify_sync.sync_shop_orders` (108 lines). Each is independent. |

### Frontend (TS/React)

| ID | Item | Effort | Notes |
|----|------|--------|-------|
| **M8** | 9 × `console.*` calls left in production code | **small** | `OrderDetailPanel.tsx:107,111,115` are clearly committed debug logs. Decide: strip via Vite config or introduce `logger.ts` gated on `import.meta.env.DEV`. |
| **M7** | 5 × `react-refresh/only-export-components` warnings | **small** | Split variant/helper exports out of `Toast.tsx`, `badge.tsx`, `button.tsx`, `tabs.tsx`, `textarea.tsx` into sibling `*.variants.ts` files. Mechanical. Plus the empty-interface fix in `textarea.tsx:5`. |
| **M3** | `useProducts.ts` / `usePackaging.ts` are copy-paste mirrors | **medium** | Build a `createResourceHooks<T, Create, Update>(resourceName, api)` factory or a smaller `useMutationWithToast` wrapper. `useShipping.ts` already has the typed `ApiError` from Phase 2.1 — reuse that pattern. |
| **M4** | 4 × frontend page components 400–616 lines | **large** (4 separate splits) | `ShopsPage.tsx` 616, `DetailLogistics.tsx` 547 (#2 hot file), `UsersPage.tsx` 493, `CreateOrderView.tsx` 460. The Phase 2.1 `OrderDetailPanel` → `detail/*` split is the model. `DetailLogistics` is the highest payoff per line touched. |

---

## Recommended execution order

The order is dictated by what **unblocks** other items, not by severity. Two threads run in parallel after the infra batch — backend cleanups and frontend cleanups don't share files.

### Batch 1 — Infra (do first, blocks everything)

1. **M9** → adds `tenacity` to `requirements.txt`. Without this, no backend test or scheduler runs in a clean image. **Verify**: `docker compose run --rm backend python -m pytest tests/` succeeds without ad-hoc pip installs.
2. **M10** → drop eager re-exports in `routers/__init__.py`, update `main.py` to import each router module directly. **Verify**: `from routers.dependencies import get_shop_for_user` no longer triggers `tenacity`/`mcp`/`apscheduler` imports. Targeted unit tests stop pulling the whole tree.

> **Why first:** every later backend item benefits from a working test loop. M10 in particular makes the test for any new helper (M5's `get_active_shop`, M3's typed factory, M2's split functions) cheaper to write.

### Batch 2 — Mechanical Python cleanups (small, parallelizable, do as one batch)

3. **M1** → `ruff --fix` to remove 40 unused imports; manual review on `webhooks.py` and `services/parcel_calculator.py` where dead code paths cluster. Defer the `update_order` import in `webhooks.py` only if its removal would touch the abandoned-implementation surface — note it explicitly in the commit if so.
4. **M5** → fix `== True`/`!= None` (ruff E711/E712) at 7 sites; extract `get_active_shop(db, shop_id)` into `routers/dependencies.py`. Migrate the 5 call-sites (`routers/imports.py:32`, `routers/shops.py:32,97,189`, `scheduler.py:32`).
5. **M6** → introduce `SHIPPING_FIELD_MAP` (or per-service equivalent), collapse 10 ad-hoc `if x in data` lines.

> **Why batched:** all three are ruff-driven, single-commit-each, no behavior change. Doing them together gives one clean `ruff` baseline before M2's service-layer refactors land.

### Batch 3 — Frontend hygiene (small, parallelizable with Batch 2)

6. **M8** → strip the committed debug `console.log`s in `OrderDetailPanel.tsx` and decide on a `logger.ts` gate. Do this **before** any component split touches those files; otherwise the splits will inherit the noise.
7. **M7** → split UI-primitive variant exports into sibling files. No logic change. Verify HMR no longer falls back to a full reload on `button.tsx` edits.

### Batch 4 — Real refactors (medium-to-large)

8. **M3** → build the resource-hooks factory or `useMutationWithToast` wrapper. Migrate `useProducts.ts` and `usePackaging.ts` first (the two files the audit flagged); leave `useShipping.ts` alone unless the abstraction lands cleanly. **Do before M4** — `ShopsPage`/`UsersPage` consume these hooks, and a typed factory makes the page-split diffs read better.
9. **M2** → split the three large service functions. Independent, can be done in any order. Suggest order:
   - `parcel_calculator.calculate_parcel_estimate` first (newest code, smallest blast radius, has the known `volume_cm3` divisor bug to fix in passing).
   - `etsy_parser.parse_etsy_csv` next (the silent-half-commit-on-error behavior is genuinely broken; splitting `_parse_rows` → `_persist_order` makes it testable).
   - `shopify_sync.sync_shop_orders` last (touches webhook + scheduler paths recently changed in Phase 2.4 — let those settle first).

   Each split should land its own test file in `backend/tests/`.

10. **M4** → page-component splits, in priority order:
    - `DetailLogistics.tsx` (547 lines, #2 hot file, highest payoff). The Phase 2.1 `OrderDetailPanel` → `detail/` model applies directly.
    - `ShopsPage.tsx` (616 lines, owner-only — narrowest exposure to break). Split into `ShopList` + `ShopForm` + `NPConfigSection`.
    - `UsersPage.tsx` and `CreateOrderView.tsx` last; both are stable and lower-churn than the first two.

> **Why last:** M4 is the only item where mistakes are user-visible. By the time it's reached, hooks (M3), logging (M8), and ruff/HMR baselines are already clean — so the splits don't carry forward debt that would have to be re-fixed later.

---

## Out-of-scope for Session 5 (explicit)

- LOW-priority items L1–L5 — defer to a future session.
- Deferred security items in TECH_DEBT.md "Deferred Security Hardening" — most have explicit triggers (SEC-02 user growth, SEC-04 orphan repair, SEC-15 public deploy). Don't pull them in opportunistically.
- H1 residual (~60 remaining `any`s in form/CSV/NP code) — was explicitly scoped at "next feature touching each file" in the Phase 2.1 retro. Leave alone unless M4 naturally touches the same hotspots, in which case fix locally and don't expand scope.

---

## Effort summary

| Bucket | Items | Estimated effort |
|--------|-------|------------------|
| Infra batch | M9, M10 | 1–2 h total |
| Mechanical Python | M1, M5, M6 | 2–4 h total (mostly ruff + small helper) |
| Frontend hygiene | M7, M8 | 1–2 h total |
| Real refactors | M3, M2, M4 | 1–3 days, gated by review and per-split tests |

Recommendation: complete batches 1–3 in one sitting (gives a clean baseline and one combined commit-set per batch), then take M3 / M2 / M4 as **separate sessions** — each is large enough that bundling them risks Phase-2-style multi-commit drift on the same file.

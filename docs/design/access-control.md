# Access Control — Current Model (USER-ACCESS-1 + USER-ACCESS-2)

**Status:** describes the state of `main`. Extracted verbatim from CLAUDE.md § Gotchas on 2026-08-21 (docs restructuring; content unchanged, only re-sectioned).
**Read this BEFORE touching** any endpoint that reads or mutates shops, orders, dashboards, finance, products, materials/overhead costs, partner payouts, imports, attachments, or shipping TTNs.
**Reasoning** (rejected alternatives, OQ decisions): `implementation_plan.md` → USER-ACCESS-1 and USER-ACCESS-2 closure entries.

## 1. Shop access (USER-ACCESS-1, supersedes SEC-05)

Access to a shop is an **explicit grant** in the `user_shop_access` table, resolved by `access_service.get_shop_scope` (returns a `ShopScope` value object — never a None sentinel) and enforced by `assert_shop_access` (shop-id surfaces) / `assert_order_access` (order surfaces) in `routers/dependencies.py`. OWNER is unrestricted (superuser; no grant rows — the resolver short-circuits). MANAGER/DESIGNER see only granted shops.

**Assignment wins:** a designer always sees orders assigned to them, and assigning an order to a designer auto-materialises their grant for that shop (hook in `order_service.update_order` + `change_order_status`), so order-level and shop-level access stay coherent.

## 2. Historical correction — why SEC-05 was not enough

SEC-05's original guard (`get_shop_for_user`) reached only **4 catalog endpoints** and derived designer access from order assignments — it did NOT gate "all shop-level endpoints". USER-ACCESS-1 replaced derivation with explicit grants and swept enforcement across orders (list/detail/mutations/CSV export), dashboard aggregates, finance (closed the any-manager-reads-any-P&L hole), shops (list/detail), products (incl. by-id), partner_payouts, imports, overhead receipts, attachments, and shipping TTNs.

## 3. Deliberately unscoped surfaces + defaults

Deliberately unscoped (global, no `shop_id`): materials + packaging catalogs, dashboard low-stock packaging + unallocated (NULL-shop) overhead, and the NP city/warehouse lookup utilities. New shops auto-grant to effectively-unrestricted managers only; new managers default to all shops at creation. See `implementation_plan.md` USER-ACCESS-1 and `tests/test_route_scope_completeness.py` (the classification that fails if a new `{shop_id}` route is left unclassified).

## 4. Money visibility — capability flags (USER-ACCESS-2)

**Capability flags** compose with shop scope. `view_finance` (P&L / dashboard revenue / partner payouts) and `view_costs` (itemised costs: per-order `FINANCIAL_FIELDS` + `computed_production_cost`, product `cost_price` + BOM cost, material/overhead unit costs, finance COGS cards) live in `user_capability` (no row = role default; `models.user.Capability` is a plain String, NOT a PG enum). Resolved by `access_service.get_capabilities` → a `CapabilitySet` value object (`has(cap)`, never a None sentinel); enforced by `assert_capability` / `require_capability` in `routers/dependencies.py`. OWNER holds every capability (resolver short-circuit; no rows).

**Backfill preserved today's incoherence:** existing MANAGERs → `view_finance=true, view_costs=false`; new non-owner users default deny-by-default (both false).

**Cost censoring is null-in-200 on mixed surfaces** (orders list+detail share `order_service.censor_order_financials`; product `cost_price`/BOM cost nulled) and **403 on cost-only endpoints** (`/products/{id}/bom/cost`, materials/overhead routers). `view_finance`-without-`view_costs` sees revenue + net_profit but the itemised cost cards are stripped (dashboard + finance, OQ-3a: total cost stays inferable from net_profit — accepted).

**Completeness is guarded by `tests/test_money_field_completeness.py`** — it fails if a new numeric response field or money route is left unclassified (this is how LEAK 1/2 would now be caught).

## 5. Audit

Grant/revoke of both shop access and capabilities is recorded in the `access_audit` table (actor defaults to `SYSTEM_USER_ID` for automated writes). Note: `access_audit.target_user_id` means "whose access changed" — partner-config changes audit elsewhere (see `docs/design/partner-config-current.md`).

## 6. Executable guards (the real enforcement completeness)

- `tests/test_route_scope_completeness.py` — every registered `{shop_id}` route must be classified (`guarded` / `owner-only` / `unscoped:*`); an unclassified new route fails the suite.
- `tests/test_money_field_completeness.py` — every float/Decimal response field must be classified (revenue/cost/margin/money/neutral) and every money route must carry an enforcement verdict.

These tests are the completeness contract; this document is the narrative. If they disagree, the tests win — then fix this document.

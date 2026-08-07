"""USER-ACCESS-2 (OQ-5) — money-surface enforcement-completeness guard.

LEAK 1 (list_orders never censored costs) and LEAK 2 (computed_production_cost
never nulled) happened because a cost field drifted onto a response with nobody
forcing a decision about whether it must be gated. This test makes that
impossible to repeat, at two levels:

1. FIELD level — every float/Decimal field on any live response model must be
   classified (revenue / cost / margin / money / neutral). A new numeric response
   field FAILS here until classified. Costs are float/Decimal in this codebase;
   counts/dimensions are int, so the float/Decimal filter targets money without
   drowning in quantities.

2. ROUTE level — every route whose response model carries a non-neutral money
   field must be classified with an enforcement verdict, and any route carrying a
   `cost`-classified field must be gated by view_costs (null or 403). A new money
   route, or a cost field appearing on an under-gated route, FAILS here.

Plus a cross-check that the per-order cost fields on OrderResponse are exactly
order_service.ORDER_COST_FIELDS — so a new order cost field cannot be added
without extending the shared censor set (the direct LEAK 2 guard).
"""
import decimal
import typing

import main
from fastapi.routing import APIRoute
from pydantic import BaseModel

from schemas.order import OrderResponse
from services.order_service import ORDER_COST_FIELDS


# ── Field classification ───────────────────────────────────
#   revenue → revenue-side figure (order/product selling value)
#   cost    → itemised production/material cost input (VIEW_COSTS-gated)
#   margin  → derived net figure (revenue − cost); gated by view_finance
#   money   → generic monetary amount (partner settlements, per-currency cards)
#             whose kind depends on context; gated at the route/card level
#   neutral → numeric but not money (percentages, quantities, dimensions)
MONEY_FIELD_CLASSIFICATION: dict[str, str] = {
    # revenue
    "revenue": "revenue",
    "total_revenue": "revenue",
    "total_price": "revenue",
    "unit_price": "revenue",
    "price": "revenue",
    # ORDER-SHIPPING-1: what the customer paid, decomposed. `revenue`, NOT
    # `cost` — the verdict `platform_fee` two blocks down carries. That one is a
    # fee we PAY out of the order; these three are components of `total_price`
    # itself, which is classified `revenue` right above and has never been
    # censored, so gating them would hide part of a number the same caller can
    # already see in full.
    #
    # `discount_total` is the one worth arguing: it is a revenue DEDUCTION, and
    # `total_refunds` below — also a revenue deduction — is classified `money`.
    # The difference is where it travels. `total_refunds` rides finance routes
    # gated by view_finance; this rides the order, beside `total_price`, for
    # anyone allowed to see the order at all. Same kind as its neighbours here.
    #
    # Deliberately NOT added to ORDER_COST_FIELDS: that set is compared for
    # EQUALITY against the `cost`-classified fields of OrderResponse
    # (test_order_cost_fields_match_censor_set below), so a `cost` verdict here
    # would force censoring and drag every order route back through the
    # view_costs gate for revenue the caller is entitled to.
    #
    # ORDER-SHIPPING-2's `shipping_discount` is classified with them and for the
    # same reason: it is a component of the same decomposition, travels on the
    # same order payload, and is derivable from figures the caller already sees
    # in full. Gating it alone would hide the reason a shipping charge is 0.00
    # from someone allowed to see the 0.00.
    "shipping_revenue": "revenue",
    "shipping_discount": "revenue",
    "discount_total": "revenue",
    "tax_total": "revenue",
    # cost (itemised)
    "production_cost": "cost",
    "shipping_np_cost": "cost",
    "platform_fee": "cost",
    "computed_production_cost": "cost",
    # FX-CONVERSION: provenance for computed_production_cost. cogs_basis_amount is
    # literally the same money pre-conversion. cogs_fx_rate is a public number on
    # its own, but it is classified `cost` so it is censored WITH the cost it
    # explains — a caller who may not see the cost has no use for its rate, and
    # publishing one beside a nulled other is incoherent.
    "cogs_fx_rate": "cost",
    "cogs_basis_amount": "cost",
    # FX-CONVERSION: the BOM cost preview expressed in one target currency. NOT
    # named `amount` on purpose — that bare name is already classified "money"
    # here, and this map is keyed globally by field name, so reusing it would
    # have inherited the wrong verdict with nobody making a decision.
    "converted_cost": "cost",
    # The rate carried INSIDE that converted block, to explain it. Classified
    # `cost` rather than neutral because it is censored together with the figure
    # it explains — routers/products.py drops the whole `converted` block without
    # VIEW_COSTS. Contrast the `uah_per_usd_*` fields on /api/settings/fx below,
    # which are neutral: there the rate is standalone owner config with no cost
    # anywhere near it. Same number, different company.
    "uah_per_usd": "cost",
    # STATEMENT-IMPORT: the Etsy statement import report. All four are costs Etsy
    # charged — the per-order fee (matched, unmatched, or overridden) and the two
    # monthly overhead totals. Named with explicit suffixes rather than reusing
    # `amount` / `total_cost`, which are already classified here under the global
    # name key and would have inherited a verdict with nobody deciding.
    "platform_fee_amount": "cost",
    "previous_platform_fee": "cost",
    "statement_platform_fee": "cost",
    "ads_overhead_amount": "cost",
    "account_fee_overhead_amount": "cost",
    # STATEMENT-IMPORT partition checksum: the same money as the three fields
    # above, re-summed from the stored rows to prove they partition. Same kind,
    # same route, same verdict — `booked_cost_total` is deliberately not called
    # `total_cost`, which is already classified here and would have inherited a
    # verdict silently.
    "booked_cost_total": "cost",
    "platform_fee_total": "cost",
    "cost_price": "cost",
    "current_unit_cost": "cost",
    "material_current_unit_cost": "cost",
    "effective_unit_cost": "cost",
    "unit_cost": "cost",
    "unit_cost_at_movement": "cost",
    "line_cost": "cost",
    "total_cost": "cost",
    "shipping_cost": "cost",
    "total_production_cost": "cost",
    "total_fees": "cost",
    # margin
    "net_profit": "margin",
    "balance_owed": "margin",
    # money (generic amounts)
    "amount": "money",
    # SHOPIFY-REFUNDS: refunds returned to the customer — a revenue-side deduction,
    # gated at the route level by view_finance (like revenue/net_profit), NOT an
    # itemised view_costs cost. The finance page's `refunds` KpiCard is covered via
    # its leaf `amount`/`change_percent` fields.
    "total_refunds": "money",
    # STATEMENT-IMPORT cross-check figures, reported but never booked: the
    # statement's own revenue base (Sale − buyer tax), its refunds, and the
    # Payoneer payouts. They travel on a route already gated view_costs-403, so
    # `money` is the honest kind here — none is an itemised production cost.
    "statement_base_amount": "money",
    "refunds_amount": "money",
    "deposits_amount": "money",
    "base_amount": "money",
    "computed_amount": "money",
    "paid_amount": "money",
    "total_paid": "money",
    "total_settled": "money",
    # neutral (not money)
    "change_percent": "neutral",
    "percent": "neutral",
    "waste_percent": "neutral",
    # BOM-WASTE-1: the material's waste allowance, denormalized onto BomItemRead
    # so line_cost can include it. A process parameter, not money — already
    # exposed unstripped as `waste_percent` on the materials surface.
    "material_waste_percent": "neutral",
    # FX-CONVERSION: exchange rates, not amounts. UAH per 1 USD as published by
    # NBU — a public number, and no part of it reveals a cost. Classified neutral
    # so /api/settings/fx stays out of _money_routes() entirely; the CONVERTED
    # figures derived from these (order cogs_*, BOM converted_cost) are classified
    # `cost` and censored, which is where the money actually is.
    "uah_per_usd_effective": "neutral",
    "uah_per_usd_override": "neutral",
    "uah_per_usd_cached": "neutral",
    # SHOP-FEE-1: the shop's total effective transaction rate. Neutral by the
    # same reading as uah_per_usd_effective above — a configured rate, not an
    # amount, and no cost figure travels with it on the shops surface. It is
    # nonetheless nulled for callers without VIEW_COSTS in routers/shops.py
    # (`_can_view_fee_percent`), because rate × total_price reconstructs
    # platform_fee exactly and total_price is never censored. Neutral here keeps
    # /api/shops — the sidebar source every role hits — out of _money_routes().
    "fee_percent": "neutral",
    "qty": "neutral",
    "qty_per_unit": "neutral",
    "delta": "neutral",
    "stock_quantity": "neutral",
    "low_stock_threshold": "neutral",
    "np_default_volume_m3": "neutral",
    "np_default_weight_kg": "neutral",
    "total_volume_cm3": "neutral",
    "volume_cm3": "neutral",
    # WB-TRACK-1: elapsed-day counts on the delivery tracking surface. Float
    # rather than int so "0.6 days overdue" does not round to "on time", and
    # classified explicitly rather than dodging this guard by making them ints —
    # the whole point is that a new numeric field forces a decision. Nothing on
    # /api/westernbid/tracking carries a currency amount.
    "days_overdue": "neutral",
    "days_since_movement": "neutral",
    # PARTNER-CONFIG-1
    #
    # `fx_rate_used`: NEUTRAL, and the obvious verdict is the wrong one. The
    # nearby precedent `cogs_fx_rate` above is classified `cost` because it is
    # censored together with the COGS figure it explains. Classifying this one
    # `cost` would fail test_cost_fields_only_on_cost_gated_routes: it rides the
    # partner-payouts settlement routes, whose verdict is `view_finance` with no
    # `view_costs`, so the only ways out would be gating the whole partner-payout
    # surface behind VIEW_COSTS (which locks MANAGERs out of settlements they are
    # meant to see) or censoring the rate. Neither is right.
    #
    # `neutral` is honest on the `uah_per_usd_effective` reading: a standalone
    # configured rate with no itemised cost travelling beside it. The PROFIT base
    # does contain COGS, but only folded into `base_amount` — already `money` and
    # already behind view_finance — and a single rate does not let anyone invert
    # a five-term fold back into its components.
    "fx_rate_used": "neutral",
    # Same kind, same route and same gate as `base_amount` (money): it IS a base
    # amount, just recomputed for the staleness badge instead of stored.
    "recomputed_base_amount": "money",
    # One component of a settlement base, shown in the preview so the operator
    # can see why the number is what it is. `money` rather than `revenue`/`cost`
    # because a single term may be either (items_revenue vs cogs) — the field is
    # a generic amount whose kind depends on its sibling `name`. It appears only
    # on the preview response, already gated view_finance. Note the PROFIT
    # preview does expose COGS here as one term; that is the same exposure
    # `base_amount` already carries and is the point of the panel.
    "converted": "money",
}

NON_NEUTRAL = {"revenue", "cost", "margin", "money"}


# ── Route enforcement verdicts ─────────────────────────────
#   view_costs-null           → 200; cost fields nulled for callers w/o VIEW_COSTS
#   view_costs-403            → whole endpoint 403 w/o VIEW_COSTS (cost-only)
#   view_finance              → gated by VIEW_FINANCE (money surface)
#   view_finance,view_costs-strip → VIEW_FINANCE to reach; itemised cost cards
#                                    stripped w/o VIEW_COSTS
#   revenue-only              → exposes only revenue-side money (no cost), so no
#                               view_costs gate; shop/role guards still apply
MONEY_SURFACE_ENFORCEMENT: dict[str, str] = {
    "GET /api/dashboard": "view_finance,view_costs-strip",
    "GET /api/materials": "view_costs-403",
    "GET /api/materials/{material_id}": "view_costs-403",
    "GET /api/materials/{material_id}/movements": "view_costs-403",
    "GET /api/materials/{material_id}/receipts": "view_costs-403",
    "GET /api/orders": "view_costs-null",
    "GET /api/orders/{order_id}": "view_costs-null",
    "GET /api/overhead-materials/{overhead_id}/receipts": "view_costs-403",
    "GET /api/products/{id}": "view_costs-null",
    # MAT-6: whole-invoice read spanning both receipt ledgers. Cost-only surface,
    # 403'd wholesale by the router-level require_capability(VIEW_COSTS).
    "GET /api/receipts/by-invoice": "view_costs-403",
    "GET /api/products/{id}/bom": "view_costs-null",
    "GET /api/products/{id}/bom/cost": "view_costs-403",
    "GET /api/shops/{shop_id}/finance": "view_finance,view_costs-strip",
    "GET /api/shops/{shop_id}/partner-payouts/balances": "view_finance",
    "GET /api/shops/{shop_id}/partner-payouts/payments": "view_finance",
    "GET /api/shops/{shop_id}/partner-payouts/settlements": "view_finance",
    # PARTNER-CONFIG-1: the staleness recompute returns recomputed_base_amount,
    # the same kind of figure as base_amount on the settlements list.
    "GET /api/shops/{shop_id}/partner-payouts/settlements/staleness": "view_finance",
    # OWNER-only cross-shop aggregate. OWNER holds every capability, so the
    # verdict is view_finance by resolver short-circuit; the real gate is the
    # router-level require_role(OWNER). Deliberately not offered to a scoped
    # MANAGER — see partner_payout_service.get_partner_balances.
    "GET /api/partners/balances": "view_finance",
    "GET /api/shops/{shop_id}/products": "view_costs-null",
    "PATCH /api/materials/{material_id}": "view_costs-403",
    "PATCH /api/orders/items/{item_id}": "revenue-only",
    "PATCH /api/orders/{order_id}": "view_costs-null",
    "PATCH /api/products/{id}": "view_costs-null",
    "POST /api/materials": "view_costs-403",
    "POST /api/materials/{material_id}/adjust": "view_costs-403",
    "POST /api/materials/{material_id}/receipts": "view_costs-403",
    "POST /api/orders": "view_costs-null",
    "POST /api/orders/{order_id}/items": "revenue-only",
    "POST /api/orders/{order_id}/status": "view_costs-null",
    # STATEMENT-IMPORT: report is per-order fees + cost totals end to end, so the
    # endpoint carries require_capability(VIEW_COSTS) directly (not the router —
    # POST /api/imports/etsy returns only counts and keeps its role-only gate).
    "POST /api/imports/etsy-statement": "view_costs-403",
    "POST /api/overhead-materials/{overhead_id}/receipts": "view_costs-403",
    "POST /api/products/{id}/image": "view_costs-null",
    "POST /api/products/{id}/image/from-shopify": "view_costs-null",
    "POST /api/shops/{shop_id}/partner-payouts/payments": "view_finance",
    # PARTNER-CONFIG-1: the preview's term table itemises the PROFIT base, which
    # includes cogs / fees / allocated overhead. Those terms are stripped for a
    # caller without VIEW_COSTS by _strip_cost_terms, mirroring the finance page.
    "POST /api/shops/{shop_id}/partner-payouts/preview": "view_finance,view_costs-strip",
    "POST /api/shops/{shop_id}/partner-payouts/settlements": "view_finance",
    "POST /api/shops/{shop_id}/products": "view_costs-null",
    "PUT /api/products/{id}/bom": "view_costs-null",
}


# ── Introspection ──────────────────────────────────────────

def _numeric_field_names(model: type, seen: set) -> set[str]:
    """Recursively collect float/Decimal field names on a Pydantic model and its
    nested models."""
    names: set[str] = set()
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        return names
    if model in seen:
        return names
    seen.add(model)
    for name, field in model.model_fields.items():
        collected: list = []

        def rec(t):
            collected.append(t)
            for a in typing.get_args(t):
                rec(a)

        rec(field.annotation)
        if any(t in (float, decimal.Decimal) for t in collected):
            names.add(name)
        for t in collected:
            names |= _numeric_field_names(t, seen)
    return names


def _response_models():
    for r in main.app.routes:
        if isinstance(r, APIRoute) and r.response_model is not None:
            rm = r.response_model
            for m in [rm, *typing.get_args(rm)]:
                if isinstance(m, type) and issubclass(m, BaseModel):
                    yield r, m


def _all_numeric_field_names() -> set[str]:
    names: set[str] = set()
    for _route, model in _response_models():
        names |= _numeric_field_names(model, set())
    return names


def _money_routes() -> dict[str, list[str]]:
    """Route key → sorted non-neutral money field names it exposes."""
    out: dict[str, set[str]] = {}
    for r, model in _response_models():
        money = {
            n
            for n in _numeric_field_names(model, set())
            if MONEY_FIELD_CLASSIFICATION.get(n) in NON_NEUTRAL
        }
        if money:
            for meth in r.methods - {"HEAD", "OPTIONS"}:
                out.setdefault(f"{meth} {r.path}", set()).update(money)
    return {k: sorted(v) for k, v in out.items()}


# ── Tests ──────────────────────────────────────────────────

def test_every_numeric_response_field_is_classified():
    live = _all_numeric_field_names()
    unclassified = live - set(MONEY_FIELD_CLASSIFICATION)
    assert not unclassified, (
        "New numeric response field(s) unclassified in "
        f"MONEY_FIELD_CLASSIFICATION: {sorted(unclassified)}. Classify each as "
        "revenue / cost / margin / money / neutral (LEAK 2 was exactly an "
        "unclassified cost field)."
    )


def test_no_stale_field_classifications():
    live = _all_numeric_field_names()
    stale = set(MONEY_FIELD_CLASSIFICATION) - live
    assert not stale, (
        f"MONEY_FIELD_CLASSIFICATION lists fields no longer present: {sorted(stale)}"
    )


def test_every_money_route_is_classified():
    live = set(_money_routes())
    unclassified = live - set(MONEY_SURFACE_ENFORCEMENT)
    assert not unclassified, (
        "New money route(s) unclassified in MONEY_SURFACE_ENFORCEMENT: "
        f"{sorted(unclassified)}. Add a verdict and enforce it."
    )


def test_no_stale_route_classifications():
    live = set(_money_routes())
    stale = set(MONEY_SURFACE_ENFORCEMENT) - live
    assert not stale, (
        f"MONEY_SURFACE_ENFORCEMENT lists routes that no longer exist: {sorted(stale)}"
    )


def test_cost_fields_only_on_cost_gated_routes():
    """Any route exposing a `cost`-classified field must be gated by view_costs
    (null or 403). This is the LEAK 1 guard: a cost field on a route whose
    verdict is merely view_finance / revenue-only would fail here."""
    offenders = []
    for route, fields in _money_routes().items():
        cost_fields = [f for f in fields if MONEY_FIELD_CLASSIFICATION[f] == "cost"]
        if cost_fields and "view_costs" not in MONEY_SURFACE_ENFORCEMENT[route]:
            offenders.append((route, cost_fields, MONEY_SURFACE_ENFORCEMENT[route]))
    assert not offenders, (
        f"Cost fields exposed on routes not gated by view_costs: {offenders}"
    )


def test_order_cost_fields_match_censor_set():
    """The cost-classified float fields on OrderResponse must be exactly
    ORDER_COST_FIELDS — so a new per-order cost field cannot be added without
    extending the shared censor helper (the direct LEAK 2 guard)."""
    order_numeric = _numeric_field_names(OrderResponse, set())
    order_cost_fields = {
        n for n in order_numeric if MONEY_FIELD_CLASSIFICATION.get(n) == "cost"
    }
    assert order_cost_fields == set(ORDER_COST_FIELDS), (
        f"OrderResponse cost fields {sorted(order_cost_fields)} != "
        f"ORDER_COST_FIELDS {sorted(ORDER_COST_FIELDS)} — extend the censor set."
    )

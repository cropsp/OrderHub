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
    # cost (itemised)
    "production_cost": "cost",
    "shipping_np_cost": "cost",
    "platform_fee": "cost",
    "computed_production_cost": "cost",
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
    "base_amount": "money",
    "computed_amount": "money",
    "paid_amount": "money",
    "total_paid": "money",
    "total_settled": "money",
    # neutral (not money)
    "change_percent": "neutral",
    "percent": "neutral",
    "waste_percent": "neutral",
    "qty": "neutral",
    "qty_per_unit": "neutral",
    "delta": "neutral",
    "stock_quantity": "neutral",
    "low_stock_threshold": "neutral",
    "np_default_volume_m3": "neutral",
    "np_default_weight_kg": "neutral",
    "total_volume_cm3": "neutral",
    "volume_cm3": "neutral",
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
    "GET /api/products/{id}/bom": "view_costs-null",
    "GET /api/products/{id}/bom/cost": "view_costs-403",
    "GET /api/shops/{shop_id}/finance": "view_finance,view_costs-strip",
    "GET /api/shops/{shop_id}/partner-payouts/balances": "view_finance",
    "GET /api/shops/{shop_id}/partner-payouts/payments": "view_finance",
    "GET /api/shops/{shop_id}/partner-payouts/settlements": "view_finance",
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
    "POST /api/overhead-materials/{overhead_id}/receipts": "view_costs-403",
    "POST /api/products/{id}/image": "view_costs-null",
    "POST /api/products/{id}/image/from-shopify": "view_costs-null",
    "POST /api/shops/{shop_id}/partner-payouts/payments": "view_finance",
    "POST /api/shops/{shop_id}/partner-payouts/preview": "view_finance",
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

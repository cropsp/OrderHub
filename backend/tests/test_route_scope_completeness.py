"""USER-ACCESS-1 (OQ-5) — enforcement-completeness guard.

The sprint's main risk is a shop-scoped endpoint slipping through unguarded. This
test enumerates every registered route carrying `{shop_id}` in its path and
asserts each is consciously classified (guarded / owner-only / deliberately
unscoped). A newly added `{shop_id}` route that nobody classified FAILS here,
forcing a decision instead of silently reopening the hole.

Indirect shop resolution (order-id / product-id / attachment-id routes) cannot be
detected from the path; those are covered by the behavioural 403 tests in
test_shop_access.py and are listed in INDIRECT_SHOP_ROUTES below for the record.
"""
import main
from fastapi.routing import APIRoute


def _shop_id_routes() -> set[str]:
    routes = set()
    for r in main.app.routes:
        if isinstance(r, APIRoute) and "{shop_id}" in r.path:
            for m in r.methods - {"HEAD", "OPTIONS"}:
                routes.add(f"{m} {r.path}")
    return routes


# Every {shop_id} route must appear here with an explicit verdict.
#   guarded     → enforces per-user shop access (assert_shop_access /
#                 get_shop_for_user / require_shop_access).
#   owner-only  → mutation restricted to OWNER (unrestricted); no scoped user can
#                 reach it, so shop scoping is unnecessary.
#   unscoped:*  → deliberately not user-scoped, with reason.
CLASSIFIED: dict[str, str] = {
    "GET /api/shops/{shop_id}": "guarded",
    "PATCH /api/shops/{shop_id}": "owner-only",
    "DELETE /api/shops/{shop_id}": "owner-only",
    "POST /api/shops/{shop_id}/sync": "guarded",
    "POST /api/shops/{shop_id}/backfill": "guarded",
    "POST /api/shops/{shop_id}/backfill-refunds": "guarded",
    "POST /api/shops/{shop_id}/backfill-order-numbers": "guarded",
    "POST /api/shops/{shop_id}/backfill-product-images": "guarded",
    # SHOP-FEE-1: OWNER-only unlike the sibling backfills — it writes
    # platform_fee (a FINANCIAL_FIELDS column, owner-gated on the update path)
    # and moves every future partner-payout base.
    "POST /api/shops/{shop_id}/backfill-platform-fees": "owner-only",
    "GET /api/shops/{shop_id}/finance": "guarded",
    "GET /api/shops/{shop_id}/products": "guarded",
    "POST /api/shops/{shop_id}/products": "guarded",
    "POST /api/shops/{shop_id}/products/bulk-csv/preview": "guarded",
    "POST /api/shops/{shop_id}/products/bulk-csv/confirm": "guarded",
    "POST /api/shops/{shop_id}/partner-payouts/preview": "guarded",
    "POST /api/shops/{shop_id}/partner-payouts/settlements": "guarded",
    "GET /api/shops/{shop_id}/partner-payouts/settlements": "guarded",
    "DELETE /api/shops/{shop_id}/partner-payouts/settlements/{settlement_id}": "guarded",
    "POST /api/shops/{shop_id}/partner-payouts/payments": "guarded",
    "GET /api/shops/{shop_id}/partner-payouts/payments": "guarded",
    "DELETE /api/shops/{shop_id}/partner-payouts/payments/{payment_id}": "guarded",
    "GET /api/shops/{shop_id}/partner-payouts/balances": "guarded",
    "GET /api/shops/{shop_id}/partner-payouts/partner-names": "guarded",
    # HMAC-authenticated Shopify callback — no user principal, verified by the
    # shop's webhook secret, not by user shop access.
    "POST /api/webhooks/shopify/{shop_id}": "unscoped:webhook",
}

# For the record — shop-scoped surfaces whose shop is resolved indirectly (no
# {shop_id} in the path). Behavioural coverage lives in test_shop_access.py.
INDIRECT_SHOP_ROUTES = {
    "GET /api/orders/{order_id}",
    "PATCH /api/orders/{order_id}",
    "POST /api/orders/{order_id}/status",
    "GET /api/products/{id}",
    "PUT /api/products/{id}/bom",
    "POST /api/attachments/order/{order_id}",
    "POST /api/shipping/np-ttn/{order_id}",
    # Both import endpoints take shop_id as a multipart FORM field, so no
    # {shop_id} appears in the path; each calls assert_shop_access before
    # touching the shop (routers/imports.py `_get_etsy_shop`).
    "POST /api/imports/etsy",
    "POST /api/imports/etsy-statement",
}


def test_every_shop_id_route_is_classified():
    live = _shop_id_routes()
    unclassified = live - set(CLASSIFIED)
    assert not unclassified, (
        "New {shop_id} route(s) are not classified in "
        f"test_route_scope_completeness.CLASSIFIED: {sorted(unclassified)}. "
        "Add a verdict (guarded / owner-only / unscoped:<reason>) and enforce it."
    )


def test_no_stale_classified_entries():
    live = _shop_id_routes()
    stale = set(CLASSIFIED) - live
    assert not stale, f"CLASSIFIED lists routes that no longer exist: {sorted(stale)}"

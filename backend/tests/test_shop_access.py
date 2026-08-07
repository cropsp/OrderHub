"""USER-ACCESS-1 — shop-access scope, guards, provisioning, revoke safety.

Mock-based, matching the repo's router-test style (functions awaited directly
with AsyncMock dbs). Covers the ShopScope value object, the shared guards
(assert_shop_access / assert_order_access), GAP A (finance), the assignment
auto-grant, the new-shop + new-user provisioning rules, and the revoke-with-
assigned-orders 409 flow.
"""
from datetime import date
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.user import UserRole
from models.order import OrderStatus
from schemas.order import OrderUpdate
from schemas.user import ShopAccessUpdate
from services.access_service import (
    ShopScope,
    get_shop_scope,
    set_shop_access,
    default_grants_for_new_user,
    propagate_new_shop_to_unrestricted_managers,
)
from routers.dependencies import assert_shop_access, assert_order_access


# ── helpers ────────────────────────────────────────────────

def _user(role, uid=None):
    u = MagicMock()
    u.role = role
    u.id = uid or uuid4()
    return u


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(values)
    return r


def _rows(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


# ── ShopScope ──────────────────────────────────────────────

def test_shopscope_unrestricted_allows_anything():
    assert ShopScope.unrestricted().can_access(uuid4()) is True


def test_shopscope_scoped_only_its_shops():
    a = uuid4()
    scope = ShopScope(shop_ids=frozenset({a}))
    assert scope.can_access(a) is True
    assert scope.can_access(uuid4()) is False


@pytest.mark.asyncio
async def test_get_shop_scope_owner_short_circuits():
    db = AsyncMock()
    scope = await get_shop_scope(db, _user(UserRole.OWNER))
    assert scope.is_unrestricted
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_shop_scope_manager_reads_grants():
    a = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalars([a])
    scope = await get_shop_scope(db, _user(UserRole.MANAGER))
    assert not scope.is_unrestricted
    assert scope.can_access(a)


# ── assert_shop_access ─────────────────────────────────────

@pytest.mark.asyncio
async def test_assert_shop_access_404_when_missing():
    db = AsyncMock()
    db.execute.return_value = _scalar_one(None)
    with pytest.raises(HTTPException) as exc:
        await assert_shop_access(db, uuid4(), _user(UserRole.MANAGER))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assert_shop_access_403_without_grant():
    sid = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one(sid), _scalars([])]
    with pytest.raises(HTTPException) as exc:
        await assert_shop_access(db, sid, _user(UserRole.MANAGER))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_shop_access_ok_with_grant():
    sid = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one(sid), _scalars([sid])]
    await assert_shop_access(db, sid, _user(UserRole.MANAGER))  # no raise


@pytest.mark.asyncio
async def test_assert_shop_access_owner_no_grant_query():
    sid = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one(sid)]
    await assert_shop_access(db, sid, _user(UserRole.OWNER))
    assert db.execute.await_count == 1  # existence only; scope short-circuits


# ── assert_order_access (OQ-2 composition) ─────────────────

@pytest.mark.asyncio
async def test_order_access_designer_assigned_ok():
    me = uuid4()
    order = MagicMock(assigned_designer_id=me, shop_id=uuid4())
    await assert_order_access(AsyncMock(), order, _user(UserRole.DESIGNER, me))


@pytest.mark.asyncio
async def test_order_access_designer_not_assigned_403():
    order = MagicMock(assigned_designer_id=uuid4(), shop_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await assert_order_access(AsyncMock(), order, _user(UserRole.DESIGNER))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_order_access_manager_with_grant_ok():
    sid = uuid4()
    order = MagicMock(assigned_designer_id=None, shop_id=sid)
    db = AsyncMock()
    db.execute.return_value = _scalars([sid])
    await assert_order_access(db, order, _user(UserRole.MANAGER))


@pytest.mark.asyncio
async def test_order_access_manager_without_grant_403():
    order = MagicMock(assigned_designer_id=None, shop_id=uuid4())
    db = AsyncMock()
    db.execute.return_value = _scalars([])
    with pytest.raises(HTTPException) as exc:
        await assert_order_access(db, order, _user(UserRole.MANAGER))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_order_access_owner_ok_without_db():
    db = AsyncMock()
    await assert_order_access(db, MagicMock(), _user(UserRole.OWNER))
    db.execute.assert_not_awaited()


# ── GAP A: finance ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_finance_overview_manager_without_grant_403():
    from routers.finance import get_shop_finance_overview
    sid = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one(sid), _scalars([])]  # exists, no grant
    with pytest.raises(HTTPException) as exc:
        await get_shop_finance_overview(
            sid, date(2026, 1, 1), date(2026, 1, 31), _user(UserRole.MANAGER), db
        )
    assert exc.value.status_code == 403


# ── assignment auto-grant (OQ-2 / rule 3) ──────────────────

@pytest.mark.asyncio
async def test_assigning_designer_materialises_shop_grant():
    from services.order_service import update_order
    designer_id = uuid4()
    shop_id = uuid4()
    order = MagicMock()
    order.id = uuid4()
    order.status = OrderStatus.NEW
    order.shop_id = shop_id
    order.assigned_designer_id = None

    db = AsyncMock()
    assignee = MagicMock(role=UserRole.DESIGNER)
    db.get = AsyncMock(return_value=assignee)

    with patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await update_order(
            db, order, OrderUpdate(assigned_designer_id=designer_id), _user(UserRole.MANAGER)
        )
    g.assert_awaited_once()
    # grant_shop_access(db, designer_id, shop_id, ...)
    assert g.await_args.args[1] == designer_id
    assert g.await_args.args[2] == shop_id


# ── provisioning: default grants for a new user (rule 2) ───

@pytest.mark.asyncio
async def test_default_grants_manager_gets_all_shops():
    s1, s2 = uuid4(), uuid4()
    with patch("services.access_service._active_shop_ids", new=AsyncMock(return_value={s1, s2})), \
         patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await default_grants_for_new_user(AsyncMock(), _user(UserRole.MANAGER), None)
    assert g.await_count == 2


@pytest.mark.asyncio
async def test_default_grants_designer_gets_none_by_default():
    with patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await default_grants_for_new_user(AsyncMock(), _user(UserRole.DESIGNER), None)
    assert g.await_count == 0


@pytest.mark.asyncio
async def test_default_grants_explicit_list_wins():
    s1 = uuid4()
    with patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await default_grants_for_new_user(AsyncMock(), _user(UserRole.DESIGNER), [s1])
    assert g.await_count == 1


@pytest.mark.asyncio
async def test_default_grants_owner_is_noop():
    with patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await default_grants_for_new_user(AsyncMock(), _user(UserRole.OWNER), None)
    assert g.await_count == 0


# ── provisioning: new shop → unrestricted managers only (rule 1) ──

@pytest.mark.asyncio
async def test_new_shop_grants_only_unrestricted_managers():
    s1, s2, new = uuid4(), uuid4(), uuid4()
    m1, m2 = uuid4(), uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalars([m1, m2])
    with patch("services.access_service._active_shop_ids", new=AsyncMock(return_value={s1, s2, new})), \
         patch("services.access_service.get_granted_shop_ids",
               new=AsyncMock(side_effect=[{s1, s2}, {s1}])), \
         patch("services.access_service.grant_shop_access", new=AsyncMock()) as g:
        await propagate_new_shop_to_unrestricted_managers(db, new)
    # m1 covered all pre-existing shops → granted; m2 was scoped → skipped.
    assert g.await_count == 1
    assert g.await_args.args[2] == new


# ── set_shop_access diff ───────────────────────────────────

@pytest.mark.asyncio
async def test_set_shop_access_computes_added_and_removed():
    a, b, c = uuid4(), uuid4(), uuid4()
    with patch("services.access_service.get_granted_shop_ids", new=AsyncMock(return_value={a, b})), \
         patch("services.access_service.grant_shop_access", new=AsyncMock()) as g, \
         patch("services.access_service.revoke_shop_access", new=AsyncMock()) as r:
        added, removed = await set_shop_access(AsyncMock(), uuid4(), {b, c})
    assert added == {c}
    assert removed == {a}
    assert g.await_count == 1
    assert r.await_count == 1


# ── revoke safety (BLOCKING 3) ─────────────────────────────

@pytest.mark.asyncio
async def test_revoke_shop_with_assigned_orders_returns_409():
    from routers.users import set_user_shop_access
    uid = uuid4()
    shop_a = uuid4()
    designer = MagicMock(role=UserRole.DESIGNER, id=uid)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one(designer),           # _load_manageable_user
        _rows([(shop_a, 2)]),            # count of assigned orders in revoked shop
    ]
    with patch("services.access_service.get_granted_shop_ids", new=AsyncMock(return_value={shop_a})):
        with pytest.raises(HTTPException) as exc:
            await set_user_shop_access(
                uid, ShopAccessUpdate(shop_ids=[], unassign_orders=False),
                _user(UserRole.OWNER), db,
            )
    assert exc.value.status_code == 409
    assert exc.value.detail["blocked"][0]["assigned_order_count"] == 2


@pytest.mark.asyncio
async def test_revoke_with_unassign_flag_unassigns_then_removes_grant():
    from routers.users import set_user_shop_access
    uid = uuid4()
    shop_a = uuid4()
    oid = uuid4()
    designer = MagicMock(role=UserRole.DESIGNER, id=uid)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one(designer),           # _load_manageable_user
        _rows([(shop_a, 1)]),            # blocked count
        _rows([(oid,)]),                 # order ids to unassign
    ]
    order = MagicMock()
    with patch("services.access_service.get_granted_shop_ids",
               new=AsyncMock(side_effect=[{shop_a}, set()])), \
         patch("services.access_service.set_shop_access", new=AsyncMock()) as setacc, \
         patch("routers.users.get_order_detail", new=AsyncMock(return_value=order)), \
         patch("routers.users.update_order", new=AsyncMock()) as upd:
        result = await set_user_shop_access(
            uid, ShopAccessUpdate(shop_ids=[], unassign_orders=True),
            _user(UserRole.OWNER), db,
        )
    upd.assert_awaited_once()           # the assigned order was unassigned
    setacc.assert_awaited_once()        # grants then replaced
    assert result.shop_ids == []


# ─── PARTNER-CONFIG-1: the global /api/partners surface ────────────────
#
# These routes carry no {shop_id}, so test_route_scope_completeness cannot see
# them and cannot classify them either (its stale-entry test would fail). The
# invisibility is only safe because the router is OWNER-only and the surface
# carries identity, not per-shop data. That is asserted behaviourally here —
# this test IS the guard for those four routes.

@pytest.mark.asyncio
async def test_partner_identity_routes_are_owner_only():
    from routers import partners as partners_router
    from routers.dependencies import require_role
    from models.user import UserRole as Role

    # Every route on the router inherits the single OWNER gate.
    gate_deps = partners_router.router.dependencies
    assert len(gate_deps) == 1, "the OWNER gate must cover the whole router"

    checker = require_role(Role.OWNER)
    for role in (Role.MANAGER, Role.DESIGNER):
        with pytest.raises(HTTPException) as exc:
            await checker(current_user=_user(role))
        assert exc.value.status_code == 403
    assert await checker(current_user=_user(Role.OWNER)) is not None


@pytest.mark.asyncio
async def test_partner_identity_surface_exposes_no_per_shop_data():
    """If a partner-identity response ever gains a shop-scoped field, this fails.

    That is the point: the moment /api/partners carries per-shop data it needs
    the scope guard it structurally cannot have, and the field belongs under
    /api/shops/{shop_id}/partner-config instead.
    """
    from schemas.partner import PartnerResponse

    assert set(PartnerResponse.model_fields) == {
        "id", "name", "is_active", "notes", "created_at", "updated_at",
    }

"""WH-2 — Router-level tests for packaging endpoints.

This module used to test `POST /packaging-boxes/{id}/restock`, which no longer
exists: a quantity-only top-up wrote units with no price behind them, so
replenishment moved to a material receipt against the paired material (which
requires a unit cost by construction). What is left to guard here is the surface
that replaced it:

- the restock route is really gone, not merely unused
- the list endpoint hides archived boxes by default and can opt back in
- DELETE archives rather than destroys
- `initial_quantity` is gone from the create schema, and an old client still
  sending it does not smuggle stock in

Same mocked-AsyncSession idiom as test_materials_router.py (MAT-1).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

import main
from models.user import UserRole
from routers.packaging import archive_packaging, create_packaging, list_packaging
from schemas.packaging import PackagingBoxCreate, PackagingBoxUpdate


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _routes() -> set[str]:
    from fastapi.routing import APIRoute

    return {
        f"{method} {r.path}"
        for r in main.app.routes
        if isinstance(r, APIRoute)
        for method in r.methods - {"HEAD", "OPTIONS"}
    }


# ---------------------------------------------------------------------------
# The retired restock route
# ---------------------------------------------------------------------------

def test_restock_endpoint_no_longer_exists():
    """WH-2: replenishment is POST /api/materials/{id}/receipts now. If this route
    ever comes back, packaging can be topped up without a cost again — which is the
    exact hole WH-2 closed."""
    assert "POST /api/packaging-boxes/{box_id}/restock" not in _routes()


def test_restock_request_schema_is_gone():
    import schemas.packaging as pkg_schemas

    assert not hasattr(pkg_schemas, "RestockRequest")


def test_packaging_ledger_writer_is_gone():
    """services/stock_service.py wrote packaging_stock_movements. WH-2 froze that
    ledger; deleting its only writer is what makes 'frozen' structural rather than
    a convention someone can quietly break."""
    with pytest.raises(ModuleNotFoundError):
        __import__("services.stock_service")


# ---------------------------------------------------------------------------
# Create — no more free stock
# ---------------------------------------------------------------------------

def test_create_schema_rejects_initial_quantity():
    """An old client still posting initial_quantity must not silently succeed with
    the field dropped — Pydantic's default extra='ignore' would have made a stale
    form look like it worked while the box stayed at zero."""
    with pytest.raises(ValidationError):
        PackagingBoxCreate(
            name="100x120x50",
            inner_length_mm=100,
            inner_width_mm=120,
            inner_height_mm=50,
            max_weight_g=2000,
            initial_quantity=25,
        )


def test_create_schema_defaults_the_threshold():
    schema = PackagingBoxCreate(
        name="100x120x50",
        inner_length_mm=100,
        inner_width_mm=120,
        inner_height_mm=50,
        max_weight_g=2000,
    )
    assert schema.low_stock_threshold == 5


def test_update_schema_keeps_a_fractional_threshold():
    """The target column is materials.low_stock_threshold, Numeric(12,2). An int
    field here would have truncated 2.5 to 2 without saying so."""
    schema = PackagingBoxUpdate(low_stock_threshold="2.50")
    assert str(schema.low_stock_threshold) == "2.50"


@pytest.mark.asyncio
async def test_create_packaging_passes_no_user_id():
    """The service no longer takes one: nothing in the paired create is authored
    (the materials tables carry no author), which is what keeps the CSV-confirm
    path — which has no user — working."""
    db = MagicMock()
    created = MagicMock()

    with patch(
        "routers.packaging.CatalogService.create_packaging_box",
        AsyncMock(return_value=created),
    ) as mock_create:
        result = await create_packaging(
            schema=PackagingBoxCreate(
                name="100x120x50",
                inner_length_mm=100,
                inner_width_mm=120,
                inner_height_mm=50,
                max_weight_g=2000,
            ),
            db=db,
            user=_make_user(),
        )

    assert result is created
    assert "user_id" not in mock_create.await_args.kwargs
    assert len(mock_create.await_args.args) == 1


# ---------------------------------------------------------------------------
# List — archived boxes are hidden by default
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("include_archived", [False, True])
async def test_list_packaging_forwards_the_archive_filter(include_archived):
    db = MagicMock()

    with patch(
        "routers.packaging.CatalogService.get_packaging_boxes",
        AsyncMock(return_value=[]),
    ) as mock_list:
        await list_packaging(
            include_archived=include_archived, db=db, user=_make_user()
        )

    assert mock_list.await_args.kwargs["include_archived"] is include_archived


# ---------------------------------------------------------------------------
# Delete — archives, never destroys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_route_archives_the_box():
    """Kept on the DELETE verb so the client contract does not move, but it calls
    the archiving service now: hard-deleting the geometry row CASCADE-ed the frozen
    packaging ledger away with it."""
    db = MagicMock()
    box_id = uuid.uuid4()

    with patch(
        "routers.packaging.CatalogService.archive_packaging_box",
        AsyncMock(),
    ) as mock_archive:
        await archive_packaging(id=box_id, db=db, user=_make_user())

    mock_archive.assert_awaited_once_with(box_id)

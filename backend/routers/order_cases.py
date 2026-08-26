"""
OrderHub CRM — Order Cases Router (CASE-1)

Five routes, all OWNER/MANAGER. DESIGNER gets nothing in v1 (task rule 5): the
gate is on the router, so it applies to every route here including any added
later — the failure mode of per-route gating is the route someone forgets.

ACCESS COMPOSES IN TWO LAYERS, and both are load-bearing:

  1. `require_role(OWNER, MANAGER)` on the router — the ROLE gate.
  2. `assert_order_access` per order-scoped route — the SHOP-SCOPE gate, which
     resolves the shop through the order (task rule 6). No new scope concept.

Layer 2 alone would NOT be enough. `routers/dependencies.py:96-124` lets a
DESIGNER through for orders assigned to them — correct for the surfaces it was
written for, wrong here, and silently so. Layer 1 is what makes rule 5 true; the
DESIGNER branch of `assert_order_access` is unreachable from this router.

The dashboard route has no order in its path and therefore no layer 2. It filters
by `get_shop_scope` inside `order_case_service.list_open_for_user` instead — see
that docstring for why it does NOT copy the deliberately-unscoped stance of the
parcel-alerts endpoint it is otherwise modelled on.

Route classification for `tests/test_route_scope_completeness.py`: none of these
carry `{shop_id}`, so that test's path scan cannot see them and would stay green
by invisibility. They are listed in its `INDIRECT_SHOP_ROUTES` for the record,
and enforcement is proven behaviourally in `tests/test_shop_access.py`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.order import Order
from models.order_case import OrderCase, OrderCaseStatus
from models.user import User, UserRole
from routers.dependencies import assert_order_access, get_current_user, require_role
from schemas.order_case import (
    OpenCaseRow,
    OpenCasesResponse,
    OrderCaseCreate,
    OrderCaseNoteCreate,
    OrderCaseNoteResponse,
    OrderCaseResponse,
    OrderCaseUpdate,
)
from services import order_case_service
from logger import get_logger

logger = get_logger("routers.order_cases")


router = APIRouter(
    prefix="/api/cases",
    tags=["cases"],
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.MANAGER))],
)


def _serialise_case(case: OrderCase) -> OrderCaseResponse:
    """Attach display names the columns don't carry.

    Names are joined at read time rather than snapshotted onto the row — the
    `wb_parcel_alert` stance (`schemas/wb_alert.py:6-13`): a snapshot is a second
    copy that drifts the day someone is renamed.
    """
    return OrderCaseResponse(
        id=case.id,
        order_id=case.order_id,
        case_type=case.case_type,
        title=case.title,
        status=case.status,
        next_action=case.next_action,
        due_at=case.due_at,
        owner_id=case.owner_id,
        owner_name=case.owner.full_name if case.owner else None,
        created_by_id=case.created_by_id,
        created_by_name=case.created_by.full_name if case.created_by else None,
        resolved_at=case.resolved_at,
        resolution_note=case.resolution_note,
        created_at=case.created_at,
        updated_at=case.updated_at,
        notes=[
            OrderCaseNoteResponse(
                id=n.id,
                kind=n.kind,
                text=n.text,
                created_at=n.created_at,
                author_id=n.author_id,
                author_name=n.author.full_name if n.author else None,
            )
            for n in case.notes
        ],
    )


async def _load_order(db: AsyncSession, order_id: uuid.UUID) -> Order:
    order = (
        await db.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


async def _load_case_and_authorise(
    db: AsyncSession, case_id: uuid.UUID, current_user: User
) -> OrderCase:
    """Fetch a case and run the shop-scope gate through its order.

    404 for a missing case; the order gate then decides 403. Doing the access
    check via the parent order rather than the case is what keeps "shop scope
    resolves through the order" a single rule instead of two.
    """
    case = await order_case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case {case_id}",
        )

    order = await _load_order(db, case.order_id)
    await assert_order_access(db, order, current_user)
    return case


# NOTE: declared before the parameterised paths so `/open` can never be read as
# a case id, whatever methods this router grows later.
@router.get("/open", response_model=OpenCasesResponse)
async def list_open_cases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-resolved cases for the dashboard block, split into the two groups it
    renders. Scoped to the caller's shops — see `list_open_for_user`.

    Resolved cases never appear here (task rule 9); they stay on the order card.
    A plain read, cheap enough for every dashboard load: no scheduler computes
    these, the query IS the definition of "open".
    """
    rows = await order_case_service.list_open_for_user(db, current_user)

    response = OpenCasesResponse()
    for case, order, customer, shop in rows:
        row = OpenCaseRow(
            id=case.id,
            order_id=case.order_id,
            case_type=case.case_type,
            title=case.title,
            status=case.status,
            next_action=case.next_action,
            due_at=case.due_at,
            owner_id=case.owner_id,
            owner_name=case.owner.full_name if case.owner else None,
            created_at=case.created_at,
            order_number=order.order_number,
            order_external_id=order.external_id,
            customer_name=customer.full_name if customer else None,
            shop_id=order.shop_id,
            shop_name=shop.name if shop else None,
        )
        if case.status == OrderCaseStatus.WAITING.value:
            response.waiting.append(row)
        else:
            response.in_progress.append(row)

    return response


@router.get("/order/{order_id}", response_model=list[OrderCaseResponse])
async def list_cases_for_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every case on this order, resolved included, newest first."""
    order = await _load_order(db, order_id)
    await assert_order_access(db, order, current_user)

    cases = await order_case_service.list_for_order(db, order_id)
    return [_serialise_case(c) for c in cases]


@router.post(
    "/order/{order_id}",
    response_model=OrderCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case_for_order(
    order_id: uuid.UUID,
    data: OrderCaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a case. Several per order is normal and deliberately unlimited."""
    order = await _load_order(db, order_id)
    await assert_order_access(db, order, current_user)

    case = await order_case_service.create_case(db, order, data, current_user)
    await db.commit()

    fresh = await order_case_service.get_case(db, case.id)
    logger.info(
        "CASE-1 case opened: %s type=%s order=%s by=%s",
        case.id, case.case_type, order.id, current_user.email,
    )
    return _serialise_case(fresh)


@router.patch("/{case_id}", response_model=OrderCaseResponse)
async def update_case(
    case_id: uuid.UUID,
    data: OrderCaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a case. A status change also appends its own timeline record — one
    transaction, so the two cannot come apart."""
    case = await _load_case_and_authorise(db, case_id, current_user)

    await order_case_service.update_case(db, case, data, current_user)
    await db.commit()

    fresh = await order_case_service.get_case(db, case_id)
    return _serialise_case(fresh)


@router.post(
    "/{case_id}/notes",
    response_model=OrderCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_case_note(
    case_id: uuid.UUID,
    data: OrderCaseNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append to the timeline.

    Returns the whole case rather than the bare note: the caller is a timeline
    that has just changed, and one response beats a mutation plus a refetch.

    There is deliberately NO update and NO delete route for notes (task rule 2).
    `tests/test_order_cases.py` asserts that against the live route table, so
    adding one is a test failure rather than a review miss.
    """
    case = await _load_case_and_authorise(db, case_id, current_user)

    await order_case_service.add_note(db, case, data.text, current_user)
    await db.commit()

    fresh = await order_case_service.get_case(db, case_id)
    return _serialise_case(fresh)

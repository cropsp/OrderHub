"""
OrderHub CRM — Order Case Service (CASE-1)

Business logic for the per-order case tracker. Routes stay thin; the ordering
rule, the status-transition record and the shop-scope filter all live here,
beside each other, so there is one definition of each.

The transaction stance matches `order_service`: these functions `flush` but
never `commit` — the route owns the commit, which is what lets a status change
and its system note land atomically.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.customer import Customer
from models.order import Order
from models.order_case import (
    OrderCase,
    OrderCaseNote,
    OrderCaseNoteKind,
    OrderCaseStatus,
)
from models.shop import Shop
from models.user import User
from schemas.order_case import OrderCaseCreate, OrderCaseUpdate
from services.access_service import get_shop_scope

# Fields a PATCH may set directly. `status` is excluded on purpose — it goes
# through the transition path below, which also writes the timeline record.
_PLAIN_UPDATABLE = ("case_type", "title", "next_action", "due_at", "owner_id")

# Ukrainian labels for the system note. The timeline is read by managers, and
# "status → waiting" in English beside Ukrainian case titles reads like a leak
# of the schema into the UI.
_STATUS_LABELS = {
    OrderCaseStatus.IN_PROGRESS.value: "В роботі",
    OrderCaseStatus.WAITING.value: "Чекаємо",
    OrderCaseStatus.RESOLVED.value: "Вирішено",
}


def _status_label(value: str) -> str:
    # Falls back to the raw value rather than raising: the vocabulary is a
    # plain string column by design, and a label gap must not 500 a timeline.
    return _STATUS_LABELS.get(value, value)


async def list_for_order(db: AsyncSession, order_id: uuid.UUID) -> list[OrderCase]:
    """Every case on one order, resolved ones included.

    Resolved cases stay readable in the order card forever (task rule 9) — they
    are the record of what happened. Only the dashboard hides them.

    Newest first: the order card is read top-down when something is going on
    right now, not as a chronology.
    """
    result = await db.execute(
        select(OrderCase)
        .where(OrderCase.order_id == order_id)
        .options(selectinload(OrderCase.notes).selectinload(OrderCaseNote.author))
        .options(selectinload(OrderCase.owner), selectinload(OrderCase.created_by))
        .order_by(OrderCase.created_at.desc(), OrderCase.id.desc())
    )
    return list(result.scalars().all())


async def get_case(db: AsyncSession, case_id: uuid.UUID) -> OrderCase | None:
    result = await db.execute(
        select(OrderCase)
        .where(OrderCase.id == case_id)
        .options(selectinload(OrderCase.notes).selectinload(OrderCaseNote.author))
        .options(selectinload(OrderCase.owner), selectinload(OrderCase.created_by))
    )
    return result.scalar_one_or_none()


async def create_case(
    db: AsyncSession, order: Order, data: OrderCaseCreate, user: User
) -> OrderCase:
    """Open a case on an order.

    No opening system note. The case's own `created_at` and `created_by_id`
    already say who opened it and when; a note repeating that would be noise on
    every single timeline.
    """
    case = OrderCase(
        id=uuid.uuid4(),
        order_id=order.id,
        case_type=data.case_type.value,
        title=data.title,
        status=OrderCaseStatus.IN_PROGRESS.value,
        next_action=data.next_action,
        due_at=data.due_at,
        owner_id=data.owner_id,
        created_by_id=user.id,
    )
    db.add(case)
    await db.flush()
    return case


async def update_case(
    db: AsyncSession, case: OrderCase, data: OrderCaseUpdate, user: User
) -> OrderCase:
    """Patch a case; a status change also writes its own timeline record.

    Task rule 3: the transition must be visible in the timeline with author and
    timestamp. That is one `OrderCaseNote(kind='system')` added in THIS
    transaction, mirroring `order_service.change_order_status` where the history
    row is added before the flush — so a failed write cannot leave a status
    change unrecorded.

    Re-setting the same status is not a transition and writes nothing. Without
    that guard a double-clicked dropdown produces "Чекаємо → Чекаємо" rows,
    which is exactly the kind of noise that makes people stop reading a
    timeline.
    """
    fields = data.model_dump(exclude_unset=True)

    for name in _PLAIN_UPDATABLE:
        if name in fields:
            setattr(case, name, fields[name])

    new_status = fields.get("status")
    if new_status is not None:
        new_value = new_status.value if hasattr(new_status, "value") else new_status
        old_value = case.status

        if new_value != old_value:
            case.status = new_value

            if new_value == OrderCaseStatus.RESOLVED.value:
                case.resolved_at = datetime.now(timezone.utc)
                # Only meaningful at close, and only if one was supplied.
                if fields.get("resolution_note") is not None:
                    case.resolution_note = fields["resolution_note"]
            else:
                # Reopening. Clear both, or a reopened case keeps claiming it
                # was resolved on some date with some summary — the row would
                # contradict itself, and the dashboard shows it as open again.
                case.resolved_at = None
                case.resolution_note = None

            db.add(
                OrderCaseNote(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    kind=OrderCaseNoteKind.SYSTEM.value,
                    author_id=user.id,
                    text=f"Статус: {_status_label(old_value)} → {_status_label(new_value)}",
                )
            )
        elif (
            new_value == OrderCaseStatus.RESOLVED.value
            and fields.get("resolution_note") is not None
        ):
            # Already resolved, editing only the summary. Not a transition.
            case.resolution_note = fields["resolution_note"]

    await db.flush()
    return case


async def add_note(
    db: AsyncSession, case: OrderCase, text: str, user: User
) -> OrderCaseNote:
    """Append a human comment. Always `kind='comment'` — the wire cannot set it
    (`OrderCaseNoteCreate` has no such field), so a client cannot forge a
    status-transition record."""
    note = OrderCaseNote(
        id=uuid.uuid4(),
        case_id=case.id,
        kind=OrderCaseNoteKind.COMMENT.value,
        author_id=user.id,
        text=text,
    )
    db.add(note)
    await db.flush()
    return note


async def list_open_for_user(
    db: AsyncSession, user: User
) -> list[tuple[OrderCase, Order, Customer | None, Shop | None]]:
    """Non-resolved cases across every order the caller is allowed to see.

    THE SHOP-SCOPE FILTER IS THE POINT OF THIS FUNCTION. The dashboard block it
    feeds is modelled on `ParcelAlertsCard`, whose endpoint is deliberately
    unscoped — `routers/westernbid.py:262-265`: parcels "are global, not
    shop-scoped". Cases are NOT: each belongs to an order, which belongs to a
    shop, and a MANAGER holds an explicit per-shop grant (USER-ACCESS-1). Copying
    the alerts endpoint's stance here would show a restricted manager the
    problem orders of shops they cannot open.

    OWNER short-circuits to unrestricted, same as everywhere else.

    Ordering: overdue first, then soonest deadline, then newest. Cases with no
    `due_at` sort last within their group — an undated case is by definition not
    late, and letting NULLs float to the top would push real deadlines down.
    """
    scope = await get_shop_scope(db, user)

    stmt = (
        select(OrderCase, Order, Customer, Shop)
        .join(Order, Order.id == OrderCase.order_id)
        .outerjoin(Customer, Customer.id == Order.customer_id)
        .outerjoin(Shop, Shop.id == Order.shop_id)
        .where(OrderCase.status != OrderCaseStatus.RESOLVED.value)
        .options(selectinload(OrderCase.owner), selectinload(OrderCase.created_by))
        .order_by(
            OrderCase.due_at.asc().nulls_last(),
            OrderCase.created_at.desc(),
        )
    )

    if not scope.is_unrestricted:
        if not scope.shop_ids:
            # No grants at all — an empty IN () is a query worth not sending.
            return []
        stmt = stmt.where(Order.shop_id.in_(scope.shop_ids))

    result = await db.execute(stmt)
    return [tuple(row) for row in result.all()]

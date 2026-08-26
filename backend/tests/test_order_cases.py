"""CASE-1 — per-order case tracker.

Mock-based, matching the repo's router-test style (functions awaited directly
with AsyncMock dbs; no live DB).

The behaviours worth pinning are the ones a future edit could quietly break:
the append-only guarantee, the status-transition record, and the fact that
resolving and reopening keep `resolved_at` / `resolution_note` honest. Access
enforcement lives in test_shop_access.py beside the other guards.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

import main
from models.order_case import OrderCaseNoteKind, OrderCaseStatus, OrderCaseType
from schemas.order_case import (
    OrderCaseCreate,
    OrderCaseNoteCreate,
    OrderCaseUpdate,
)
from services import order_case_service


# ── helpers ────────────────────────────────────────────────

def _user(uid=None, name="Оксана"):
    u = MagicMock()
    u.id = uid or uuid4()
    u.full_name = name
    u.email = "manager@orderhub.dev"
    return u


def _case(status=OrderCaseStatus.IN_PROGRESS.value, **kw):
    c = MagicMock()
    c.id = kw.get("id", uuid4())
    c.order_id = kw.get("order_id", uuid4())
    c.status = status
    c.resolved_at = kw.get("resolved_at")
    c.resolution_note = kw.get("resolution_note")
    return c


def _rows(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _scalars(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(values)
    return r


def _added(db):
    """Every object handed to db.add() during the call."""
    return [c.args[0] for c in db.add.call_args_list]


def _notes_added(db):
    from models.order_case import OrderCaseNote
    return [o for o in _added(db) if isinstance(o, OrderCaseNote)]


# ── create ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_case_starts_in_progress_and_records_author():
    db = AsyncMock()
    db.add = MagicMock()
    order = MagicMock(id=uuid4())
    user = _user()

    case = await order_case_service.create_case(
        db,
        order,
        OrderCaseCreate(case_type=OrderCaseType.RETURN, title="Повернулась"),
        user,
    )

    assert case.status == OrderCaseStatus.IN_PROGRESS.value
    assert case.case_type == "return"
    assert case.order_id == order.id
    assert case.created_by_id == user.id
    assert case.resolved_at is None


@pytest.mark.asyncio
async def test_create_case_writes_no_opening_note():
    """The case row already carries created_at + created_by. A note repeating
    that would be noise on every timeline."""
    db = AsyncMock()
    db.add = MagicMock()

    await order_case_service.create_case(
        db,
        MagicMock(id=uuid4()),
        OrderCaseCreate(case_type=OrderCaseType.REVIEW, title="1 зірка"),
        _user(),
    )

    assert _notes_added(db) == []


# ── status transitions (task rule 3) ───────────────────────

@pytest.mark.asyncio
async def test_status_change_appends_system_note_with_author():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case()
    user = _user()

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(status=OrderCaseStatus.WAITING), user
    )

    notes = _notes_added(db)
    assert len(notes) == 1
    assert notes[0].kind == OrderCaseNoteKind.SYSTEM.value
    # Rule 3: "with author + timestamp". The author is on the row; the
    # timestamp is the column default.
    assert notes[0].author_id == user.id
    assert "В роботі" in notes[0].text and "Чекаємо" in notes[0].text
    assert case.status == OrderCaseStatus.WAITING.value


@pytest.mark.asyncio
async def test_setting_the_same_status_is_not_a_transition():
    """A double-clicked dropdown must not produce "Чекаємо → Чекаємо" rows."""
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(status=OrderCaseStatus.WAITING.value)

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(status=OrderCaseStatus.WAITING), _user()
    )

    assert _notes_added(db) == []


@pytest.mark.asyncio
async def test_resolving_stamps_resolved_at_and_note():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case()

    await order_case_service.update_case(
        db,
        case,
        OrderCaseUpdate(
            status=OrderCaseStatus.RESOLVED, resolution_note="Переслали, отримав"
        ),
        _user(),
    )

    assert case.status == OrderCaseStatus.RESOLVED.value
    assert case.resolved_at is not None
    assert case.resolved_at.tzinfo is not None  # timezone-aware, not naive
    assert case.resolution_note == "Переслали, отримав"


@pytest.mark.asyncio
async def test_reopening_clears_resolution_so_the_row_cannot_contradict_itself():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(
        status=OrderCaseStatus.RESOLVED.value,
        resolved_at=datetime.now(timezone.utc),
        resolution_note="Переслали",
    )

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(status=OrderCaseStatus.IN_PROGRESS), _user()
    )

    assert case.status == OrderCaseStatus.IN_PROGRESS.value
    assert case.resolved_at is None
    assert case.resolution_note is None
    assert len(_notes_added(db)) == 1


@pytest.mark.asyncio
async def test_editing_resolution_note_on_a_resolved_case_is_not_a_transition():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(
        status=OrderCaseStatus.RESOLVED.value,
        resolved_at=datetime.now(timezone.utc),
        resolution_note="старе",
    )

    await order_case_service.update_case(
        db,
        case,
        OrderCaseUpdate(status=OrderCaseStatus.RESOLVED, resolution_note="нове"),
        _user(),
    )

    assert case.resolution_note == "нове"
    assert _notes_added(db) == []


@pytest.mark.asyncio
async def test_plain_field_edit_writes_no_note():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case()

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(next_action="Чекаємо адресу"), _user()
    )

    assert case.next_action == "Чекаємо адресу"
    assert _notes_added(db) == []


# ── notes are append-only (task rule 2) ────────────────────

@pytest.mark.asyncio
async def test_add_note_is_always_a_comment_never_a_system_row():
    db = AsyncMock()
    db.add = MagicMock()

    await order_case_service.add_note(db, _case(), "Написав клієнту", _user())

    notes = _notes_added(db)
    assert len(notes) == 1
    assert notes[0].kind == OrderCaseNoteKind.COMMENT.value


def test_note_create_schema_has_no_kind_field():
    """A client must not be able to forge a status-transition record."""
    assert "kind" not in OrderCaseNoteCreate.model_fields


def test_no_route_can_edit_or_delete_a_note():
    """Rule 2 asserted against the LIVE route table, so adding an edit/delete
    endpoint is a test failure rather than something review has to catch."""
    offenders = [
        f"{m} {r.path}"
        for r in main.app.routes
        if isinstance(r, APIRoute) and "notes" in r.path
        for m in r.methods - {"HEAD", "OPTIONS"}
        if m in {"PATCH", "PUT", "DELETE"}
    ]
    assert not offenders, f"Notes must be append-only; found: {offenders}"


# ── dashboard listing ──────────────────────────────────────

@pytest.mark.asyncio
async def test_open_list_owner_is_unrestricted_and_applies_no_shop_filter():
    from models.user import UserRole
    db = AsyncMock()
    db.execute.return_value = _rows([])
    owner = _user()
    owner.role = UserRole.OWNER

    await order_case_service.list_open_for_user(db, owner)

    # One query: the listing. get_shop_scope short-circuits without touching db.
    assert db.execute.await_count == 1
    sql = str(db.execute.await_args.args[0])
    assert "shop_id IN" not in sql


@pytest.mark.asyncio
async def test_open_list_manager_without_any_grant_returns_empty_without_querying():
    from models.user import UserRole
    db = AsyncMock()
    db.execute.return_value = _scalars([])  # get_shop_scope → no grants
    manager = _user()
    manager.role = UserRole.MANAGER

    result = await order_case_service.list_open_for_user(db, manager)

    assert result == []
    # Only the scope lookup ran — no point sending an empty IN ().
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_open_list_manager_filters_by_granted_shops():
    from models.user import UserRole
    shop_id = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [_scalars([shop_id]), _rows([])]
    manager = _user()
    manager.role = UserRole.MANAGER

    await order_case_service.list_open_for_user(db, manager)

    sql = str(db.execute.await_args_list[1].args[0])
    assert "shop_id IN" in sql


@pytest.mark.asyncio
async def test_open_list_excludes_resolved_cases():
    from models.user import UserRole
    db = AsyncMock()
    db.execute.return_value = _rows([])
    owner = _user()
    owner.role = UserRole.OWNER

    await order_case_service.list_open_for_user(db, owner)

    sql = str(db.execute.await_args.args[0])
    assert "status !=" in sql
    # Undated cases must sort last — an undated case is not late.
    assert "NULLS LAST" in sql.upper()


@pytest.mark.asyncio
async def test_open_route_splits_waiting_from_in_progress():
    from routers.order_cases import list_open_cases

    order = MagicMock(order_number="91890_1816", external_id="123", shop_id=uuid4())
    customer = MagicMock(full_name="Ivan")
    # `name=` is consumed by MagicMock's own constructor — set it after.
    shop = MagicMock()
    shop.name = "Lamamarka"

    working = _case(status=OrderCaseStatus.IN_PROGRESS.value)
    waiting = _case(status=OrderCaseStatus.WAITING.value)
    for c in (working, waiting):
        c.case_type = "return"
        c.title = "t"
        c.next_action = None
        c.due_at = None
        c.owner_id = None
        c.owner = None
        c.created_at = datetime.now(timezone.utc)

    with patch.object(
        order_case_service,
        "list_open_for_user",
        AsyncMock(return_value=[
            (working, order, customer, shop),
            (waiting, order, customer, shop),
        ]),
    ):
        result = await list_open_cases(_user(), AsyncMock())

    assert [r.id for r in result.in_progress] == [working.id]
    assert [r.id for r in result.waiting] == [waiting.id]


def test_dashboard_row_does_not_carry_note_timelines():
    """The block renders no notes; shipping every open case's whole timeline to
    every dashboard load would be pure waste."""
    from schemas.order_case import OpenCaseRow
    assert "notes" not in OpenCaseRow.model_fields


# ── ordering semantics the dashboard depends on ────────────

@pytest.mark.asyncio
async def test_overdue_sorts_before_a_later_deadline():
    """The service orders by due_at ASC, so a past deadline precedes a future
    one — that is the whole "overdue first" rule (task rule 4), and it is a
    query property rather than something the component re-derives."""
    from models.user import UserRole
    now = datetime.now(timezone.utc)
    overdue = _case()
    overdue.due_at = now - timedelta(days=2)
    later = _case()
    later.due_at = now + timedelta(days=5)

    db = AsyncMock()
    db.execute.return_value = _rows([])
    owner = _user()
    owner.role = UserRole.OWNER

    await order_case_service.list_open_for_user(db, owner)

    sql = str(db.execute.await_args.args[0])
    assert "ORDER BY" in sql.upper()
    assert "due_at ASC" in sql


# ── response bodies (CASE-1-fix) ───────────────────────────

@pytest.mark.asyncio
async def test_patch_response_carries_the_note_it_just_wrote():
    """THE STALE-TIMELINE TEST.

    A mutation response that omits the row it just created is a lie the UI then
    has to refetch its way out of. The shape reproduced here is the real one:
    the route loads the case (notes eagerly loaded), writes, commits, and
    re-queries — and because `expire_on_commit=False` the re-query returns the
    SAME identity-mapped instance. `get_case` is patched to return that instance
    both times, which is exactly what the identity map does; nothing else can
    make the collection correct except the write itself doing so.
    """
    from models.order_case import OrderCase
    from routers.order_cases import update_case as update_case_route

    user = _user()
    user.id = uuid4()
    case = OrderCase(
        id=uuid4(),
        order_id=uuid4(),
        case_type=OrderCaseType.RETURN.value,
        title="Повернулась до відправника",
        status=OrderCaseStatus.IN_PROGRESS.value,
        created_by_id=user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    case.notes = []          # loaded, and empty — the pre-write state
    case.owner = None
    case.created_by = None

    db = AsyncMock()
    db.add = MagicMock()

    with patch.object(
        order_case_service, "get_case", AsyncMock(return_value=case)
    ), patch(
        "routers.order_cases._load_order", AsyncMock(return_value=MagicMock())
    ), patch(
        "routers.order_cases.assert_order_access", AsyncMock()
    ):
        response = await update_case_route(
            case.id,
            OrderCaseUpdate(status=OrderCaseStatus.WAITING),
            user,
            db,
        )

    system_notes = [n for n in response.notes if n.kind == OrderCaseNoteKind.SYSTEM.value]
    assert len(system_notes) == 1
    assert "В роботі" in system_notes[0].text
    assert "Чекаємо" in system_notes[0].text
    assert system_notes[0].created_at is not None


@pytest.mark.asyncio
async def test_resolution_summary_is_appended_to_the_system_note():
    """Rule 5 (CASE-1-fix): the "why" lives in the append-only timeline too."""
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(status=OrderCaseStatus.WAITING.value)

    await order_case_service.update_case(
        db,
        case,
        OrderCaseUpdate(
            status=OrderCaseStatus.RESOLVED,
            resolution_note="Переслали, отримав",
        ),
        _user(),
    )

    note = _notes_added(db)[0]
    assert note.text == "Статус: Чекаємо → Вирішено — Переслали, отримав"
    # The column keeps its own copy — this duplicates the summary, not moves it.
    assert case.resolution_note == "Переслали, отримав"


@pytest.mark.asyncio
async def test_resolving_without_a_summary_keeps_the_bare_transition_text():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(status=OrderCaseStatus.WAITING.value)

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(status=OrderCaseStatus.RESOLVED), _user()
    )

    assert _notes_added(db)[0].text == "Статус: Чекаємо → Вирішено"


@pytest.mark.asyncio
async def test_a_whitespace_only_summary_does_not_dangle_a_dash():
    db = AsyncMock()
    db.add = MagicMock()
    case = _case(status=OrderCaseStatus.WAITING.value)

    await order_case_service.update_case(
        db, case, OrderCaseUpdate(status=OrderCaseStatus.RESOLVED, resolution_note="   "), _user()
    )

    assert _notes_added(db)[0].text == "Статус: Чекаємо → Вирішено"

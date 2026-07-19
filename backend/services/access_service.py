"""
OrderHub CRM — Shop Access Service (USER-ACCESS-1)

Single source of truth for the `user_shop_access` grant table and for resolving
a user's accessible-shop set. Every read/write of shop scoping goes through here
so there is exactly one place the rules live.

Design notes:
- OWNER is unrestricted by design (superuser) and never needs a grant row — the
  resolver short-circuits to ShopScope.unrestricted().
- The resolver returns an explicit ShopScope value object, never a None sentinel,
  so a missed access check cannot silently crash-or-deny (USER-ACCESS-1 SMALLER 4).
- Grant/revoke ops emit a structured audit log line. A persistent user-action
  audit *table* is deferred to USER-ACCESS-2 (no such table exists today).
- These functions flush but never commit — the calling router owns the commit,
  matching the order_service convention.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger
from models.shop import Shop
from models.user import User, UserRole
from models.user_shop_access import UserShopAccess

logger = get_logger("services.access")


@dataclass(frozen=True)
class ShopScope:
    """A user's resolved shop visibility.

    Use `can_access(shop_id)` rather than inspecting the fields directly — it is
    the one gate that correctly handles the unrestricted (OWNER) case.
    """

    is_unrestricted: bool = False
    shop_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    @classmethod
    def unrestricted(cls) -> "ShopScope":
        return cls(is_unrestricted=True, shop_ids=frozenset())

    def can_access(self, shop_id: uuid.UUID) -> bool:
        return self.is_unrestricted or shop_id in self.shop_ids


# ─── Resolve ───────────────────────────────────────────────

async def get_shop_scope(db: AsyncSession, user: User) -> ShopScope:
    """Resolve the caller's accessible-shop set.

    OWNER → unrestricted (no query). MANAGER/DESIGNER → their granted shop ids.
    """
    if user.role == UserRole.OWNER:
        return ShopScope.unrestricted()

    result = await db.execute(
        select(UserShopAccess.shop_id).where(UserShopAccess.user_id == user.id)
    )
    return ShopScope(shop_ids=frozenset(result.scalars().all()))


# ─── Mutate ────────────────────────────────────────────────

async def grant_shop_access(
    db: AsyncSession,
    user_id: uuid.UUID,
    shop_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    source: str = "manual",
) -> None:
    """Idempotently grant a user access to a shop (ON CONFLICT DO NOTHING)."""
    stmt = (
        pg_insert(UserShopAccess)
        .values(id=uuid.uuid4(), user_id=user_id, shop_id=shop_id)
        .on_conflict_do_nothing(constraint="uq_user_shop_access_user_shop")
    )
    await db.execute(stmt)
    logger.info(
        "[ACCESS] grant user=%s shop=%s actor=%s source=%s",
        user_id, shop_id, actor_id, source,
    )


async def revoke_shop_access(
    db: AsyncSession,
    user_id: uuid.UUID,
    shop_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Remove a user's grant for a shop (no-op if absent)."""
    await db.execute(
        delete(UserShopAccess).where(
            UserShopAccess.user_id == user_id,
            UserShopAccess.shop_id == shop_id,
        )
    )
    logger.info("[ACCESS] revoke user=%s shop=%s actor=%s", user_id, shop_id, actor_id)


async def get_granted_shop_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """The raw grant set for a user (independent of role — no OWNER short-circuit)."""
    result = await db.execute(
        select(UserShopAccess.shop_id).where(UserShopAccess.user_id == user_id)
    )
    return set(result.scalars().all())


async def set_shop_access(
    db: AsyncSession,
    user_id: uuid.UUID,
    shop_ids: set[uuid.UUID],
    *,
    actor_id: uuid.UUID | None = None,
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Replace a user's grant set with `shop_ids`.

    Returns (added, removed). Does NOT enforce the revoke-with-assigned-orders
    guard — that check lives in the users router, which needs order context.
    """
    current = await get_granted_shop_ids(db, user_id)
    added = shop_ids - current
    removed = current - shop_ids

    for shop_id in added:
        await grant_shop_access(db, user_id, shop_id, actor_id=actor_id, source="editor")
    for shop_id in removed:
        await revoke_shop_access(db, user_id, shop_id, actor_id=actor_id)

    return added, removed


# ─── Provisioning helpers ──────────────────────────────────

async def _active_shop_ids(db: AsyncSession) -> set[uuid.UUID]:
    result = await db.execute(select(Shop.id).where(Shop.is_active == True))  # noqa: E712
    return set(result.scalars().all())


async def default_grants_for_new_user(
    db: AsyncSession,
    user: User,
    shop_ids: list[uuid.UUID] | None = None,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Set a newly created user's shop access (USER-ACCESS-1 rule 2).

    Prevents the onboarding trap where a new MANAGER/DESIGNER sees nothing.
    - Explicit `shop_ids` given → grant exactly those (any non-OWNER role).
    - Omitted + MANAGER → all active shops (preserves today's "manager = all").
    - Omitted + DESIGNER → none (they also accrue grants on order assignment).
    - OWNER → no-op (unrestricted).
    """
    if user.role == UserRole.OWNER:
        return

    if shop_ids is None:
        grants = await _active_shop_ids(db) if user.role == UserRole.MANAGER else set()
    else:
        grants = set(shop_ids)

    for shop_id in grants:
        await grant_shop_access(
            db, user.id, shop_id, actor_id=actor_id, source="user-create"
        )


async def propagate_new_shop_to_unrestricted_managers(
    db: AsyncSession,
    new_shop_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Grant a newly created shop only to *effectively unrestricted* managers
    (USER-ACCESS-1 rule 1).

    A manager receives the new shop iff their current grant set already covered
    every pre-existing active shop. A deliberately-scoped manager stays scoped.
    Edge: with zero pre-existing shops, every manager (∅ ⊇ ∅) qualifies.
    """
    preexisting = await _active_shop_ids(db) - {new_shop_id}

    result = await db.execute(
        select(User.id).where(
            User.role == UserRole.MANAGER, User.is_active == True  # noqa: E712
        )
    )
    manager_ids = list(result.scalars().all())

    for manager_id in manager_ids:
        granted = await get_granted_shop_ids(db, manager_id)
        if preexisting <= granted:  # covered all pre-existing shops → unrestricted
            await grant_shop_access(
                db, manager_id, new_shop_id, actor_id=actor_id, source="shop-create"
            )

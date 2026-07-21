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
- Grant/revoke ops emit a structured audit log line AND a persistent row in the
  `access_audit` table (USER-ACCESS-2) — for both shop access and capabilities.
- These functions flush but never commit — the calling router owns the commit,
  matching the order_service convention.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from constants import SYSTEM_USER_ID
from logger import get_logger
from models.access_audit import AccessAudit
from models.shop import Shop
from models.user import Capability, User, UserRole
from models.user_capability import UserCapability
from models.user_shop_access import UserShopAccess

logger = get_logger("services.access")


# ─── Capability defaults ───────────────────────────────────
#
# USER-ACCESS-2 role defaults, applied when a user has no explicit override row.
# Deny-by-default for every non-owner role: restricting money visibility is the
# whole point, so a MANAGER/DESIGNER created after this sprint sees nothing
# financial until the OWNER grants it explicitly. Existing managers keep today's
# view_finance via an explicit backfill row (migration), NOT via this default.
# OWNER is never resolved through here — the resolver short-circuits.
ROLE_CAPABILITY_DEFAULTS: dict[UserRole, frozenset[Capability]] = {
    UserRole.MANAGER: frozenset(),
    UserRole.DESIGNER: frozenset(),
}


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


# ─── Capabilities (USER-ACCESS-2) ──────────────────────────

@dataclass(frozen=True)
class CapabilitySet:
    """A user's resolved money-visibility capabilities.

    Use `has(cap)` rather than inspecting fields directly — it is the one gate
    that correctly handles the unrestricted (OWNER) case. No None sentinels, same
    footgun rule as ShopScope: a missed check cannot silently crash-or-deny.
    """

    is_owner: bool = False
    granted: frozenset[Capability] = field(default_factory=frozenset)

    @classmethod
    def owner(cls) -> "CapabilitySet":
        return cls(is_owner=True, granted=frozenset(Capability))

    def has(self, cap: Capability) -> bool:
        return self.is_owner or cap in self.granted


async def get_capabilities(db: AsyncSession, user: User) -> CapabilitySet:
    """Resolve a user's capabilities: role default, overridden per explicit row.

    OWNER → every capability (no query). Otherwise start from the role default
    and let each explicit `user_capability` row win (granted=true adds, false
    removes) — so a permissive future default can still be revoked per user.
    """
    if user.role == UserRole.OWNER:
        return CapabilitySet.owner()

    resolved = set(ROLE_CAPABILITY_DEFAULTS.get(user.role, frozenset()))
    result = await db.execute(
        select(UserCapability.capability, UserCapability.granted).where(
            UserCapability.user_id == user.id
        )
    )
    for cap_name, granted in result.all():
        try:
            cap = Capability(cap_name)
        except ValueError:
            continue  # unknown/retired capability name — ignore defensively
        if granted:
            resolved.add(cap)
        else:
            resolved.discard(cap)
    return CapabilitySet(granted=frozenset(resolved))


async def set_capabilities(
    db: AsyncSession,
    user_id: uuid.UUID,
    values: dict[Capability, bool],
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Upsert explicit capability override rows for a user, auditing each change.

    Each entry writes (or updates) exactly one row and records an access-audit
    row. OWNER targets are a no-op decided by the caller (router) — this helper
    is unconditional. Flush-but-never-commit; the router owns the commit.
    """
    for cap, granted in values.items():
        stmt = (
            pg_insert(UserCapability)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                capability=cap.value,
                granted=granted,
            )
            .on_conflict_do_update(
                constraint="uq_user_capability_user_cap",
                set_={"granted": granted},
            )
        )
        await db.execute(stmt)
        await _write_access_audit(
            db,
            actor_id=actor_id,
            target_user_id=user_id,
            object_type="capability",
            object_id=cap.value,
            action="grant" if granted else "revoke",
            source="capability-editor",
        )
        logger.info(
            "[ACCESS] capability user=%s cap=%s granted=%s actor=%s",
            user_id, cap.value, granted, actor_id,
        )


# ─── Access audit (USER-ACCESS-2) ──────────────────────────

async def _write_access_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    target_user_id: uuid.UUID,
    object_type: str,
    object_id: object,
    action: str,
    source: str,
) -> None:
    """Append one persistent access-audit row. Non-human writes (assignment
    hook, shop-create propagation) fall back to SYSTEM_USER_ID as the actor."""
    db.add(
        AccessAudit(
            id=uuid.uuid4(),
            actor_id=actor_id or SYSTEM_USER_ID,
            target_user_id=target_user_id,
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            source=source,
        )
    )


# ─── Mutate ────────────────────────────────────────────────

async def grant_shop_access(
    db: AsyncSession,
    user_id: uuid.UUID,
    shop_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    source: str = "manual",
) -> None:
    """Idempotently grant a user access to a shop (ON CONFLICT DO NOTHING).

    Only a grant that actually inserts a row is audited — an idempotent no-op
    (e.g. the assignment hook re-granting an existing shop) writes nothing, so
    the audit trail stays free of noise.
    """
    stmt = (
        pg_insert(UserShopAccess)
        .values(id=uuid.uuid4(), user_id=user_id, shop_id=shop_id)
        .on_conflict_do_nothing(constraint="uq_user_shop_access_user_shop")
    )
    result = await db.execute(stmt)
    logger.info(
        "[ACCESS] grant user=%s shop=%s actor=%s source=%s",
        user_id, shop_id, actor_id, source,
    )
    if result.rowcount:
        await _write_access_audit(
            db,
            actor_id=actor_id,
            target_user_id=user_id,
            object_type="shop_access",
            object_id=shop_id,
            action="grant",
            source=source,
        )


async def revoke_shop_access(
    db: AsyncSession,
    user_id: uuid.UUID,
    shop_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    source: str = "manual",
) -> None:
    """Remove a user's grant for a shop (no-op if absent).

    `source` mirrors grant_shop_access (USER-ACCESS-2 symmetry fix). Only a
    revoke that actually removes a row is audited.
    """
    result = await db.execute(
        delete(UserShopAccess).where(
            UserShopAccess.user_id == user_id,
            UserShopAccess.shop_id == shop_id,
        )
    )
    logger.info(
        "[ACCESS] revoke user=%s shop=%s actor=%s source=%s",
        user_id, shop_id, actor_id, source,
    )
    if result.rowcount:
        await _write_access_audit(
            db,
            actor_id=actor_id,
            target_user_id=user_id,
            object_type="shop_access",
            object_id=shop_id,
            action="revoke",
            source=source,
        )


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
        await revoke_shop_access(db, user_id, shop_id, actor_id=actor_id, source="editor")

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

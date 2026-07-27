"""OrderHub CRM — provision the MCP agent user (MCP-WAREHOUSE §5.6/§5.7).

Creates (or reconciles) the dedicated principal the MCP warehouse server logs in
as. Idempotent: safe to re-run on dev and prod.

Why a MANAGER and not an OWNER: OWNER short-circuits both `get_shop_scope` and
`get_capabilities`, which would make the agent an unbounded superuser. A MANAGER
with explicit shop grants and an explicit `view_costs` capability is bounded by
exactly the same guards that bound a human manager — no new authorization code,
nothing the completeness tests can miss.

`view_finance` is deliberately NOT granted by default: the agent populates costs,
it has no reason to read the P&L. Pass --view-finance if that changes.

Every stock/cost row the agent writes carries this user's id (the receipt,
movement and overhead-receipt tables all have a NOT NULL user_id), so its work is
attributable and separable from the owner's.

Usage:
  cd backend && python scripts/provision_agent_user.py --shops KoraKlenu
  cd backend && python scripts/provision_agent_user.py --all-shops
  cd backend && python scripts/provision_agent_user.py --show
  cd backend && python scripts/provision_agent_user.py --reset-password

Revoke with: UPDATE users SET is_active = false WHERE email = '<agent email>';
(checked by both get_current_user and /api/auth/refresh).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/provision_agent_user.py` from the backend root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from database import async_session_factory
from models.shop import Shop
from models.user import Capability, User, UserRole
from services.access_service import (
    get_capabilities,
    get_granted_shop_ids,
    set_capabilities,
    set_shop_access,
)
from services.auth_service import generate_temp_password, hash_password

DEFAULT_EMAIL = "agent@orderhub.dev"
DEFAULT_NAME = "MCP Warehouse Agent"


async def _resolve_shops(session, names: list[str], all_shops: bool) -> set:
    result = await session.execute(
        select(Shop.id, Shop.name).where(Shop.is_active == True)  # noqa: E712
    )
    rows = result.all()
    by_name = {name: shop_id for shop_id, name in rows}

    if all_shops:
        return set(by_name.values())

    resolved, missing = set(), []
    for wanted in names:
        match = next((n for n in by_name if n.lower() == wanted.lower()), None)
        if match is None:
            missing.append(wanted)
        else:
            resolved.add(by_name[match])
    if missing:
        raise SystemExit(
            f"No active shop named {missing!r}. Available: {sorted(by_name)}"
        )
    return resolved


async def _report(session, user: User) -> None:
    caps = await get_capabilities(session, user)
    granted = await get_granted_shop_ids(session, user.id)
    names = []
    if granted:
        result = await session.execute(select(Shop.name).where(Shop.id.in_(granted)))
        names = sorted(result.scalars().all())

    print(f"  email       {user.email}")
    print(f"  role        {user.role.value}")
    print(f"  active      {user.is_active}")
    print(f"  view_costs  {caps.has(Capability.VIEW_COSTS)}")
    print(f"  view_finance {caps.has(Capability.VIEW_FINANCE)}")
    print(f"  shops       {', '.join(names) if names else '(none)'}")


async def run(args) -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == args.email))
        user = result.scalar_one_or_none()

        if args.show:
            if user is None:
                print(f"No agent user {args.email!r}.")
                return 1
            print("Agent user:")
            await _report(session, user)
            return 0

        new_password: str | None = None
        if user is None:
            new_password = args.password or generate_temp_password(20)
            user = User(
                email=args.email,
                hashed_password=hash_password(new_password),
                full_name=args.name,
                role=UserRole.MANAGER,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"Created agent user {args.email!r}.")
        else:
            if user.role != UserRole.MANAGER:
                raise SystemExit(
                    f"{args.email!r} exists with role {user.role.value}; refusing to "
                    "change it. The agent principal must be a MANAGER — an OWNER "
                    "short-circuits every access check."
                )
            if args.reset_password or args.password:
                new_password = args.password or generate_temp_password(20)
                user.hashed_password = hash_password(new_password)
                print(f"Reset password for {args.email!r}.")
            else:
                print(f"Agent user {args.email!r} already exists; reconciling access.")

        # Capabilities: view_costs is required (material unit costs are the whole
        # job); view_finance stays off unless asked for.
        await set_capabilities(
            session,
            user.id,
            {
                Capability.VIEW_COSTS: True,
                Capability.VIEW_FINANCE: bool(args.view_finance),
            },
        )

        if args.all_shops or args.shops:
            shop_ids = await _resolve_shops(session, args.shops, args.all_shops)
            added, removed = await set_shop_access(session, user.id, shop_ids)
            print(f"Shop access: +{len(added)} / -{len(removed)}")

        await session.commit()
        await session.refresh(user)

        print("\nAgent user:")
        await _report(session, user)

        if new_password:
            print(
                "\n  password    "
                f"{new_password}\n"
                "\n  Store it in mcp_server/.env as ORDERHUB_AGENT_PASSWORD "
                "(git-ignored) or in the OS keychain.\n"
                "  It is shown once and is not recoverable — re-run with "
                "--reset-password to issue a new one."
            )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument(
        "--password",
        default=None,
        help="Set an explicit password. Omit to generate one (printed once).",
    )
    parser.add_argument(
        "--reset-password", action="store_true", help="Issue a new password."
    )
    parser.add_argument(
        "--shops",
        nargs="*",
        default=[],
        metavar="NAME",
        help="Shop names to grant (replaces the current grant set).",
    )
    parser.add_argument(
        "--all-shops", action="store_true", help="Grant every active shop."
    )
    parser.add_argument(
        "--view-finance",
        action="store_true",
        help="Also grant view_finance (P&L). Off by default — the agent writes "
        "costs, it does not need to read profit.",
    )
    parser.add_argument(
        "--show", action="store_true", help="Print current state and exit."
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

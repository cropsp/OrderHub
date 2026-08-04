"""
OrderHub CRM — Imports Router
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.user import Capability, User, UserRole
from models.shop import Shop, ShopPlatform
from schemas.common import ImportResult
from schemas.etsy_statement import StatementImportReport
from routers.dependencies import (
    assert_shop_access,
    get_current_user,
    require_capability,
    require_role,
)
from services.etsy_parser import parse_etsy_csv
from services.etsy_statement_parser import StatementParseError
from services.etsy_statement_service import import_statement

logger = get_logger("routers.imports")

router = APIRouter(prefix="/api/imports", tags=["imports"])


async def _get_etsy_shop(db: AsyncSession, shop_id: uuid.UUID, current_user: User) -> Shop:
    """Resolve an active Etsy shop the caller may write to."""
    # USER-ACCESS-1: a manager may only import into a shop they can access.
    await assert_shop_access(db, shop_id, current_user)

    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))
    shop = result.scalar_one_or_none()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    if shop.platform != ShopPlatform.ETSY:
        raise HTTPException(status_code=400, detail="Shop is not an Etsy shop")

    return shop


@router.post("/etsy", response_model=ImportResult)
async def import_etsy_orders(
    shop_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Import orders from an Etsy CSV export. Idempotent based on Sale ID."""
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    shop = await _get_etsy_shop(db, shop_id, current_user)

    content = await file.read()

    try:
        import_result = await parse_etsy_csv(db, shop, content, current_user.id)
        await db.commit() # Commit the transaction here after successful parsing
        return import_result
    except Exception as e:
        await db.rollback()
        # CSV parse/validation errors carry actionable per-row context (e.g. "Row 5: missing 'Sale Date'");
        # surface them to the user verbatim. Internal traceback still goes to logs.
        logger.error(f"[IMPORTS] Etsy import failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import: {str(e)}")


@router.post(
    "/etsy-statement",
    response_model=StatementImportReport,
    # USER-ACCESS-2: the report is entirely per-order fees and cost totals, so the
    # whole endpoint is 403'd without VIEW_COSTS (`view_costs-403`). It sits on
    # the endpoint rather than the router so the order-CSV import above — which
    # returns only counts — keeps its existing role-only gate.
    dependencies=[Depends(require_capability(Capability.VIEW_COSTS))],
)
async def import_etsy_statement(
    shop_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    # Defaults TRUE, like every other money-writing surface in this codebase
    # (ShopPlatformFeeBackfillRequest.dry_run). A caller that forgets the flag
    # gets a rehearsal, never an unreviewed write; booking is an explicit
    # `dry_run=false`.
    dry_run: bool = Form(True),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Import one monthly Etsy payment-account statement (STATEMENT-IMPORT).

    Derives exact per-order `platform_fee` from the Fee + fee-VAT lines and books
    advertising and listing/account fees to two monthly overhead rows.

    Idempotent per calendar month: re-uploading a statement replaces that
    period's lines wholesale and recomputes the affected fees, so importing the
    same file twice is a no-op and a re-issued statement fully supersedes the
    original.

    `dry_run=true` (the default) reports exactly what a real import would do and
    writes nothing — the service runs the import whole and rolls it back, so the
    two reports are identical bar this flag.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    shop = await _get_etsy_shop(db, shop_id, current_user)

    content = await file.read()

    try:
        report = await import_statement(
            db, shop, content, file.filename, current_user.id, dry_run=dry_run
        )
        # A dry run has already rolled itself back inside the service; committing
        # here would only commit an empty transaction, but not committing keeps
        # the two paths honestly distinct at the surface too.
        if not dry_run:
            await db.commit()
        return report
    except StatementParseError as e:
        # A row we do not understand aborts the whole import by design: silently
        # dropping one is how fee under-booking hides. The message names the
        # offending row, so surface it verbatim — it is the operator's fix.
        await db.rollback()
        logger.warning(
            f"[IMPORTS] Etsy statement rejected for shop {shop_id}: {e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(
            f"[IMPORTS] Etsy statement import failed for shop {shop_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to import: {str(e)}")

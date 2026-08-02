"""
OrderHub CRM — Receipts-by-invoice Router

MAT-6: one read that reconstructs a whole supplier invoice. Until now receipts
could only be listed per-material (`/api/materials/{id}/receipts`), so checking
that an 8-line invoice was booked correctly meant one call per material.

It deliberately spans **both** ledgers. A real supplier invoice mixes direct
materials with overhead lines — two of the eight invoices in the first real load
carry a cutting-service / finishing-compound line alongside the leather — so a
direct-only view would return an invoice that never ties to its paper total,
which is the one thing this endpoint exists to do.

Lives in its own router rather than under `/api/materials` for two reasons:
`/api/materials/receipts` would collide with `/api/materials/{material_id}`
(matched as a material id, then rejected as a malformed UUID) unless declared
above it — an ordering dependency that breaks silently — and the response is not
purely material receipts anyway.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.material import (
    Material,
    MaterialReceipt,
    OverheadMaterial,
    OverheadMaterialReceipt,
)
from models.user import Capability, UserRole
from routers.dependencies import require_capability, require_role
from schemas.material import (
    InvoiceMaterialReceiptRead,
    InvoiceOverheadReceiptRead,
    InvoiceReceiptsRead,
)


# USER-ACCESS-2: receipt lines carry unit costs and totals — an itemised cost
# surface, gated by view_costs at the router level, exactly like the
# /api/materials and /api/overhead-materials routers it reads from.
router = APIRouter(
    prefix="/api/receipts",
    tags=["Receipts"],
    dependencies=[Depends(require_capability(Capability.VIEW_COSTS))],
)


@router.get("/by-invoice", response_model=InvoiceReceiptsRead)
async def list_receipts_by_invoice(
    invoice_no: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Every line booked under one supplier invoice, across materials and overhead.

    Ordered oldest-first — the order the lines were entered off the paper
    invoice, the inverse of the per-material "newest purchase first" listings.

    An unknown invoice returns 200 with two empty lists rather than 404: an
    invoice is not an entity here, only a string stamped on receipt rows, so
    "no lines" is an answer and not a missing resource.
    """
    material_rows = await db.execute(
        select(MaterialReceipt, Material.name)
        .join(Material, MaterialReceipt.material_id == Material.id)
        .where(MaterialReceipt.invoice_no == invoice_no)
        .order_by(MaterialReceipt.received_at, MaterialReceipt.created_at)
    )
    overhead_rows = await db.execute(
        select(OverheadMaterialReceipt, OverheadMaterial.name)
        .join(
            OverheadMaterial,
            OverheadMaterialReceipt.overhead_material_id == OverheadMaterial.id,
        )
        .where(OverheadMaterialReceipt.invoice_no == invoice_no)
        .order_by(
            OverheadMaterialReceipt.received_at, OverheadMaterialReceipt.created_at
        )
    )

    materials: List[InvoiceMaterialReceiptRead] = []
    for receipt, material_name in material_rows.all():
        line = InvoiceMaterialReceiptRead.model_validate(receipt)
        line.material_name = material_name
        materials.append(line)

    overheads: List[InvoiceOverheadReceiptRead] = []
    for receipt, overhead_name in overhead_rows.all():
        line = InvoiceOverheadReceiptRead.model_validate(receipt)
        line.overhead_material_name = overhead_name
        overheads.append(line)

    return InvoiceReceiptsRead(
        invoice_no=invoice_no,
        material_receipts=materials,
        overhead_receipts=overheads,
    )

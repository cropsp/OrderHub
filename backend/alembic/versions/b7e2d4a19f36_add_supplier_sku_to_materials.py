"""add supplier_sku to materials (MAT-6)

The supplier's article (артикул) — the key that actually ties one material
across several invoices. Until now it only lived in free-text `notes`, so it
could not be searched and the create-time duplicate guard could only catch an
exact *name* collision.

Purely additive: one nullable column + one index. Downgrade drops both.

The index is deliberately **non-unique**. Suppliers own their code spaces and
may reuse a number for unrelated items; `materials.supplier_name` is free text,
so the correct key `(supplier, sku)` is not expressible here. A partial unique
on active rows would also turn un-archiving a material into an IntegrityError
raised from a router with no handling for it. Collisions are refused at the MCP
`create_material` guard (overridable with `allow_duplicate_sku=True`) instead.

Revision ID: b7e2d4a19f36
Revises: f982a7258777
Create Date: 2026-08-02 09:58:14.220517
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2d4a19f36'
down_revision: Union[str, None] = 'f982a7258777'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'materials',
        sa.Column('supplier_sku', sa.String(length=100), nullable=True),
    )
    op.create_index(
        'ix_materials_supplier_sku', 'materials', ['supplier_sku'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_materials_supplier_sku', table_name='materials')
    op.drop_column('materials', 'supplier_sku')

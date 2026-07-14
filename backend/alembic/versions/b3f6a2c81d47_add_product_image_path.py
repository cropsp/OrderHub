"""add_product_image_path

Adds a single nullable ``image_path`` column to ``products`` (PC-F-1). The value
is a path relative to ``UPLOADS_DIR`` (``products/{product_id}/{uuid}.{ext}``);
the bytes live on the ``uploads_data`` volume, not in the DB.

``downgrade()`` drops the column. Files already written under
``uploads/products/`` are deliberately left on disk — a schema migration does not
delete operator data. Re-upgrading yields a NULL column (the rows lose their
pointer), so the orphaned files would need manual cleanup if a downgrade is ever
made permanent.

Revision ID: b3f6a2c81d47
Revises: a7c8e91d2b4f
Create Date: 2026-07-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f6a2c81d47'
down_revision: Union[str, None] = 'a7c8e91d2b4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('image_path', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'image_path')

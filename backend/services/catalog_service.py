import uuid
from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from models.material import Material
from models.product import Product, ProductVariant
from models.packaging import PackagingBox
from schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate, ProductVariantUpdate
from schemas.packaging import PackagingBoxCreate, PackagingBoxUpdate


# WH-1: the Material minted alongside a new packaging box. Boxes are counted in
# pieces and bought in hryvnia; cost and stock start at zero and move only through
# receipts, exactly like any other material. The same values are frozen into the
# WH-1 migration, which backfills historical boxes without importing this module.
PACKAGING_MATERIAL_UNIT = "шт"
PACKAGING_MATERIAL_CURRENCY = "UAH"


class CatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Product Operations ---
    async def get_products(self, shop_id: uuid.UUID, is_active: Optional[bool] = True) -> List[Product]:
        query = select(Product).filter(Product.shop_id == shop_id).options(selectinload(Product.variants))
        if is_active is not None:
            query = query.filter(Product.is_active == is_active)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_product(self, shop_id: uuid.UUID, schema: ProductCreate) -> Product:
        product = Product(
            shop_id=shop_id,
            title=schema.title,
            description=schema.description,
            external_ref=schema.external_ref,
            is_active=schema.is_active
        )
        self.db.add(product)
        await self.db.flush()

        for v_schema in schema.variants:
            variant = ProductVariant(
                product_id=product.id,
                sku=v_schema.sku,
                variant_name=v_schema.variant_name,
                external_ref=v_schema.external_ref,
                weight_g=v_schema.weight_g,
                length_mm=v_schema.length_mm,
                width_mm=v_schema.width_mm,
                height_mm=v_schema.height_mm,
                price=v_schema.price,
                cost_price=v_schema.cost_price,
                stock_quantity=v_schema.stock_quantity,
                is_active=v_schema.is_active
            )
            self.db.add(variant)
        
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def get_product(self, product_id: uuid.UUID) -> Optional[Product]:
        query = select(Product).filter(Product.id == product_id).options(selectinload(Product.variants))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_product(self, product_id: uuid.UUID, schema: ProductUpdate) -> Optional[Product]:
        product = await self.get_product(product_id)
        if not product:
            return None

        update_data = schema.model_dump(exclude_unset=True)

        # Extract variants before setting product-level fields
        variant_patches = update_data.pop('variants', None)

        for key, value in update_data.items():
            setattr(product, key, value)

        # Apply variant patches when provided (form edit flow)
        if variant_patches:
            for v_data in variant_patches:
                v_id = v_data.pop('id', None)
                if v_id is None:
                    required = ('weight_g', 'length_mm', 'width_mm', 'height_mm')
                    missing = [f for f in required if v_data.get(f) is None]
                    if missing:
                        raise ValueError(f"New variant missing required fields: {missing}")
                    self.db.add(ProductVariant(product_id=product_id, **v_data))
                    continue
                variant = await self.db.get(ProductVariant, v_id)
                if variant is None or variant.product_id != product_id:
                    continue
                for key, value in v_data.items():
                    setattr(variant, key, value)

        await self.db.commit()
        # Re-fetch via get_product to ensure variants are loaded via selectinload
        return await self.get_product(product_id)

    async def soft_delete_product(self, product_id: uuid.UUID):
        product = await self.get_product(product_id)
        if product:
            product.is_active = False
            product.archived_at = datetime.now()
            await self.db.commit()

    # --- Packaging Operations ---
    #
    # WH-2: every read here loads the paired Material eagerly. PackagingBoxRead's
    # stock counters are properties over that material, so a box serialized without
    # it raises MissingGreenlet at response time. The relationship is deliberately
    # left default-lazy on the model (see models/packaging.py) — making it eager
    # there would drag a materials query onto every page of GET /api/orders, which
    # never reads the object. Loading is the caller's job, at the three sites that
    # actually build the read model. Precedent: get_product's selectinload re-fetch.
    async def get_packaging_boxes(
        self, *, include_archived: bool = False
    ) -> List[PackagingBox]:
        # contains_eager, not joinedload: the join is already here for the filter,
        # and joinedload would add a second, aliased one.
        query = (
            select(PackagingBox)
            .join(PackagingBox.material)
            .options(contains_eager(PackagingBox.material))
            .order_by(PackagingBox.packaging_type, PackagingBox.sort_order)
        )
        if not include_archived:
            query = query.where(Material.is_active.is_(True))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_packaging_box(self, schema: PackagingBoxCreate) -> PackagingBox:
        data = schema.model_dump()
        # WH-2: the threshold is a material setting now — the box row no longer has
        # the column. It still enters through the packaging form because that is the
        # one surface where boxes are managed.
        low_stock_threshold = data.pop("low_stock_threshold")

        # WH-1: a box IS a material (cost, receipts, supplier article, archiving)
        # plus this geometry row. Both are staged in the caller's single transaction
        # so a box can never exist without its material. No user_id is needed — the
        # materials tables carry no author — which keeps the CSV-confirm path
        # working exactly as before.
        material = Material(
            name=data["name"],
            unit=PACKAGING_MATERIAL_UNIT,
            currency=PACKAGING_MATERIAL_CURRENCY,
            category="PACKAGING",
            is_stock_tracked=True,
            is_active=True,
            low_stock_threshold=low_stock_threshold,
        )
        self.db.add(material)
        # The UUID primary key default is Python-side, applied at flush — the id has
        # to be materialized before the geometry row can point at it.
        await self.db.flush()

        box = PackagingBox(**data, material_id=material.id)
        self.db.add(box)
        await self.db.flush()

        await self.db.commit()
        # Re-fetch rather than refresh: refresh would leave `material` unloaded.
        return await self.get_packaging_box(box.id)

    async def get_packaging_box(self, box_id: uuid.UUID) -> Optional[PackagingBox]:
        query = (
            select(PackagingBox)
            .filter(PackagingBox.id == box_id)
            .options(joinedload(PackagingBox.material))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_packaging_box(self, box_id: uuid.UUID, schema: PackagingBoxUpdate) -> Optional[PackagingBox]:
        box = await self.get_packaging_box(box_id)
        if not box:
            return None

        update_data = schema.model_dump(exclude_unset=True)
        # WH-2: threshold lives on the material; never setattr it onto the box.
        new_threshold = update_data.pop("low_stock_threshold", None)
        for key, value in update_data.items():
            setattr(box, key, value)

        # WH-1: the packaging surface is the single place a box is named, so the
        # paired material follows it. The reverse rename is refused by the materials
        # router, which keeps the two from drifting apart.
        if "name" in update_data or new_threshold is not None:
            material = await self.db.get(Material, box.material_id)
            if material is not None:
                if "name" in update_data:
                    material.name = update_data["name"]
                if new_threshold is not None:
                    material.low_stock_threshold = new_threshold

        await self.db.commit()
        return await self.get_packaging_box(box_id)

    async def archive_packaging_box(self, box_id: uuid.UUID):
        """Archive a box: the material is deactivated, the geometry row SURVIVES.

        WH-2 finishes what WH-1 started. The geometry row used to be hard-deleted,
        which CASCADE-ed its packaging_stock_movements history away — the very rows
        WH-2 freezes as read-only archaeology — and left a material nothing pointed
        at. A box lives exactly as long as its material now (design §2.6): archived
        boxes drop out of the picker and the parcel calculator, keep their receipts
        and their ledger, and can be brought back by reactivating the material.
        """
        box = await self.get_packaging_box(box_id)
        if not box:
            return

        material = await self.db.get(Material, box.material_id)
        if material is not None:
            material.is_active = False

        await self.db.commit()

    async def find_product_by_external_ref(self, shop_id: uuid.UUID, external_ref: str) -> Optional[Product]:
        query = (
            select(Product)
            .filter(Product.shop_id == shop_id, Product.external_ref == external_ref)
            .options(selectinload(Product.variants))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # --- SKU Uniqueness Check ---
    async def is_sku_taken(self, shop_id: uuid.UUID, sku: str, exclude_variant_id: Optional[uuid.UUID] = None) -> bool:
        query = select(ProductVariant).join(Product).filter(
            Product.shop_id == shop_id,
            ProductVariant.sku == sku
        )
        if exclude_variant_id:
            query = query.filter(ProductVariant.id != exclude_variant_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

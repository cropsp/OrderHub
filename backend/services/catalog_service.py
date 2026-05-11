import uuid
from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.product import Product, ProductVariant
from models.packaging import PackagingBox
from models.stock_movement import StockMovementReason
from schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate, ProductVariantUpdate
from schemas.packaging import PackagingBoxCreate, PackagingBoxUpdate
from services import stock_service


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
    async def get_packaging_boxes(self) -> List[PackagingBox]:
        query = select(PackagingBox).order_by(
            PackagingBox.packaging_type, PackagingBox.sort_order
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_packaging_box(
        self,
        schema: PackagingBoxCreate,
        user_id: Optional[uuid.UUID] = None,
    ) -> PackagingBox:
        data = schema.model_dump()
        initial_quantity = data.pop("initial_quantity", 0)
        box = PackagingBox(**data)
        self.db.add(box)
        await self.db.flush()

        if initial_quantity > 0:
            if user_id is None:
                raise ValueError(
                    "user_id is required to record an initial_stock ledger row"
                )
            await stock_service.apply_movement(
                self.db,
                box_id=box.id,
                delta=initial_quantity,
                reason=StockMovementReason.INITIAL_STOCK,
                user_id=user_id,
            )

        await self.db.commit()
        await self.db.refresh(box)
        return box

    async def get_packaging_box(self, box_id: uuid.UUID) -> Optional[PackagingBox]:
        query = select(PackagingBox).filter(PackagingBox.id == box_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_packaging_box(self, box_id: uuid.UUID, schema: PackagingBoxUpdate) -> Optional[PackagingBox]:
        box = await self.get_packaging_box(box_id)
        if not box:
            return None
        
        update_data = schema.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(box, key, value)
        
        await self.db.commit()
        await self.db.refresh(box)
        return box

    async def delete_packaging_box(self, box_id: uuid.UUID):
        await self.db.execute(delete(PackagingBox).filter(PackagingBox.id == box_id))
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

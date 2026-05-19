"""
OrderHub CRM — Models Package

Imports all models so Alembic and SQLAlchemy can discover them.
"""

from models.base import Base
from models.user import User, UserRole
from models.shop import Shop, ShopPlatform
from models.customer import Customer
from models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    ALLOWED_TRANSITIONS,
)
from models.product import Product, ProductVariant
from models.packaging import PackagingBox, PackagingType
from models.stock_movement import PackagingStockMovement, StockMovementReason
from models.attachment import Attachment, AttachmentType
from models.material import (
    Material,
    MaterialMovement,
    MaterialMovementReason,
    MaterialReceipt,
    OverheadMaterial,
    OverheadMaterialReceipt,
)
from models.bom import BomItem
from models.partner_settlement import PartnerSettlement, PartnerSettlementFormula
from models.partner_payment import PartnerPayment
from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Shop",
    "ShopPlatform",
    "Customer",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusHistory",
    "ALLOWED_TRANSITIONS",
    "Attachment",
    "AttachmentType",
    "Product",
    "ProductVariant",
    "PackagingBox",
    "PackagingType",
    "PackagingStockMovement",
    "StockMovementReason",
    "Material",
    "OverheadMaterial",
    "MaterialReceipt",
    "OverheadMaterialReceipt",
    "MaterialMovement",
    "MaterialMovementReason",
    "BomItem",
    "PartnerSettlement",
    "PartnerSettlementFormula",
    "PartnerPayment",
    "IdlaserDraftJob",
    "IdlaserDraftJobState",
]

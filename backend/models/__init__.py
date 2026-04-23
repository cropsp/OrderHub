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
from models.attachment import Attachment, AttachmentType

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
]

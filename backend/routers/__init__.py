"""
OrderHub CRM — Routers Package
"""

from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.shops import router as shops_router
from routers.customers import router as customers_router
from routers.orders import router as orders_router
from routers.imports import router as imports_router
from routers.attachments import router as attachments_router
from routers.dashboard import router as dashboard_router
from routers.webhooks import router as webhooks_router
from routers.products import router as products_router
from routers.packaging import router as packaging_router

__all__ = [
    "auth_router",
    "users_router",
    "shops_router",
    "customers_router",
    "orders_router",
    "imports_router",
    "attachments_router",
    "dashboard_router",
    "webhooks_router",
    "products_router",
    "packaging_router",
]

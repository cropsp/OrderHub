"""
OrderHub CRM — Schemas Package
"""

from schemas.auth import LoginRequest, TokenResponse, RefreshResponse, TokenPayload
from schemas.user import UserBase, UserCreate, UserUpdate, UserResponse, UserWithPasswordResponse
from schemas.common import PaginationParams, PaginatedResponse, ErrorResponse, ImportResult

from schemas.shop import ShopBase, ShopCreate, ShopUpdate, ShopResponse, ShopDetailResponse
from schemas.customer import CustomerCreate, CustomerResponse
from schemas.order import (
    OrderItemResponse, StatusHistoryResponse, OrderBase, OrderListResponse, OrderResponse,
    OrderCreate, OrderUpdate, StatusChangeRequest
)
from schemas.dashboard import DashboardStats, RevenueByCurrency, DashboardResponse
from schemas.attachment import AttachmentResponse

__all__ = [
    "LoginRequest", "TokenResponse", "RefreshResponse", "TokenPayload",
    "UserBase", "UserCreate", "UserUpdate", "UserResponse", "UserWithPasswordResponse",
    "PaginationParams", "PaginatedResponse", "ErrorResponse", "ImportResult",
    "ShopBase", "ShopCreate", "ShopUpdate", "ShopResponse", "ShopDetailResponse",
    "CustomerCreate", "CustomerResponse",
    "OrderItemResponse", "StatusHistoryResponse", "OrderBase", "OrderListResponse",
    "OrderResponse", "OrderCreate", "OrderUpdate", "StatusChangeRequest",
    "DashboardStats", "RevenueByCurrency", "DashboardResponse",
    "AttachmentResponse",
]

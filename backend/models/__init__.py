"""
OrderHub CRM — Models Package

Imports all models so Alembic and SQLAlchemy can discover them.
"""

from models.base import Base
from models.user import User, UserRole, Capability
from models.app_setting import (
    AppSetting,
    FX_FETCHED_AT,
    FX_RATE_DATE,
    FX_SOURCE_URL,
    FX_UAH_PER_USD_CACHED,
    FX_UAH_PER_USD_OVERRIDE,
    GOOGLE_ADDRESS_VALIDATION_API_KEY,
    PLAINTEXT_SETTING_KEYS,
    SECRET_SETTING_KEYS,
    WB_TRACKING_STALLED_DAYS,
    WESTERNBID_API_KEY,
    WESTERNBID_LOGIN,
)
from models.shop import Shop, ShopPlatform
from models.customer import Customer
from models.order import (
    AddressValidationStatus,
    Order,
    OrderItem,
    OrderRefund,
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
from models.etsy_statement_line import EtsyStatementLine
from models.partner_settlement import PartnerSettlement, PartnerSettlementFormula
from models.partner_payment import PartnerPayment
from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState
from models.user_shop_access import UserShopAccess
from models.user_capability import UserCapability
from models.access_audit import AccessAudit
from models.fx_rate_audit import FxRateAudit
from models.agent_action_log import AgentActionLog
from models.wb_parcel import WbParcel
from models.wb_tracking import WbParcelTracking, WbTrackingEvent

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Capability",
    "AppSetting",
    "FX_FETCHED_AT",
    "FX_RATE_DATE",
    "FX_SOURCE_URL",
    "FX_UAH_PER_USD_CACHED",
    "FX_UAH_PER_USD_OVERRIDE",
    "GOOGLE_ADDRESS_VALIDATION_API_KEY",
    "PLAINTEXT_SETTING_KEYS",
    "SECRET_SETTING_KEYS",
    "WB_TRACKING_STALLED_DAYS",
    "WESTERNBID_API_KEY",
    "WESTERNBID_LOGIN",
    "Shop",
    "ShopPlatform",
    "Customer",
    "AddressValidationStatus",
    "Order",
    "OrderItem",
    "OrderRefund",
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
    "EtsyStatementLine",
    "PartnerSettlement",
    "PartnerSettlementFormula",
    "PartnerPayment",
    "IdlaserDraftJob",
    "IdlaserDraftJobState",
    "UserShopAccess",
    "UserCapability",
    "AccessAudit",
    "FxRateAudit",
    "AgentActionLog",
    "WbParcel",
    "WbParcelTracking",
    "WbTrackingEvent",
]

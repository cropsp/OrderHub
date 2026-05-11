import csv
import io
import uuid
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError
from schemas.product import ProductCreate, ProductVariantCreate
from schemas.packaging import PackagingBoxCreate
from schemas.import_preview import ImportErrorDetail, ImportPreviewResponse


class ImportService:
    # Class-level storage for previews (in-memory, simple TTL)
    # Format: { token: { "data": List[Dict], "type": "product"|"packaging", "shop_id": UUID, "expiry": timestamp } }
    _storage: Dict[str, Dict[str, Any]] = {}
    TTL = 600  # 10 minutes

    @classmethod
    def _cleanup(cls):
        now = time.time()
        keys_to_del = [k for k, v in cls._storage.items() if v["expiry"] < now]
        for k in keys_to_del:
            del cls._storage[k]

    @classmethod
    def save_preview(cls, shop_id: Optional[uuid.UUID], data: List[Dict], import_type: str) -> str:
        cls._cleanup()
        token = f"import_{uuid.uuid4().hex}"
        cls._storage[token] = {
            "data": data,
            "type": import_type,
            "shop_id": shop_id,
            "expiry": time.time() + cls.TTL
        }
        return token

    @classmethod
    def get_preview(cls, token: str) -> Optional[Dict[str, Any]]:
        cls._cleanup()
        item = cls._storage.get(token)
        if item and item["expiry"] > time.time():
            return item
        return None

    @classmethod
    def clear_preview(cls, token: str):
        if token in cls._storage:
            del cls._storage[token]

    @staticmethod
    def parse_csv(file_content: bytes) -> List[Dict[str, str]]:
        stream = io.StringIO(file_content.decode("utf-8"))
        reader = csv.DictReader(stream)
        return list(reader)

    @staticmethod
    def validate_products_csv(rows: List[Dict[str, str]]) -> Tuple[List[ProductCreate], List[ImportErrorDetail]]:
        valid_items = []
        errors = []
        
        # Tracking SKUs in current file to detect duplicates within CSV
        seen_skus = set()

        for i, row in enumerate(rows, start=1):
            try:
                # Basic field extraction and validation
                title = row.get("title", "").strip()
                sku = row.get("sku", "").strip()
                
                if not title:
                    errors.append(ImportErrorDetail(row=i, reason="Missing title"))
                    continue
                if not sku:
                    errors.append(ImportErrorDetail(row=i, reason="Missing SKU"))
                    continue
                if sku in seen_skus:
                    errors.append(ImportErrorDetail(row=i, reason=f"Duplicate SKU '{sku}' in CSV"))
                    continue
                
                seen_skus.add(sku)

                # Construct Pydantic model for validation
                p_create = ProductCreate(
                    title=title,
                    description=row.get("description"),
                    variants=[
                        ProductVariantCreate(
                            sku=sku,
                            weight_g=int(row.get("weight_g", 0)),
                            length_mm=int(row.get("length_mm", 0)),
                            width_mm=int(row.get("width_mm", 0)),
                            height_mm=int(row.get("height_mm", 0))
                        )
                    ]
                )
                valid_items.append(p_create)
            except (ValueError, ValidationError) as e:
                errors.append(ImportErrorDetail(row=i, reason=str(e)))
        
        return valid_items, errors

    @staticmethod
    def validate_packaging_csv(rows: List[Dict[str, str]]) -> Tuple[List[PackagingBoxCreate], List[ImportErrorDetail]]:
        valid_items = []
        errors = []

        for i, row in enumerate(rows, start=1):
            try:
                box_create = PackagingBoxCreate(
                    name=row.get("name", "").strip(),
                    packaging_type=row.get("packaging_type", "BOX").strip().upper(),
                    inner_length_mm=int(row.get("inner_length_mm", 0)),
                    inner_width_mm=int(row.get("inner_width_mm", 0)),
                    inner_height_mm=int(row.get("inner_height_mm", 0)),
                    max_thickness_mm=int(row["max_thickness_mm"]) if row.get("max_thickness_mm") else None,
                    max_weight_g=int(row.get("max_weight_g", 0)),
                    tare_weight_g=int(row.get("tare_weight_g", 0)),
                    sort_order=int(row.get("sort_order", 0))
                )
                valid_items.append(box_create)
            except (ValueError, ValidationError) as e:
                errors.append(ImportErrorDetail(row=i, reason=str(e)))
        
        return valid_items, errors

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ImportErrorDetail(BaseModel):
    row: int
    reason: str


class ImportPreviewResponse(BaseModel):
    import_token: str
    valid_count: int
    invalid_count: int
    errors: List[ImportErrorDetail]
    preview: List[Dict[str, Any]]


class ImportConfirmRequest(BaseModel):
    import_token: str

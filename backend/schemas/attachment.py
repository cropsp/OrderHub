"""
OrderHub CRM — Attachment Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.attachment import AttachmentType


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    uploaded_by_id: uuid.UUID
    file_name: str
    file_size: int
    mime_type: str
    attachment_type: AttachmentType
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

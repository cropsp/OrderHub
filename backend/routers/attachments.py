"""
OrderHub CRM — Attachments Router
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.user import User, UserRole
from models.order import Order
from models.attachment import Attachment, AttachmentType
from schemas.attachment import AttachmentResponse
from routers.dependencies import get_current_user, require_role
from services.file_storage import save_file, get_absolute_path, delete_file

logger = get_logger("routers.attachments")

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("/order/{order_id}", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    order_id: uuid.UUID,
    attachment_type: AttachmentType = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment for an order."""
    
    # Check if order exists
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Designers can only attach to assigned orders
    if current_user.role == UserRole.DESIGNER and order.assigned_designer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
        
    # Save file
    try:
        relative_path, file_size = await save_file(file, order_id)
    except Exception as e:
        logger.error(f"[ATTACHMENTS] Failed to save upload for order {order_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save attachment")
        
    # Create DB entry
    attachment = Attachment(
        id=uuid.uuid4(),
        order_id=order_id,
        uploaded_by_id=current_user.id,
        file_name=file.filename or "unknown",
        file_path=relative_path,
        file_size=file_size,
        mime_type=file.content_type or "application/octet-stream",
        attachment_type=attachment_type
    )
    
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    
    return attachment
    

@router.get("/order/{order_id}", response_model=list[AttachmentResponse])
async def list_attachments_by_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all attachments for a specific order."""
    # Check if order exists (and permission check if needed)
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Designers can only see attachments for assigned orders
    if current_user.role == UserRole.DESIGNER and order.assigned_designer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
        
    result = await db.execute(
        select(Attachment).where(Attachment.order_id == order_id).order_by(Attachment.created_at.desc())
    )
    attachments = result.scalars().all()
    return attachments



@router.get("/{attachment_id}")
async def download_attachment(
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download an attachment."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if current_user.role == UserRole.DESIGNER:
        order_result = await db.execute(select(Order).where(Order.id == attachment.order_id))
        order = order_result.scalar_one_or_none()
        if not order or order.assigned_designer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not assigned to this order")

    abs_path = get_absolute_path(attachment.file_path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="File content not found on disk")

    return FileResponse(
        path=abs_path,
        filename=attachment.file_name,
        media_type=attachment.mime_type
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an attachment (owner or uploader only)."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    # Check permissions
    if current_user.role != UserRole.OWNER and attachment.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this attachment")
        
    # Delete from disk
    delete_file(attachment.file_path)
    
    # Delete from DB
    await db.delete(attachment)
    await db.commit()

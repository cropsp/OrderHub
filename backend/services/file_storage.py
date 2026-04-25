"""
OrderHub CRM — File Storage Service
"""

import os
import uuid
import aiofiles
from fastapi import UploadFile
from pathlib import Path
from config import get_settings

settings = get_settings()
UPLOADS_DIR = Path(settings.UPLOADS_DIR)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""


async def save_file(
    upload_file: UploadFile,
    order_id: uuid.UUID,
    max_size: int = MAX_UPLOAD_BYTES,
) -> tuple[str, int]:
    """
    Saves an uploaded file to disk, enforcing ``max_size`` while streaming.
    Raises ``FileTooLargeError`` (and removes any partial file) if exceeded.
    Returns: (relative_file_path, file_size_in_bytes)
    """
    # Create directory for the order if it doesn't exist
    order_dir = UPLOADS_DIR / str(order_id)
    order_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions and path traversal
    base_name = os.path.basename(upload_file.filename) if upload_file.filename else "unknown"
    safe_filename = f"{uuid.uuid4()}_{base_name}"
    file_path = order_dir / safe_filename

    # Relative path to store in DB
    relative_path = str(Path(str(order_id)) / safe_filename)

    file_size = 0
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await upload_file.read(1024 * 1024):  # 1MB chunks
                file_size += len(content)
                if file_size > max_size:
                    raise FileTooLargeError(
                        f"upload exceeds maximum size of {max_size} bytes"
                    )
                await out_file.write(content)
    except FileTooLargeError:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    return relative_path, file_size


def get_absolute_path(relative_path: str) -> Path | None:
    """Gets the absolute path for a file, validating it stays within UPLOADS_DIR."""
    try:
        abs_path = (UPLOADS_DIR / relative_path).resolve()
        uploads_dir = UPLOADS_DIR.resolve()
        
        # Security check: prevent directory traversal attacks
        if uploads_dir not in abs_path.parents:
            return None
            
        if not abs_path.exists() or not abs_path.is_file():
            return None
            
        return abs_path
    except Exception:
        return None


def delete_file(relative_path: str) -> bool:
    """Deletes a file from disk."""
    abs_path = get_absolute_path(relative_path)
    if abs_path:
        try:
            abs_path.unlink()
            return True
        except Exception:
            pass
    return False

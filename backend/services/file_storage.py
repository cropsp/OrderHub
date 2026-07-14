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

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — designer source bundles (.psd/.ai/.zip) routinely 30-80 MB

# PC-F-1 — product images are thumbnails, not designer bundles, hence the tighter cap.
PRODUCT_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
PRODUCT_IMAGE_SUBDIR = "products"

# Allowed product-image types, mapped to the extension we generate. The client's
# declared Content-Type is never trusted — the type is sniffed from the leading
# bytes (``sniff_image_mime``), because we serve these files back to the browser.
PRODUCT_IMAGE_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""


class UnsupportedImageTypeError(Exception):
    """Raised when uploaded bytes are not an allowed product-image type."""


def sniff_image_mime(head: bytes) -> str | None:
    """Detects an allowed image type from the file's leading bytes.

    Returns the mime type, or ``None`` if the bytes are not an allowed image.
    Magic numbers per the JFIF, PNG and WebP (RIFF container) specs.
    """
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _stream_to_disk(
    upload_file: UploadFile,
    file_path: Path,
    max_size: int,
) -> int:
    """Streams ``upload_file`` into ``file_path`` in 1MB chunks, enforcing
    ``max_size``. Removes the partial file and raises ``FileTooLargeError`` if
    exceeded. Returns the number of bytes written."""
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

    return file_size


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

    file_size = await _stream_to_disk(upload_file, file_path, max_size)

    return relative_path, file_size


async def save_product_image(
    upload_file: UploadFile,
    product_id: uuid.UUID,
    ext: str,
) -> tuple[str, int]:
    """
    Saves a validated product image under ``products/{product_id}/``.

    The filename is generated (``{uuid}.{ext}``) — the client-supplied filename is
    never used, so the extension we serve Content-Type from is always our own.
    Caller must validate the type first (see ``sniff_image_mime``).
    Returns: (relative_file_path, file_size_in_bytes)
    """
    product_dir = UPLOADS_DIR / PRODUCT_IMAGE_SUBDIR / str(product_id)
    product_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{uuid.uuid4()}.{ext}"
    relative_path = str(Path(PRODUCT_IMAGE_SUBDIR) / str(product_id) / safe_filename)

    file_size = await _stream_to_disk(
        upload_file, product_dir / safe_filename, PRODUCT_IMAGE_MAX_BYTES
    )

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

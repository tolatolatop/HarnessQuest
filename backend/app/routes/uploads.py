import logging
import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import get_settings
from app.dependencies import get_current_user
from app.models import User
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/uploads", tags=["uploads"])
logger = logging.getLogger("uvicorn.error")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
MINIO_IMAGE_PREFIX = "uploads/images"


@router.post("/images")
async def upload_image(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {allowed}",
        )

    settings = get_settings()
    max_size_bytes = settings.max_image_upload_size_mb * 1024 * 1024

    content = await file.read()
    content_size = len(content)
    logger.info(
        "Image upload received filename=%s content_type=%s size_bytes=%s max_size_bytes=%s user_id=%s",
        file.filename,
        file.content_type,
        content_size,
        max_size_bytes,
        current_user.id,
    )
    if content_size > max_size_bytes:
        logger.warning(
            "Image upload rejected filename=%s size_bytes=%s max_size_bytes=%s user_id=%s",
            file.filename,
            content_size,
            max_size_bytes,
            current_user.id,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Image exceeds maximum size of {settings.max_image_upload_size_mb} MB",
        )

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    unique_name = f"{ts}_{uuid.uuid4().hex[:8]}{ext}"
    key = f"{MINIO_IMAGE_PREFIX}/{unique_name}"

    content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    storage = ObjectStorage()
    storage.put_binary(key, content, content_type=content_type)
    logger.info(
        "Image upload stored filename=%s key=%s size_bytes=%s content_type=%s user_id=%s",
        file.filename,
        key,
        content_size,
        content_type,
        current_user.id,
    )

    url = f"/api/v1/uploads/images/{unique_name}"
    return {"url": url}


@router.get("/images/{filename}")
def serve_image(
    filename: str,
) -> Response:
    key = f"{MINIO_IMAGE_PREFIX}/{filename}"
    storage = ObjectStorage()
    try:
        data, content_type = storage.get_binary(key)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc

    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )

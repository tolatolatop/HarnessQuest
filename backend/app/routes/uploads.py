import mimetypes
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app.dependencies import get_current_user
from app.models import User
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MINIO_IMAGE_PREFIX = "uploads/images"


@router.post("/images")
async def upload_image(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {allowed}",
        )

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds maximum size of 10 MB")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    unique_name = f"{ts}_{uuid.uuid4().hex[:8]}{ext}"
    key = f"{MINIO_IMAGE_PREFIX}/{unique_name}"

    content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    storage = ObjectStorage()
    storage.put_binary(key, content, content_type=content_type)

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
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )

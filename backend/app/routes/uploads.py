import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.config import get_settings
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


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

    settings = get_settings()
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    unique_name = f"{ts}_{uuid.uuid4().hex[:8]}{ext}"
    dest = os.path.join(upload_dir, unique_name)
    with open(dest, "wb") as f:
        f.write(content)

    url = f"/api/v1/uploads/images/{unique_name}"
    return {"url": url}

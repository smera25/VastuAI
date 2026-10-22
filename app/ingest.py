"""Upload validation + normalisation shared by every endpoint that accepts photos."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_LONG_SIDE = 2048          # bound memory/time for detection + reconstruction

Image.MAX_IMAGE_PIXELS = settings.max_image_pixels


@dataclass
class IngestedImage:
    index: int
    filename: str
    path: Path
    width: int
    height: int
    original_bytes: int


def normalise_image_bytes(data: bytes, name: str) -> Image.Image:
    """Decode, apply EXIF rotation (phones store portrait shots sideways), return RGB."""
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not read {name}: it is not a valid image ({exc}).") from exc
    if min(image.size) < 64:
        raise HTTPException(status_code=400, detail=f"{name}: image is too small (minimum 64 px).")
    return image


async def read_upload(file: UploadFile) -> tuple[bytes, str]:
    name = file.filename or "image"
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"{name}: upload a JPG, PNG, or WEBP image.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{name}: the uploaded file is empty.")
    if len(data) > settings.max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{name}: image must be smaller than {settings.max_image_bytes // (1024 * 1024)} MB.",
        )
    return data, name


async def ingest_uploads(files: list[UploadFile], dest_dir: Path) -> list[IngestedImage]:
    """Validate every upload, normalise it, and save as JPEG under ``dest_dir``."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one room image.")
    if len(files) > settings.max_room_images:
        raise HTTPException(status_code=400, detail=f"Upload no more than {settings.max_room_images} images.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[IngestedImage] = []
    for i, f in enumerate(files):
        data, name = await read_upload(f)
        image = normalise_image_bytes(data, name)
        if max(image.size) > MAX_LONG_SIDE:
            image.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.Resampling.LANCZOS)
        path = dest_dir / f"{i:02d}.jpg"
        image.save(path, format="JPEG", quality=92)
        out.append(IngestedImage(i, name, path, image.width, image.height, len(data)))
    return out

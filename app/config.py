
"""Environment-driven configuration. Secrets live here (backend only) - never in the frontend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids an extra dependency). Real env vars win."""
    if not path.is_file():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'"),
        )


_load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: str) -> str:
    """Return a normalized string setting."""
    return os.getenv(name, default).strip().lower()


@dataclass
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("VASTU_DATA_DIR", str(ROOT_DIR / "data"))
        )
    )

    # --- uploads -----------------------------------------------------------
    max_image_bytes: int = int(
        os.getenv("MAX_IMAGE_BYTES", 10 * 1024 * 1024)
    )
    max_room_images: int = int(os.getenv("MAX_ROOM_IMAGES", 12))
    min_room_images: int = 1
    max_image_pixels: int = int(
        os.getenv("MAX_IMAGE_PIXELS", 40_000_000)
    )

    # --- CORS --------------------------------------------------------------
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )

    # Allows development access from a phone on the same Wi-Fi.
    cors_origin_regex: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    )

    # --- VGGT --------------------------------------------------------------
    # auto = use VGGT when dependencies and weights are available.
    vggt_enabled: str = _bool("VGGT_ENABLED", "auto")
    vggt_model_id: str = os.getenv(
        "VGGT_MODEL_ID", "facebook/VGGT-1B"
    )
    vggt_weights_path: str = os.getenv("VGGT_WEIGHTS_PATH", "")
    vggt_device: str = _bool("VGGT_DEVICE", "auto")
    vggt_max_images: int = int(os.getenv("VGGT_MAX_IMAGES", 8))

    # --- image generation --------------------------------------------------
    # Supported: auto | openai | gemini | stability | none
    image_provider: str = _bool("IMAGE_PROVIDER", "auto")

    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_image_model: str = os.getenv(
        "OPENAI_IMAGE_MODEL", "gpt-image-1.5"
    )
    openai_image_quality: str = os.getenv(
        "OPENAI_IMAGE_QUALITY", "medium"
    )
    openai_base_url: str = os.getenv(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    )

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_image_model: str = os.getenv(
        "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"
    )
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    )

    # Stability AI
    stability_api_key: str = os.getenv("STABILITY_API_KEY", "")
    stability_image_model: str = os.getenv(
        "STABILITY_IMAGE_MODEL",
        "stable-diffusion-xl-1024-v1-0",
    )
    stability_base_url: str = os.getenv(
        "STABILITY_BASE_URL",
        "https://api.stability.ai",
    )

    # Shared image-generation timeout
    image_timeout_seconds: float = float(
        os.getenv("IMAGE_TIMEOUT_SECONDS", 180)
    )

    # --- jobs --------------------------------------------------------------
    job_ttl_seconds: int = int(
        os.getenv("JOB_TTL_SECONDS", 3600)
    )

    # --- logging -----------------------------------------------------------
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def ensure_dirs(self) -> None:
        for sub in ("jobs", "redesigns", "visualizations"):
            (self.data_dir / sub).mkdir(
                parents=True,
                exist_ok=True,
            )


settings = Settings()

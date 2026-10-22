
"""
Image-generation providers for Vastu Atelier.

Providers:
- OpenAI Images API
- Gemini generateContent API
- Stability AI Stable Image SD 3.5 API

All API keys are read from backend environment variables.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO

import httpx
from PIL import Image

from app.config import settings

log = logging.getLogger(__name__)


class ImageProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 502,
        hint: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.hint = hint

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass
class ImageResult:
    png_bytes: bytes
    provider: str
    model: str


def _to_png(raw: bytes) -> bytes:
    """Convert a generated image to PNG."""
    try:
        with Image.open(BytesIO(raw)) as im:
            out = BytesIO()
            im.convert("RGB").save(out, format="PNG")
            return out.getvalue()
    except Exception as exc:
        raise ImageProviderError(
            "provider_invalid_image",
            "The image provider returned data that could not be decoded.",
            502,
        ) from exc


def _image_size(reference: bytes | None) -> str:
    if reference:
        try:
            with Image.open(BytesIO(reference)) as im:
                w, h = im.size

            if w > h * 1.1:
                return "1536x1024"
            if h > w * 1.1:
                return "1024x1536"
            return "1024x1024"
        except Exception:
            pass

    return "1536x1024"


def _http_error(
    provider: str,
    exc: httpx.HTTPStatusError,
) -> ImageProviderError:
    status = exc.response.status_code

    try:
        body = exc.response.json()
        error = body.get("error", {})
        if isinstance(error, dict):
            detail = error.get("message") or str(body)[:500]
        else:
            detail = str(error or body)[:500]
    except Exception:
        detail = exc.response.text[:500]

    log.warning(
        "%s API returned HTTP %s: %s",
        provider,
        status,
        detail,
    )

    if status in (401, 403):
        return ImageProviderError(
            "provider_auth_failed",
            f"{provider} rejected the API key ({status}).",
            502,
            "Check the backend API key and account access.",
        )

    if status == 402:
        return ImageProviderError(
            "provider_payment_required",
            f"{provider} requires available credits or billing.",
            402,
            "Check the provider dashboard and remaining credits.",
        )

    if status == 429:
        return ImageProviderError(
            "provider_rate_limited",
            f"{provider} rate limit or quota reached.",
            429,
            "Check account limits and retry later.",
        )

    if status == 400 and any(
        word in detail.lower()
        for word in ("safety", "moderation", "policy", "blocked")
    ):
        return ImageProviderError(
            "provider_rejected_prompt",
            f"{provider} declined the request: {detail}",
            422,
            "Simplify the design prompt and retry.",
        )

    return ImageProviderError(
        "provider_error",
        f"{provider} returned HTTP {status}: {detail}",
        502,
        "Check the backend logs for the provider's response.",
    )


class ImageProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(
        self,
        prompt: str,
        reference_jpeg: bytes | None,
    ) -> ImageResult:
        ...


class OpenAIProvider(ImageProvider):
    name = "openai"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = settings.openai_image_model
        self._client = httpx.Client(
            timeout=settings.image_timeout_seconds,
            transport=transport,
        )
        self._auth = {
            "Authorization": f"Bearer {settings.openai_api_key}"
        }

    def generate(
        self,
        prompt: str,
        reference_jpeg: bytes | None,
    ) -> ImageResult:
        base = settings.openai_base_url.rstrip("/")
        size = _image_size(reference_jpeg)
        quality = settings.openai_image_quality

        try:
            if reference_jpeg:
                resp = self._client.post(
                    f"{base}/images/edits",
                    headers=self._auth,
                    data={
                        "model": self.model,
                        "prompt": prompt,
                        "size": size,
                        "quality": quality,
                    },
                    files={
                        "image[]": (
                            "reference.jpg",
                            reference_jpeg,
                            "image/jpeg",
                        )
                    },
                )
            else:
                resp = self._client.post(
                    f"{base}/images/generations",
                    headers={
                        **self._auth,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "size": size,
                        "quality": quality,
                    },
                )

            resp.raise_for_status()
            encoded = resp.json()["data"][0]["b64_json"]

        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "provider_timeout",
                "OpenAI took too long to respond.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_error("OpenAI", exc) from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ImageProviderError(
                "provider_bad_response",
                f"Unexpected response from OpenAI: {exc}",
            ) from exc

        return ImageResult(
            _to_png(base64.b64decode(encoded)),
            self.name,
            self.model,
        )


class GeminiProvider(ImageProvider):
    name = "gemini"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = settings.gemini_image_model
        self._client = httpx.Client(
            timeout=settings.image_timeout_seconds,
            transport=transport,
        )

    def generate(
        self,
        prompt: str,
        reference_jpeg: bytes | None,
    ) -> ImageResult:
        parts: list[dict] = [{"text": prompt}]

        if reference_jpeg:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(
                        reference_jpeg
                    ).decode("ascii"),
                }
            })

        url = (
            f"{settings.gemini_base_url.rstrip('/')}"
            f"/models/{self.model}:generateContent"
        )

        try:
            resp = self._client.post(
                url,
                headers={
                    "x-goog-api-key": settings.gemini_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"]
                    },
                },
            )
            resp.raise_for_status()
            body = resp.json()

        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "provider_timeout",
                "Gemini took too long to respond.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_error("Gemini", exc) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ImageProviderError(
                "provider_bad_response",
                f"Unexpected response from Gemini: {exc}",
            ) from exc

        text_bits = []

        for candidate in body.get("candidates", []):
            content = candidate.get("content") or {}

            for part in content.get("parts", []):
                blob = part.get("inlineData") or part.get("inline_data")

                if blob and blob.get("data"):
                    return ImageResult(
                        _to_png(base64.b64decode(blob["data"])),
                        self.name,
                        self.model,
                    )

                if part.get("text"):
                    text_bits.append(part["text"])

        raise ImageProviderError(
            "provider_no_image",
            "Gemini returned no image."
            + (
                f" It said: {' '.join(text_bits)[:200]}"
                if text_bits else ""
            ),
            502,
            "The prompt may have been blocked. Simplify it and retry.",
        )


class StabilityProvider(ImageProvider):
    """
    Stability AI Stable Image API using SD 3.5.

    Supports text-to-image and image-to-image requests.
    """

    name = "stability"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = settings.stability_image_model
        self._client = httpx.Client(
            timeout=settings.image_timeout_seconds,
            transport=transport,
        )
        self._auth = {
            "Authorization": f"Bearer {settings.stability_api_key}",
        }

    def generate(
        self,
        prompt: str,
        reference_jpeg: bytes | None,
    ) -> ImageResult:
        url = (
            f"{settings.stability_base_url.rstrip('/')}"
            "/v2beta/stable-image/generate/sd3"
        )

        data = {
            "prompt": prompt,
            "model": self.model,
            "output_format": "png",
            "negative_prompt": (
                "blurry, distorted walls, malformed furniture, "
                "unrealistic perspective, text, watermark"
            ),
        }

        files = None

        if reference_jpeg:
            # Moderate strength aims to balance redesign with preservation.
            # This is a starting point and can be tuned after testing.
            data["mode"] = "image-to-image"
            data["strength"] = "0.80"

            files = {
                "image": (
                    "reference.jpg",
                    reference_jpeg,
                    "image/jpeg",
                )
            }
        else:
            data["mode"] = "text-to-image"
            data["aspect_ratio"] = "3:2"

        try:
            resp = self._client.post(
                url,
                headers={
                    **self._auth,
                    "Accept": "image/*",
                },
                data=data,
                files=files,
            )
            resp.raise_for_status()

            image_bytes = resp.content

            if not image_bytes:
                raise ImageProviderError(
                    "provider_no_image",
                    "Stability AI returned an empty image response.",
                    502,
                )

        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "provider_timeout",
                "Stability AI took too long to respond.",
                504,
                "Retry the generation. Image requests may take time.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_error("Stability AI", exc) from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                "provider_bad_response",
                f"Could not communicate with Stability AI: {exc}",
            ) from exc

        return ImageResult(
            _to_png(image_bytes),
            self.name,
            self.model,
        )


def provider_status() -> dict:
    choice = settings.image_provider

    openai_ok = bool(settings.openai_api_key)
    gemini_ok = bool(settings.gemini_api_key)
    stability_ok = bool(settings.stability_api_key)

    configured = (
        (choice == "openai" and openai_ok)
        or (choice == "gemini" and gemini_ok)
        or (choice == "stability" and stability_ok)
        or (
            choice == "auto"
            and (openai_ok or gemini_ok or stability_ok)
        )
    )

    if choice == "auto":
        active = (
            "openai" if openai_ok
            else "gemini" if gemini_ok
            else "stability" if stability_ok
            else None
        )
    else:
        active = choice

    return {
        "setting": choice,
        "configured": bool(configured),
        "active": active if configured else None,
        "openai_key_present": openai_ok,
        "gemini_key_present": gemini_ok,
        "stability_key_present": stability_ok,
        "reason": (
            None if configured else
            "Image generation is disabled (IMAGE_PROVIDER=none)."
            if choice == "none" else
            "No API key is configured for the selected image provider. "
            "Check IMAGE_PROVIDER and the backend .env file."
        ),
    }


def get_provider(
    transport: httpx.BaseTransport | None = None,
) -> ImageProvider:
    status = provider_status()

    if not status["configured"]:
        raise ImageProviderError(
            "image_provider_not_configured",
            status["reason"],
            503,
            "Set the selected provider's API key in the backend .env "
            "file, then restart the backend.",
        )

    providers = {
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "stability": StabilityProvider,
    }

    provider_class = providers.get(status["active"])

    if provider_class is None:
        raise ImageProviderError(
            "image_provider_not_supported",
            f"Unsupported image provider: {status['active']}",
            503,
            "Use IMAGE_PROVIDER=openai, gemini, stability, auto, or none.",
        )

    return provider_class(transport)


DISCLAIMER = (
    "This image is an AI-generated visual proposal. It follows the "
    "structured layout only approximately and may not preserve the real "
    "room's geometry, proportions or fixed features exactly. Use the "
    "floor plan for dimensions and placement."
)

"""Provider tests use httpx.MockTransport: they verify REQUEST CONSTRUCTION and RESPONSE/ERROR HANDLING,
NOT real image generation (no API keys are available in CI)."""
import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from app import image_providers as ip
from app.config import settings


def png_b64():
    buf = BytesIO(); Image.new("RGB", (8, 8), "white").save(buf, "PNG"); return base64.b64encode(buf.getvalue()).decode()


def jpeg():
    buf = BytesIO(); Image.new("RGB", (30, 20), "gray").save(buf, "JPEG"); return buf.getvalue()


@pytest.fixture
def keys(monkeypatch):
    for k, v in dict(openai_api_key="sk-test", gemini_api_key="g-test", image_provider="auto").items():
        monkeypatch.setattr(settings, k, v, raising=False)


def _patch(monkeypatch, **kw):
    for k, v in kw.items():
        monkeypatch.setattr(settings, k, v, raising=False)


def test_not_configured_is_an_explicit_actionable_error(monkeypatch):
    _patch(monkeypatch, openai_api_key="", gemini_api_key="", image_provider="auto")
    with pytest.raises(ip.ImageProviderError) as e:
        ip.get_provider()
    assert e.value.code == "image_provider_not_configured" and e.value.status_code == 503
    assert ".env" in e.value.hint


def test_none_setting_disables(monkeypatch):
    _patch(monkeypatch, image_provider="none", openai_api_key="sk")
    assert ip.provider_status()["configured"] is False


def test_openai_edit_request_shape(keys):
    seen = {}
    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["ct"], seen["body"] = str(req.url), req.headers["authorization"], req.headers["content-type"], req.content
        return httpx.Response(200, json={"data": [{"b64_json": png_b64()}]})
    r = ip.OpenAIProvider(httpx.MockTransport(handler)).generate("a prompt", jpeg())
    assert seen["url"].endswith("/images/edits") and seen["auth"] == "Bearer sk-test"
    assert seen["ct"].startswith("multipart/form-data")
    assert b'name="image[]"' in seen["body"] and b"a prompt" in seen["body"] and b"gpt-image" in seen["body"]
    assert r.png_bytes[:4] == b"\x89PNG" and r.provider == "openai"


def test_openai_generation_without_reference_uses_json_endpoint(keys):
    seen = {}
    def handler(req):
        seen["url"], seen["json"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"data": [{"b64_json": png_b64()}]})
    ip.OpenAIProvider(httpx.MockTransport(handler)).generate("p", None)
    assert seen["url"].endswith("/images/generations") and seen["json"]["prompt"] == "p"


@pytest.mark.parametrize("status,code", [(401, "provider_auth_failed"), (429, "provider_rate_limited"), (500, "provider_error")])
def test_openai_http_errors_map_to_codes(keys, status, code):
    prov = ip.OpenAIProvider(httpx.MockTransport(lambda r: httpx.Response(status, json={"error": {"message": "nope"}})))
    with pytest.raises(ip.ImageProviderError) as e:
        prov.generate("p", None)
    assert e.value.code == code


def test_openai_moderation_block_is_distinct(keys):
    prov = ip.OpenAIProvider(httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": "blocked by safety system"}})))
    with pytest.raises(ip.ImageProviderError) as e:
        prov.generate("p", None)
    assert e.value.code == "provider_rejected_prompt"


def test_openai_timeout_mapped(keys):
    def boom(req): raise httpx.ReadTimeout("slow")
    with pytest.raises(ip.ImageProviderError) as e:
        ip.OpenAIProvider(httpx.MockTransport(boom)).generate("p", None)
    assert e.value.code == "provider_timeout" and e.value.status_code == 504


def test_gemini_request_and_camelcase_response(keys):
    seen = {}
    def handler(req):
        seen["url"], seen["key"], seen["json"] = str(req.url), req.headers["x-goog-api-key"], json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mime_type": "image/png", "data": png_b64()}}]}}]})
    r = ip.GeminiProvider(httpx.MockTransport(handler)).generate("p", jpeg())
    assert ":generateContent" in seen["url"] and seen["key"] == "g-test"
    assert seen["json"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
    assert any("inline_data" in p for p in seen["json"]["contents"][0]["parts"])
    assert r.provider == "gemini"


def test_gemini_text_only_reply_is_an_error_not_a_fake_image(keys):
    prov = ip.GeminiProvider(httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "I cannot"}]}}]})))
    with pytest.raises(ip.ImageProviderError) as e:
        prov.generate("p", None)
    assert e.value.code == "provider_no_image"


def test_image_size_follows_reference_aspect():
    from PIL import Image as I
    buf = BytesIO(); I.new("RGB", (100, 200)).save(buf, "JPEG")
    assert ip._image_size(buf.getvalue()) == "1024x1536"
    assert ip._image_size(None) == "1536x1024"

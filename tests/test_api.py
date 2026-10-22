"""API tests (FastAPI TestClient). Model-dependent paths use STUBS fed with the synthetic room
(see tests/synthetic_room.py) - they verify wiring and honesty, not real VGGT/YOLO inference."""
import base64
import time
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from app import image_providers as ip
from app import room_analyzer, vggt_service
from app.config import settings
from tests import synthetic_room as sr

client = TestClient(main.app)

# The exact request that produced the project's shipped response.json
LEGACY_BODY = {
    "room_type": "bedroom", "width": 4, "length": 3.5, "north_direction": "east",
    "compass_heading_degrees": 92, "manual_compass_direction": "east",
    "placements": [{"item": "bed", "x": 0.5, "y": 0.5, "width": 1.6, "length": 2},
                   {"item": "wardrobe", "x": 3, "y": 0.5, "width": 0.6, "length": 1.8}],
}


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_dirs()


def jpeg(w=518, h=518, color="gray"):
    buf = BytesIO(); Image.new("RGB", (w, h), color).save(buf, "JPEG"); return buf.getvalue()


def wait(job_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("job timed out")


# --------------------------------------------------------------------------- basics
def test_health_reports_honest_capabilities():
    h = client.get("/health").json()
    assert h["status"] == "healthy"
    caps = h["capabilities"]
    assert caps["geometry_reconstruction"]["available"] is False and "PyTorch" in caps["geometry_reconstruction"]["reason"]
    assert set(caps) == {"object_detection", "geometry_reconstruction", "image_generation"}


def test_no_duplicate_routes_or_models():
    paths = [(r.path, tuple(sorted(r.methods))) for r in main.app.routes if hasattr(r, "methods")]
    assert len(paths) == len(set(paths)), "duplicate route definitions"
    assert sum(1 for p, m in paths if p == "/room-layout/analyze") == 1


def test_cors_allows_vite_dev_and_lan_origins():
    for origin in ("http://localhost:5173", "http://192.168.1.20:5173"):
        r = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == origin
    r = client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


# --------------------------------------------------------------------------- legacy contracts
def test_room_layout_analyze_replays_shipped_request_and_keeps_old_keys():
    r = client.post("/room-layout/analyze", json=LEGACY_BODY)
    assert r.status_code == 200, r.text
    b = r.json()
    for key in ("status", "room_type", "dimensions_metres", "north_direction", "orientation_check", "coordinate_convention",
                "placements", "layout_status", "vastu_analysis", "floorplan_png_base64", "limitations"):
        assert key in b
    assert b["orientation_check"]["status"] == "confirmed_by_two_inputs"
    assert b["coordinate_convention"]["edges"] == {"top": "east", "right": "south", "bottom": "west", "left": "north"}
    assert b["vastu_analysis"]["coordinate_orientation"] == {"top": "east", "right": "south", "bottom": "west", "left": "north"}
    bed = next(x for x in b["vastu_analysis"]["results"] if x["item"] == "bed")
    assert bed["room_side"] == ["west", "north"] and bed["status"] == "review"     # same as the shipped response.json
    assert base64.b64decode(b["floorplan_png_base64"])[:4] == b"\x89PNG"
    assert b["vastu_report"]["room_summary"]["orientation"]["north_edge"] == "left"


def test_compass_disagreement_still_422_with_legacy_detail_shape():
    r = client.post("/room-layout/analyze", json={**LEGACY_BODY, "manual_compass_direction": "south"})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["orientation_check"]["compass_cardinal_direction"] == "east" and d["orientation_check"]["directions_match"] is False


def test_missing_orientation_is_rejected_not_defaulted():
    body = {k: v for k, v in LEGACY_BODY.items() if k not in ("north_direction", "compass_heading_degrees", "manual_compass_direction")}
    r = client.post("/room-layout/analyze", json=body)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "orientation_required"


def test_furniture_outside_room_rejected():
    body = {**LEGACY_BODY, "placements": [{"item": "bed", "x": 3.5, "y": 0.5, "width": 1.6, "length": 2}]}
    assert client.post("/room-layout/analyze", json=body).status_code == 400


@pytest.mark.parametrize("top,edges", [
    ("north", ("north", "east", "south", "west")), ("east", ("east", "south", "west", "north")),
    ("south", ("south", "west", "north", "east")), ("west", ("west", "north", "east", "south"))])
def test_every_orientation_flows_through_api(top, edges):
    body = {**LEGACY_BODY, "north_direction": None, "top_edge_direction": top,
            "compass_heading_degrees": None, "manual_compass_direction": None}
    b = client.post("/room-layout/analyze", json=body).json()
    conv = b["coordinate_convention"]["edges"]
    assert (conv["top"], conv["right"], conv["bottom"], conv["left"]) == edges
    assert b["vastu_analysis"]["coordinate_orientation"] == conv                # legacy summary agrees
    assert b["vastu_report"]["room_summary"]["orientation"]["edges"] == conv    # new engine agrees


def test_facing_direction_derives_top_edge_via_api():
    body = {k: v for k, v in LEGACY_BODY.items() if k not in ("north_direction", "compass_heading_degrees", "manual_compass_direction")}
    b = client.post("/room-layout/analyze", json={**body, "facing_direction": "east", "facing_edge": "right"}).json()
    assert b["top_edge_direction"] == "north"


def test_get_floorplan_png_pdf_and_alias():
    r = client.get("/floorplan", params={"top_edge_direction": "east"})
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert client.get("/floorplan", params={"north_direction": "east", "format": "pdf"}).content[:4] == b"%PDF"
    assert client.get("/floorplan", params={"width": 1}).status_code == 400


def test_post_floorplan_renders_structured_layout_with_openings():
    layout = {"room_type": "study_room", "width": 3.5, "length": 3, "orientation": {"facing_direction": "north", "facing_edge": "left"},
              "openings": [{"type": "window", "wall": "top", "offset": 1, "width": 1.2}],
              "placements": [{"item": "desk", "x": 0.2, "y": 0.2, "width": 1.2, "length": 0.6, "facing_edge": "bottom"}]}
    r = client.post("/floorplan", json={"layout": layout, "format": "png"})
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_vastu_analyze_both_forms():
    legacy = client.post("/vastu/analyze", json={"room_type": "bedroom", "placements": {"bed": "south", "wardrobe": "west"}}).json()
    assert [x["status"] for x in legacy["results"]] == ["preferred", "preferred"]
    layout = {"room_type": "kitchen", "width": 3, "length": 3, "orientation": {"top_edge_direction": "north"},
              "placements": [{"item": "stove", "x": 2.4, "y": 0.0, "width": 0.6, "length": 0.6, "facing_edge": "left"},
                             {"item": "sink", "x": 0.0, "y": 2.4, "width": 0.6, "length": 0.6}]}
    rep = client.post("/vastu/analyze", json={"layout": layout}).json()
    stove = next(r for r in rep["results"] if r["rule_id"] == "stove-zone")
    assert stove["observed"]["zone"] == "south_east" and stove["status"] == "satisfied"
    assert next(r for r in rep["results"] if r["rule_id"] == "stove-facing")["status"] == "violated"   # facing west
    assert client.post("/vastu/analyze", json={"room_type": "bedroom"}).status_code == 422


def test_vastu_missing_information_is_indeterminate_not_guessed():
    layout = {"room_type": "bedroom", "width": 4, "length": 3.5, "orientation": {"top_edge_direction": "north"},
              "placements": [{"item": "bed", "x": 1, "y": 0, "width": 1.6, "length": 2.0}]}      # no headboard edge recorded, no windows
    rep = client.post("/vastu/analyze", json={"layout": layout}).json()
    byid = {r["rule_id"]: r for r in rep["results"]}
    assert byid["bed-head-direction"]["status"] == "indeterminate"
    assert byid["window-light"]["status"] == "indeterminate"
    assert rep["summary"]["indeterminate"] >= 2


def test_vastu_rules_catalog_exposes_both_shapes():
    r = client.get("/vastu/rules").json()
    assert "bedroom" in r["rules"] and r["rule_catalog"] and "disclaimer" in r
    assert {"study_room", "dining_room"} <= set(r["available_room_types"])


# --------------------------------------------------------------------------- uploads
def test_upload_validation():
    assert client.post("/analyze-room", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post("/analyze-room", files={"file": ("a.jpg", b"", "image/jpeg")}).status_code == 400
    assert client.post("/analyze-room", files={"file": ("a.jpg", b"not an image", "image/jpeg")}).status_code == 400
    big = b"0" * (settings.max_image_bytes + 1)
    assert client.post("/analyze-room", files={"file": ("a.jpg", big, "image/jpeg")}).status_code == 413


def test_valid_image_reports_detection_unavailable_explicitly_here():
    r = client.post("/analyze-room", files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "detection_unavailable"


def test_analysis_job_rejects_bad_metadata_and_too_many_photos():
    f = [("files", ("a.jpg", jpeg(), "image/jpeg"))]
    assert client.post("/room-analysis/jobs", files=f, data={"metadata": "{not json"}).status_code == 400
    assert client.post("/room-analysis/jobs", files=f, data={"metadata": '{"room_type":"castle"}'}).status_code == 400
    many = [("files", (f"{i}.jpg", jpeg(64, 64), "image/jpeg")) for i in range(settings.max_room_images + 1)]
    assert client.post("/room-analysis/jobs", files=many, data={"metadata": '{"room_type":"bedroom"}'}).status_code == 400
    conflict = '{"room_type":"bedroom","orientation":{"top_edge_direction":"north","facing_direction":"east","facing_edge":"top"}}'
    r = client.post("/room-analysis/jobs", files=f, data={"metadata": conflict})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "orientation_conflict"


# --------------------------------------------------------------------------- job pipeline: honest fallback
def test_job_without_models_falls_back_to_user_dimensions_and_says_so():
    files = [("files", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(3)]
    meta = ('{"room_type":"bedroom","width":4,"length":3.5,"orientation":{"top_edge_direction":"east"},'
            '"furniture":[{"id":"bed-1","item":"bed","source":"detected"}]}')
    r = client.post("/room-analysis/jobs", files=files, data={"metadata": meta})
    assert r.status_code == 202
    job = wait(r.json()["job_id"])
    assert job["status"] == "succeeded"
    res = job["result"]
    assert res["geometry_status"] == "not_reconstructed" and res["layout_status"] == "manual_dimensions"
    assert res["room"] == {"width": 4.0, "length": 3.5, "dimensions_source": "user_provided"}
    assert res["placements"] == [] and res["unplaced"][0]["id"] == "bed-1"          # no guessed position
    assert res["orientation"]["edges"]["left"] == "north"
    stages = {s["key"]: s for s in job["stages"]}
    assert stages["reconstruction"]["status"] == "skipped" and "PyTorch" in stages["reconstruction"]["detail"]
    assert stages["detection"]["status"] == "skipped"
    assert any("did not run" in w for w in res["warnings"])


def test_job_without_dimensions_demands_manual_input():
    r = client.post("/room-analysis/jobs", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))], data={"metadata": '{"room_type":"bedroom"}'})
    res = wait(r.json()["job_id"])["result"]
    assert res["room"] is None and res["layout_status"] == "needs_manual_input" and res["orientation"] is None


def test_unknown_job_is_404():
    assert client.get("/jobs/deadbeefdeadbeef").status_code == 404


# --------------------------------------------------------------------------- job pipeline with STUBBED models
def test_full_pipeline_wiring_with_stubbed_vggt_and_yolo(monkeypatch):
    cams = [(2.5, 0.35, 0, 1.4), (0.35, 0.35, 45, 1.4), (4.65, 0.35, 315, 1.4), (4.65, 3.65, 225, 1.4),
            (0.35, 3.65, 135, 1.4), (2.5, 3.65, 180, 1.4), (4.65, 2.0, 270, 1.4), (0.35, 2.0, 90, 1.4)]
    pts, conf, valid, ext, bed_masks = sr.build_multi_position(cams, size=518)
    out = vggt_service.VGGTOutput(points=pts, conf=conf, valid=valid, extrinsics=ext, intrinsics=np.zeros((8, 3, 3)),
                                  mappings=[vggt_service.pad_mapping(518, 518)] * 8, device="stub")
    monkeypatch.setattr(vggt_service, "availability", lambda: {"available": True, "reason": None})
    monkeypatch.setattr(vggt_service, "run_vggt", lambda paths, sizes: out)
    monkeypatch.setattr(room_analyzer, "detection_available", lambda: (True, None))
    calls = iter(range(8))

    def fake_detect(arr, conf=0.25):
        i = next(calls)
        m = bed_masks[i]
        if m.sum() < 40:
            return []
        ys, xs = np.where(m)
        return [{"label": "bed", "confidence": 0.9, "bounding_box": {"x_min": float(xs.min()), "y_min": float(ys.min()), "x_max": float(xs.max() + 1), "y_max": float(ys.max() + 1)}}]
    monkeypatch.setattr(room_analyzer, "detect_objects", fake_detect)

    files = [("files", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(8)]
    meta = ('{"room_type":"bedroom","width":5,"length":4,"orientation":{"facing_direction":"north","facing_edge":"top"},'
            '"furniture":[{"id":"bed-1","item":"bed","source":"detected"},{"id":"desk-1","item":"desk","source":"user_added"},'
            '{"id":"plant-1","item":"plant","source":"user_added","x":4.0,"y":0.2}]}')
    r = client.post("/room-analysis/jobs", files=files, data={"metadata": meta})
    job = wait(r.json()["job_id"])
    assert job["status"] == "succeeded", job.get("error")
    res = job["result"]
    assert res["geometry_status"] == "reconstructed" and res["reconstruction_completeness"] == "partial_estimate"
    assert res["room"]["width"] == 5.0 and res["room"]["length"] == 4.0
    assert res["geometry"]["confidence"] == "medium"
    placed = {p["id"]: p for p in res["placements"]}
    assert placed["bed-1"]["position_source"] == "reconstructed"
    cx, cy = placed["bed-1"]["x"] + placed["bed-1"]["width"] / 2, placed["bed-1"]["y"] + placed["bed-1"]["length"] / 2
    assert np.hypot(cx - 1.4, cy - 2.2) < 0.9                                      # sub-metre, as documented
    assert placed["plant-1"]["position_source"] == "user" and placed["plant-1"]["x"] == 4.0
    assert [u["id"] for u in res["unplaced"]] == ["desk-1"]                         # never seen -> not invented
    assert all(s["status"] == "done" for s in job["stages"])
    assert any("estimates from the photos" in w for w in res["warnings"])


def test_vggt_failure_is_reported_and_pipeline_falls_back(monkeypatch):
    monkeypatch.setattr(vggt_service, "availability", lambda: {"available": True, "reason": None})
    def boom(paths, sizes): raise RuntimeError("CUDA out of memory")
    monkeypatch.setattr(vggt_service, "run_vggt", boom)
    files = [("files", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(2)]
    r = client.post("/room-analysis/jobs", files=files, data={"metadata": '{"room_type":"bedroom","width":4,"length":3}'})
    job = wait(r.json()["job_id"])
    assert job["status"] == "succeeded"
    assert next(s for s in job["stages"] if s["key"] == "reconstruction")["status"] == "failed"
    assert job["result"]["geometry_status"] == "not_reconstructed" and "CUDA out of memory" in job["result"]["reconstruction_unavailable_reason"]


# --------------------------------------------------------------------------- redesign
PLAN_REQ = {
    "layout": {"room_type": "bedroom", "width": 4, "length": 3.5, "orientation": {"top_edge_direction": "east"},
               "openings": [{"type": "door", "wall": "bottom", "offset": 2.6, "width": 0.9, "is_main_entrance": True},
                            {"type": "window", "wall": "top", "offset": 1.2, "width": 1.4}],
               "placements": [{"id": "bed-1", "item": "bed", "x": 0.5, "y": 0.5, "width": 1.6, "length": 2.0, "headboard_edge": "left"},
                              {"id": "wardrobe-1", "item": "wardrobe", "x": 3.0, "y": 0.5, "width": 0.6, "length": 1.8}]},
    "preferences": {"style": "scandinavian", "add": ["desk"]},
}


def test_redesign_plan_floorplan_retrieval_and_persistence():
    spec = client.post("/redesign/plan", json=PLAN_REQ).json()
    rid = spec["id"]
    assert spec["proposed_layout"]["placements"] and spec["vastu"]["after"]["violated"] <= spec["vastu"]["before"]["violated"]
    assert client.get(f"/redesign/{rid}").json()["id"] == rid
    for which in ("proposed", "current"):
        r = client.get(f"/redesign/{rid}/floorplan", params={"which": which})
        assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert client.get(f"/redesign/{rid}/floorplan", params={"format": "pdf"}).content[:4] == b"%PDF"
    assert client.get("/redesign/00000000000000ff").status_code == 404
    assert client.get("/redesign/../etc/passwd").status_code in (404, 422)


def test_visualize_without_provider_is_explicit_503_not_a_fake(monkeypatch):
    for k in ("openai_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, k, "")
    rid = client.post("/redesign/plan", json=PLAN_REQ).json()["id"]
    r = client.post(f"/redesign/{rid}/visualize")
    assert r.status_code == 503
    d = r.json()["detail"]
    assert d["code"] == "image_provider_not_configured" and ".env" in d["hint"]
    assert client.get(f"/redesign/{rid}/visualization.png").status_code == 404


class FakeProvider(ip.ImageProvider):
    """MOCK - returns a flat grey PNG. Proves job plumbing/persistence; is NOT AI output."""
    name, model = "fake", "fake-1"
    def __init__(self): self.prompt = self.ref = None
    def generate(self, prompt, reference_jpeg):
        self.prompt, self.ref = prompt, reference_jpeg
        buf = BytesIO(); Image.new("RGB", (16, 16), "gray").save(buf, "PNG")
        return ip.ImageResult(buf.getvalue(), "fake", "fake-1")


def test_visualize_job_uses_same_spec_and_persists(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ip, "get_provider", lambda transport=None: fake)
    spec = client.post("/redesign/plan", json=PLAN_REQ).json()
    rid = spec["id"]
    r = client.post(f"/redesign/{rid}/visualize", files={"reference_image": ("room.jpg", jpeg(300, 200), "image/jpeg")})
    assert r.status_code == 202
    job = wait(r.json()["job_id"])
    assert job["status"] == "succeeded"
    assert fake.ref is not None and fake.ref[:2] == b"\xff\xd8"
    # prompt is derived from the SAME stored spec as the floor plan
    for p in spec["proposed_layout"]["placements"]:
        assert p["label"].split()[0] in fake.prompt
    viz = client.get(f"/redesign/{rid}").json()["visualization"]
    assert viz["provider"] == "fake" and "AI-generated visual proposal" in viz["disclaimer"]
    assert client.get(f"/redesign/{rid}/visualization.png").content[:4] == b"\x89PNG"


def test_provider_failure_surfaces_in_job_error(monkeypatch):
    class Boom(FakeProvider):
        def generate(self, prompt, ref): raise ip.ImageProviderError("provider_rate_limited", "quota", 429, "wait")
    monkeypatch.setattr(ip, "get_provider", lambda transport=None: Boom())
    rid = client.post("/redesign/plan", json=PLAN_REQ).json()["id"]
    job = wait(client.post(f"/redesign/{rid}/visualize").json()["job_id"])
    assert job["status"] == "failed" and job["error"]["code"] == "provider_rate_limited" and job["error"]["hint"] == "wait"
    assert client.get(f"/redesign/{rid}").json()["visualization"] is None          # failed run leaves no fake result

"""Geometry tests on a SYNTHETIC ray-cast room (validates the math, not VGGT itself)."""
import numpy as np
import pytest

from app import geometry as g
from tests import synthetic_room as sr

YAWS_8 = [0, 45, 90, 135, 180, 225, 270, 315]


def _run(yaws, **kw):
    pts, conf, valid, ext, bed = sr.build(yaws, **kw)
    return pts, conf, valid, ext, bed


def test_extrinsics_helpers_are_consistent():
    pts, conf, valid, ext, bed = _run([0, 90])
    c = g.camera_centers(ext)
    assert np.allclose(c[0], 0)                       # camera 0 is the origin
    assert np.allclose(g.camera_forward_world(ext)[0], [0, 0, 1])
    assert np.allclose(g.camera_up_world(ext)[0], [0, -1, 0])


def test_recovers_room_with_user_dimensions_facing_north():
    pts, conf, valid, ext, _ = _run(YAWS_8)
    res, recon = g.reconstruct_room(pts, conf, valid, ext, user_width=5.0, user_length=4.0)
    room = res["room"]
    # Reference camera faces north => plan x = east-west (5 m), plan y = north-south (4 m).
    assert (room["width"], room["length"]) == (5.0, 4.0)
    assert room["dimensions_source"] == "user_provided"
    assert room["dimensions_assignment"] == "as_entered"
    assert res["metrics"]["perimeter_coverage"] >= 0.9
    assert res["confidence"] == "medium"
    assert not res["warnings"]
    # Scale: reconstruction used scale 0.4, so metres/unit should be ~ 1/0.4 = 2.5
    assert room["scale_metres_per_unit"] == pytest.approx(2.5, rel=0.08)


def test_recovers_dimensions_without_user_input_but_flags_estimate():
    pts, conf, valid, ext, _ = _run(YAWS_8)
    res, _ = g.reconstruct_room(pts, conf, valid, ext)
    room = res["room"]
    assert room["dimensions_source"] == "estimated"
    # camera really is 1.4 m high => estimate should be near truth (within 10%)
    assert room["width"] == pytest.approx(5.0, rel=0.10)
    assert room["length"] == pytest.approx(4.0, rel=0.10)
    assert any("scale assumes" in w for w in res["warnings"])
    assert res["confidence"] == "low"            # estimated scale can never be 'medium'


def test_reference_camera_facing_east_swaps_axes():
    """If photo 1 faces east, the plan's top edge is the east wall: plan width is the N-S extent."""
    yaws = [90, 135, 180, 225, 270, 315, 0, 45]
    pts, conf, valid, ext, _ = _run(yaws)
    res, _ = g.reconstruct_room(pts, conf, valid, ext, user_width=5.0, user_length=4.0)
    room = res["room"]
    assert room["dimensions_assignment"] == "swapped"
    assert (room["width"], room["length"]) == (4.0, 5.0)


def test_mismatched_user_dimensions_are_flagged_not_hidden():
    pts, conf, valid, ext, _ = _run(YAWS_8)
    res, _ = g.reconstruct_room(pts, conf, valid, ext, user_width=3.0, user_length=6.0)
    assert any("differ from your entered dimensions" in w for w in res["warnings"])


def test_sparse_coverage_lowers_confidence_and_warns():
    pts, conf, valid, ext, _ = _run([0, 20])      # two nearly parallel photos of one wall
    try:
        res, _ = g.reconstruct_room(pts, conf, valid, ext, user_width=5.0, user_length=4.0)
    except g.GeometryError:
        return                                     # refusing to reconstruct is also acceptable
    assert res["confidence"] == "low"
    assert res["warnings"]


def test_localizes_bed_in_plan_coordinates():
    """Cameras in the four corners looking inward (photo 1 faces north) - a realistic capture pattern."""
    cams = [(2.5, 0.35, 0, 1.4), (0.35, 0.35, 45, 1.4), (4.65, 0.35, 315, 1.4),
            (4.65, 3.65, 225, 1.4), (0.35, 3.65, 135, 1.4), (2.5, 3.65, 180, 1.4),
            (4.65, 2.0, 270, 1.4), (0.35, 2.0, 90, 1.4)]
    pts, conf, valid, ext, bed_masks = sr.build_multi_position(cams)
    res, recon = g.reconstruct_room(pts, conf, valid, ext, user_width=5.0, user_length=4.0)
    assert (res["room"]["width"], res["room"]["length"]) == (5.0, 4.0)
    centers = g.camera_centers(ext)
    true_centre = np.array([(0.6 + 2.2) / 2, (1.2 + 3.2) / 2])
    found = []
    for i in range(len(cams)):
        mask = bed_masks[i]
        if mask.sum() < 40:
            continue
        ys, xs = np.where(mask)
        det = g.localize_detection(recon, pts[i], conf[i], valid[i], (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), "bed", centers[i])
        if det:
            found.append((i, det))
    assert len(found) >= 3, "bed should be seen from several corners"
    errs = [np.hypot(d["x"] - true_centre[0], d["y"] - true_centre[1]) for _, d in found]
    merged = g.merge_candidates([{**d, "item": "bed", "seen_in": [i]} for i, d in found])
    best = min(np.hypot(m["x"] - true_centre[0], m["y"] - true_centre[1]) for m in merged)
    # Honest expectation for single-view monocular localisation: sub-metre, not centimetres.
    assert np.median(errs) < 0.8, f"per-view median error {np.median(errs):.2f} m"
    assert len(merged) <= 2
    assert best < 0.6, f"merged bed centre error {best:.2f} m"


def test_footprint_stays_inside_room_and_aligns_to_wall():
    fp = g.place_footprint("bed", 0.2, 2.0, 5.0, 4.0)       # bed centre near the left wall
    assert fp["x"] >= 0 and fp["x"] + fp["width"] <= 5.0 and fp["y"] + fp["length"] <= 4.0
    assert fp["length"] > fp["width"]                       # long side parallel to the nearby left wall


def test_too_little_data_raises_clear_error():
    pts = np.zeros((2, 4, 4, 3)); conf = np.ones((2, 4, 4)); valid = np.ones((2, 4, 4), bool)
    ext = np.stack([np.hstack([np.eye(3), np.zeros((3, 1))])] * 2)
    with pytest.raises(g.GeometryError):
        g.reconstruct_room(pts, conf, valid, ext)

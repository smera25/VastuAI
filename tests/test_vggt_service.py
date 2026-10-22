import numpy as np
from app import vggt_service as vs


def test_pad_mapping_matches_vggt_arithmetic_landscape_and_portrait():
    # 1200x800 landscape: width->518, height 800*(518/1200)=345.3 -> round(24.66)*14 = 350
    m = vs.pad_mapping(1200, 800)
    assert (m.new_w, m.new_h) == (518, 350)
    assert (m.pad_left, m.pad_top) == (0, 84)
    # portrait 800x1200: mirror image
    p = vs.pad_mapping(800, 1200)
    assert (p.new_w, p.new_h) == (350, 518) and (p.pad_left, p.pad_top) == (84, 0)


def test_valid_mask_and_bbox_mapping_are_consistent():
    m = vs.pad_mapping(1200, 800)
    mask = m.valid_mask()
    assert mask.sum() == 518 * 350
    # the image's own corners must land on the valid region's corners
    x1, y1, x2, y2 = m.bbox(0, 0, 1200, 800)
    assert (round(x1), round(y1)) == (0, 84) and (round(x2), round(y2)) == (518, 434)
    assert mask[int(y1) + 1, int(x1) + 1] and mask[int(y2) - 1, int(x2) - 1]


def test_availability_reports_precise_reason_when_torch_missing():
    info = vs.availability()
    assert info["available"] is False          # no torch in this environment
    assert "PyTorch" in info["reason"]


def test_run_refuses_rather_than_fabricating():
    import pytest
    with pytest.raises(RuntimeError):
        vs.run_vggt([], [])

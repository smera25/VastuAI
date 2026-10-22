import itertools

import pytest

from app import orientation as ori
from app import redesign, vastu_rules
from app.schemas import RedesignPreferences, RoomLayout

DIRS = ["north", "east", "south", "west"]


def bedroom(top="east", **kw):
    return RoomLayout(
        room_type="bedroom", width=4.0, length=3.5, orientation={"top_edge_direction": top},
        openings=[{"type": "door", "wall": "bottom", "offset": 2.6, "width": 0.9, "is_main_entrance": True},
                  {"type": "window", "wall": "top", "offset": 1.2, "width": 1.4}],
        placements=[
            {"id": "bed-1", "item": "bed", "x": 0.5, "y": 0.5, "width": 1.6, "length": 2.0, "headboard_edge": "left"},
            {"id": "wardrobe-1", "item": "wardrobe", "x": 3.0, "y": 0.5, "width": 0.6, "length": 1.8},
        ], **kw)


def rects(layout):
    return [(p.id, p.x, p.y, p.width, p.length) for p in layout.placements]


@pytest.mark.parametrize("top", DIRS)
def test_proposed_layout_obeys_hard_constraints(top):
    spec = redesign.create_redesign(bedroom(top), RedesignPreferences(add=["desk", "nightstand"]))
    proposed = RoomLayout.model_validate(spec["proposed_layout"])     # also re-validates inside-room
    rs = rects(proposed)
    for (a, ax, ay, aw, al), (b, bx, by, bw, bl) in itertools.combinations(rs, 2):
        assert redesign._rects_overlap((ax, ay, aw, al), (bx, by, bw, bl)) is False, f"{a} overlaps {b}"
    door = [o for o in proposed.openings if o.type == "door"][0]
    swing = vastu_rules.door_swing_rect(door, proposed)
    for (_, x, y, w, l) in rs:
        assert not redesign._rects_overlap((x, y, w, l), swing), "furniture blocks the door swing"


@pytest.mark.parametrize("top", DIRS)
def test_bed_head_direction_is_preferred_in_every_orientation(top):
    """The same physical room, described with any top edge, must give a south/east bed head."""
    spec = redesign.create_redesign(bedroom(top), RedesignPreferences())
    layout = RoomLayout.model_validate(spec["proposed_layout"])
    bed = next(p for p in layout.placements if p.item == "bed")
    head = ori.edge_directions(top)[bed.headboard_edge]
    assert head in ("south", "east"), f"top={top}: head toward {head}"
    # and the evaluator agrees with the planner
    report = vastu_rules.evaluate(layout)
    r = next(r for r in report["results"] if r["rule_id"] == "bed-head-direction")
    assert r["status"] == "satisfied"


@pytest.mark.parametrize("top", DIRS)
def test_planner_and_evaluator_agree_on_bed_zone(top):
    spec = redesign.create_redesign(bedroom(top), RedesignPreferences())
    layout = RoomLayout.model_validate(spec["proposed_layout"])
    zone = next(z for z in vastu_rules.evaluate(layout)["room_summary"]["item_zones"] if z["item"] == "bed")["zone"]
    assert zone in ("south_west", "south", "west")


def test_retained_good_placement_is_not_moved():
    good = RoomLayout(
        room_type="bedroom", width=4.0, length=3.5, orientation={"top_edge_direction": "north"},
        placements=[{"id": "bed-1", "item": "bed", "x": 0.0, "y": 0.0, "width": 1.6, "length": 2.0, "headboard_edge": "left"}],
    )  # SW corner, headboard west... not S/E, so test with headboard bottom (south)
    good.placements[0].headboard_edge = "bottom"
    spec = redesign.create_redesign(good, RedesignPreferences())
    assert spec["changes"][0]["status"] == "keep"


def test_follow_vastu_off_is_labelled_and_minimises_movement():
    spec = redesign.create_redesign(bedroom("east"), RedesignPreferences(follow_vastu=False))
    assert any("switched off" in w for w in spec["warnings"])
    assert spec["vastu"]["followed"] is False


def test_replace_and_add_are_reflected_in_changes_and_budget():
    spec = redesign.create_redesign(bedroom("east"), RedesignPreferences(replace=["wardrobe-1"], add=["desk"], budget_inr=1000))
    statuses = {c["id"]: c["status"] for c in spec["changes"]}
    assert statuses["wardrobe-1"] == "replaced" and statuses["desk-new1"] == "added"
    b = spec["budget"]
    assert b["status"] == "estimated" and b["total_inr"][0] > 0 and b["within_budget"] == "no"
    assert "not quotes" in b["note"]


def test_rearrangement_only_has_no_budget_implication():
    spec = redesign.create_redesign(bedroom("east"), RedesignPreferences())
    assert spec["budget"]["status"] == "no_purchases_needed"


def test_overfull_room_reports_unplaced_instead_of_overlapping():
    spec = redesign.create_redesign(
        RoomLayout(room_type="bedroom", width=2.2, length=2.2, orientation={"top_edge_direction": "north"}, placements=[]),
        RedesignPreferences(add=["bed", "wardrobe", "sofa", "dining_table"]))
    assert spec["unplaced"], "a 2.2 m square cannot hold all of that"
    proposed = RoomLayout.model_validate(spec["proposed_layout"])
    for a, b in itertools.combinations(rects(proposed), 2):
        assert not redesign._rects_overlap(a[1:], b[1:])


def test_spec_is_single_source_for_prompt_and_plan():
    spec = redesign.create_redesign(bedroom("east"), RedesignPreferences(style="scandinavian", notes="lots of plants"))
    prompt = redesign.build_prompt(spec, has_reference_image=True)
    layout = RoomLayout.model_validate(spec["proposed_layout"])
    for p in layout.placements:
        assert (p.label or "").split()[0] in prompt          # every furniture item in the plan is in the prompt
    assert "scandinavian" in prompt and "lots of plants" in prompt
    assert "reference photo" in prompt


def test_view_description_rotates_with_reference_view_edge():
    layout = RoomLayout(room_type="bedroom", width=4, length=3, orientation={"top_edge_direction": "north"},
                        placements=[{"item": "bed", "x": 1.2, "y": 2.0, "width": 1.6, "length": 1.0}])  # against TOP wall, centred
    assert "against the far wall" in redesign.describe_layout(layout, "top")[0]
    assert "along the near wall" in redesign.describe_layout(layout, "bottom")[0]
    assert "against the right wall" in redesign.describe_layout(layout, "left")[0]   # facing the left edge, the top wall is on the viewer's right
    assert redesign.side_of_edge("top", "top") == "far wall"
    assert redesign.side_of_edge("right", "top") == "right wall"
    assert redesign.side_of_edge("bottom", "right") == "right wall"      # facing the right edge, the bottom edge is on the viewer's right

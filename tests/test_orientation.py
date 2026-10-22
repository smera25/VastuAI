"""Orientation mapping tests - all four cardinal orientations, every dependent calculation."""
import json
from pathlib import Path

import pytest

from app import orientation as o

CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "shared" / "orientation-cases.json").read_text()
)
CLOCKWISE = ["north", "east", "south", "west"]


@pytest.mark.parametrize("case", CASES["top_edge_cases"], ids=lambda c: f"top={c['top']}")
def test_edge_labels_match_ground_truth(case):
    edges = o.edge_directions(case["top"])
    assert edges == {k: case[k] for k in ("top", "right", "bottom", "left")}
    assert o.north_edge(case["top"]) == case["north_edge"]
    assert o.north_arrow_rotation_degrees(case["top"]) == case["north_arrow_degrees"]


@pytest.mark.parametrize("top", CLOCKWISE)
def test_clockwise_sequence_and_bijection(top):
    edges = o.edge_directions(top)
    seq = [edges[e] for e in ("top", "right", "bottom", "left")]
    start = CLOCKWISE.index(top)
    assert seq == [CLOCKWISE[(start + i) % 4] for i in range(4)]
    assert sorted(seq) == sorted(CLOCKWISE)  # every direction appears exactly once


@pytest.mark.parametrize("top", CLOCKWISE)
def test_inverse_mapping_roundtrip(top):
    for edge, direction in o.edge_directions(top).items():
        assert o.edge_for_direction(top, direction) == edge


def test_brief_example_top_is_east():
    assert o.edge_directions("east") == {
        "top": "east", "right": "south", "bottom": "west", "left": "north"
    }


@pytest.mark.parametrize("case", CASES["facing_cases"], ids=lambda c: f"{c['facing']}@{c['facing_edge']}")
def test_top_edge_from_facing(case):
    assert o.top_edge_from_facing(case["facing"], case["facing_edge"]) == case["expected_top"]
    # The faced edge must then be labelled with the direction faced.
    top = case["expected_top"]
    assert o.edge_directions(top)[case["facing_edge"]] == case["facing"]


@pytest.mark.parametrize("case", CASES["zone_cases"], ids=lambda c: str(c["point"]))
@pytest.mark.parametrize("top", CLOCKWISE)
def test_zone_for_point_follows_orientation(case, top):
    room = CASES["zone_room"]
    x, y = case["point"]
    assert o.zone_for_point(x, y, room["width"], room["length"], top) == case["by_top"][top]


@pytest.mark.parametrize("case", CASES["heading_cases"], ids=lambda c: str(c["heading"]))
def test_heading_to_cardinal(case):
    assert o.heading_to_cardinal(case["heading"]) == case["cardinal"]


def test_changing_orientation_changes_every_dependent_value():
    """The same physical plan point must land in four different zones as the top edge rotates."""
    zones = {t: o.zone_for_point(0.5, 2.5, 4, 3, t) for t in CLOCKWISE}
    assert len(set(zones.values())) == 4
    arrows = {t: o.north_arrow_rotation_degrees(t) for t in CLOCKWISE}
    assert len(set(arrows.values())) == 4


def test_wall_zone_uses_same_mapping():
    # Door in the middle of the plan's LEFT wall; with top=east the left wall is north.
    assert o.wall_zone("left", 1.5, 4, 3, "east") == "north"
    assert o.wall_zone("top", 2.0, 4, 3, "east") == "east"
    assert o.wall_zone("bottom", 2.0, 4, 3, "east") == "west"
    assert o.wall_zone("right", 1.5, 4, 3, "east") == "south"


def test_resolve_from_top_edge_and_alias():
    assert o.resolve_orientation(top_edge_direction="east").top_edge_direction == "east"
    assert o.resolve_orientation(north_direction="east").top_edge_direction == "east"  # legacy alias


def test_resolve_from_facing():
    r = o.resolve_orientation(facing_direction="east", facing_edge="right")
    assert r.top_edge_direction == "north"
    assert r.edges["right"] == "east"


def test_resolve_agreeing_inputs_ok_and_contradiction_raises():
    ok = o.resolve_orientation(top_edge_direction="north", facing_direction="east", facing_edge="right")
    assert ok.top_edge_direction == "north"
    with pytest.raises(o.OrientationConflict):
        o.resolve_orientation(top_edge_direction="south", facing_direction="east", facing_edge="top")


def test_resolve_requires_something():
    with pytest.raises(o.OrientationError):
        o.resolve_orientation()


def test_compass_heading_must_match_manual_direction():
    r = o.resolve_orientation(top_edge_direction="east", heading_degrees=92, manual_compass_direction="east")
    assert r.source == "device_compass"
    with pytest.raises(o.OrientationConflict) as exc:
        o.resolve_orientation(top_edge_direction="east", heading_degrees=92, manual_compass_direction="south")
    assert exc.value.details["compass_cardinal_direction"] == "east"
    with pytest.raises(o.OrientationError):
        o.resolve_orientation(top_edge_direction="east", heading_degrees=92)  # no manual confirmation


def test_invalid_values_rejected():
    for bad in ("up", "", "NORTHEAST"):
        with pytest.raises(o.OrientationError):
            o.normalize_direction(bad)
    with pytest.raises(o.OrientationError):
        o.normalize_edge("middle")


@pytest.mark.parametrize("top", CLOCKWISE)
def test_plan_cell_for_zone_is_inverse_of_zone_for_point(top):
    room_w, room_l = 6.0, 6.0
    for zone in o.ZONES:
        col, row = o.plan_cell_for_zone(zone, top)
        x = room_w / 2 + col * room_w / 3
        y = room_l / 2 + row * room_l / 3
        assert o.zone_for_point(x, y, room_w, room_l, top) == zone


def test_zone_description_for_top_east():
    # With top=east, the north-west zone sits in the bottom... verify by hand:
    # left=north, bottom=west  =>  north-west = bottom-left corner.
    assert o.describe_plan_cell(*o.plan_cell_for_zone("north_west", "east")) == "bottom-left corner"
    # south-east = top-right corner (top=east, right=south).
    assert o.describe_plan_cell(*o.plan_cell_for_zone("south_east", "east")) == "top-right corner"

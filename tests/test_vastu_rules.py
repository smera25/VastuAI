"""Rules are data: they can be overridden, disabled and extended from a JSON file."""
import json

import pytest

from app import vastu_rules
from app.schemas import RoomLayout


def living(placements):
    return RoomLayout(room_type="living_room", width=4, length=4, orientation={"top_edge_direction": "north"}, placements=placements)


def test_override_file_changes_disables_and_adds_rules(tmp_path, monkeypatch):
    f = tmp_path / "rules.json"
    f.write_text(json.dumps([
        {"id": "tv-zone", "enabled": False},
        {"id": "seating-zone", "preferred": ["north"]},
        {"id": "custom-plant", "title": "Plants east", "category": "vastu", "rooms": ["*"], "items": ["plant"], "kind": "item_zone",
         "preferred": ["east"], "avoid": [], "reason": "custom", "consensus": "custom"},
    ]))
    monkeypatch.setenv("VASTU_RULES_FILE", str(f))
    ids = {r["id"] for r in vastu_rules.load_rules()}
    assert "tv-zone" not in ids and "custom-plant" in ids
    layout = living([{"id": "s", "item": "sofa", "x": 1.5, "y": 3.0, "width": 1.0, "length": 0.8},     # top-middle = north
                     {"id": "t", "item": "tv_unit", "x": 0.0, "y": 0.0, "width": 1.0, "length": 0.4},
                     {"id": "p", "item": "plant", "x": 0.0, "y": 1.8, "width": 0.4, "length": 0.4}])  # west
    byid = {(r["rule_id"]): r for r in vastu_rules.evaluate(layout)["results"]}
    assert byid["seating-zone"]["status"] == "satisfied"            # overridden preference (north) now applies
    assert "tv-zone" not in byid                                      # disabled
    assert byid["custom-plant"]["status"] == "violated"              # new rule evaluated


def test_broken_override_file_fails_loudly(tmp_path, monkeypatch):
    f = tmp_path / "bad.json"; f.write_text("{not json")
    monkeypatch.setenv("VASTU_RULES_FILE", str(f))
    with pytest.raises(RuntimeError):
        vastu_rules.load_rules()


def test_shipped_example_file_is_valid(monkeypatch):
    monkeypatch.setenv("VASTU_RULES_FILE", "config/vastu_rules.example.json")
    ids = {r["id"] for r in vastu_rules.load_rules()}
    assert "pooja-corner-zone" in ids and "tv-zone" not in ids


def test_every_rule_has_reason_and_consensus_and_valid_zones():
    from app import orientation as ori
    for r in vastu_rules.DEFAULT_RULES:
        assert r["reason"] and r["consensus"] and r["category"] in ("vastu", "practical")
        for z in r.get("preferred", []) + r.get("avoid", []):
            assert z in ori.ZONES or z in ori.CARDINALS


def test_zone_rules_never_prefer_and_avoid_the_same_zone():
    for r in vastu_rules.DEFAULT_RULES:
        assert not set(r.get("preferred", [])) & set(r.get("avoid", [])), r["id"]

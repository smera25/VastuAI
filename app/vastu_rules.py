"""
Structured, configurable Vastu rules engine.

Vastu is treated here as a *traditional design framework*, not a validated
science, and not every school agrees on every rule. Each rule therefore carries
a ``consensus`` note and a plain-language ``reason`` - the engine never invents
citations. Rules are plain data; deployments can disable or override them with
a JSON file (``VASTU_RULES_FILE``) without touching code.

Result statuses
---------------
satisfied      the evaluated placement matches the rule
violated       the placement conflicts with the rule (``severity`` minor|major)
indeterminate  required information is missing - the rule is NOT guessed
Each violated/indeterminate finding also carries ``requires_confirmation``
(true when the evidence is estimated rather than user-confirmed).

All directions flow through ``app.orientation`` - no direction logic lives here.
"""
from __future__ import annotations

import json
import logging
import math
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from app import orientation as ori
from app.furniture import display_label, is_heavy
from app.schemas import RoomLayout

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Vastu Shastra is a traditional design framework. These checks encode commonly "
    "cited guidance, are not scientifically established requirements, and are not "
    "universally agreed upon between schools. Treat them as configurable preferences "
    "and always prioritise safety, accessibility and the real constraints of the room."
)

# ---------------------------------------------------------------------------
# Default rule set (data, not code)
# ---------------------------------------------------------------------------
# kind: item_zone | head_direction | facing_direction | opening_zone |
#       any_opening_zone | heavy_zone_avoid | separation | door_clearance
# `rooms` = ["*"] means every room type. `consensus` is shown to the user.

DEFAULT_RULES: list[dict[str, Any]] = [
    # ---- bedroom ---------------------------------------------------------
    {
        "id": "bed-head-direction", "title": "Bed head direction", "category": "vastu",
        "rooms": ["bedroom"], "items": ["bed", "single_bed"], "kind": "head_direction",
        "preferred": ["south", "east"], "avoid": ["north"],
        "reason": "Traditional guidance commonly recommends sleeping with the head toward the south or east, and avoiding north.",
        "consensus": "Widely cited; some schools also accept west.",
    },
    {
        "id": "bed-zone", "title": "Bed placement zone", "category": "vastu",
        "rooms": ["bedroom"], "items": ["bed", "single_bed"], "kind": "item_zone",
        "preferred": ["south_west", "south", "west"], "avoid": ["north_east", "center"],
        "reason": "The south-west is traditionally associated with stability and rest; the north-east and the centre are usually kept light and open.",
        "consensus": "Widely cited for primary bedrooms.",
    },
    {
        "id": "wardrobe-zone", "title": "Heavy storage zone", "category": "vastu",
        "rooms": ["bedroom"], "items": ["wardrobe", "dresser", "storage"], "kind": "item_zone",
        "preferred": ["south", "west", "south_west", "north_west"], "avoid": ["north_east"],
        "reason": "Heavy storage is traditionally placed along the south or west sides, keeping the north-east light.",
        "consensus": "Commonly cited.",
    },
    # ---- study -----------------------------------------------------------
    {
        "id": "desk-zone", "title": "Study desk zone", "category": "vastu",
        "rooms": ["study_room", "bedroom", "living_room", "other"], "items": ["desk"], "kind": "item_zone",
        "preferred": ["west", "south_west", "south", "north_west"], "avoid": [],
        "reason": "A desk on the west/south side lets the user sit facing east or north, the directions traditionally preferred for study.",
        "consensus": "Varies; the facing direction is usually considered more important than the zone.",
    },
    {
        "id": "desk-facing", "title": "Direction faced while working", "category": "vastu",
        "rooms": ["study_room", "bedroom", "living_room", "other"], "items": ["desk"], "kind": "facing_direction",
        "preferred": ["east", "north"], "avoid": ["south"],
        "reason": "Traditional guidance prefers facing east or north while studying or working.",
        "consensus": "Widely cited.",
    },
    {
        "id": "bookshelf-zone", "title": "Bookshelf zone", "category": "vastu",
        "rooms": ["study_room", "bedroom", "living_room"], "items": ["bookshelf"], "kind": "item_zone",
        "preferred": ["west", "south", "south_west"], "avoid": ["north_east"],
        "reason": "Tall, heavy shelving is traditionally kept on the west or south walls.",
        "consensus": "Commonly cited.",
    },
    # ---- kitchen ---------------------------------------------------------
    {
        "id": "stove-zone", "title": "Stove / hob zone", "category": "vastu",
        "rooms": ["kitchen"], "items": ["stove"], "kind": "item_zone",
        "preferred": ["south_east", "north_west"], "avoid": ["north_east", "south_west"],
        "reason": "Fire is traditionally associated with the south-east (north-west as the alternate); the north-east is associated with water.",
        "consensus": "Widely cited.",
    },
    {
        "id": "stove-facing", "title": "Direction faced while cooking", "category": "vastu",
        "rooms": ["kitchen"], "items": ["stove"], "kind": "facing_direction",
        "preferred": ["east"], "avoid": [],
        "reason": "Traditional guidance commonly prefers the cook to face east.",
        "consensus": "Widely cited.",
    },
    {
        "id": "sink-zone", "title": "Sink / water zone", "category": "vastu",
        "rooms": ["kitchen"], "items": ["sink"], "kind": "item_zone",
        "preferred": ["north_east", "north", "east"], "avoid": ["south_east", "south_west"],
        "reason": "Water is traditionally associated with the north-east/north, and kept away from the fire zone.",
        "consensus": "Commonly cited.",
    },
    {
        "id": "refrigerator-zone", "title": "Refrigerator zone", "category": "vastu",
        "rooms": ["kitchen"], "items": ["refrigerator"], "kind": "item_zone",
        "preferred": ["south_west", "west", "north_west", "south"], "avoid": ["north_east"],
        "reason": "Heavy appliances are traditionally placed in the south/west, keeping the north-east light.",
        "consensus": "Commonly cited.",
    },
    {
        "id": "sink-stove-separation", "title": "Sink kept apart from stove", "category": "vastu",
        "rooms": ["kitchen"], "items": ["sink", "stove"], "kind": "separation", "min_distance": 1.0,
        "reason": "Water and fire elements are traditionally not placed directly adjacent. (This also keeps wet and hot work areas apart in practice.)",
        "consensus": "Commonly cited.",
    },
    # ---- living / dining -------------------------------------------------
    {
        "id": "seating-zone", "title": "Heavy seating zone", "category": "vastu",
        "rooms": ["living_room", "other"], "items": ["sofa", "armchair"], "kind": "item_zone",
        "preferred": ["south", "west", "south_west"], "avoid": ["north_east"],
        "reason": "Heavier seating is traditionally placed toward the south or west, keeping the north-east open.",
        "consensus": "Commonly cited.",
    },
    {
        "id": "tv-zone", "title": "Television zone", "category": "vastu",
        "rooms": ["living_room", "other"], "items": ["tv_unit"], "kind": "item_zone",
        "preferred": ["south_east", "south", "west"], "avoid": ["north_east"],
        "reason": "Electrical appliances are traditionally associated with the south-east (fire/energy element).",
        "consensus": "Varies; weakly agreed.",
    },
    {
        "id": "dining-zone", "title": "Dining table zone", "category": "vastu",
        "rooms": ["dining_room", "living_room", "kitchen", "other"], "items": ["dining_table"], "kind": "item_zone",
        "preferred": ["west", "east", "north_west"], "avoid": ["south_west"],
        "reason": "The dining area is traditionally placed toward the west or east.",
        "consensus": "Varies by school.",
    },
    # ---- general ---------------------------------------------------------
    {
        "id": "ne-keep-light", "title": "Keep the north-east light", "category": "vastu",
        "rooms": ["*"], "kind": "heavy_zone_avoid", "avoid": ["north_east"],
        "reason": "The north-east is traditionally kept open and uncluttered; heavy furniture is better placed elsewhere.",
        "consensus": "Widely cited.",
    },
    {
        "id": "centre-keep-clear", "title": "Keep the centre clear", "category": "vastu",
        "rooms": ["*"], "kind": "heavy_zone_avoid", "avoid": ["center"],
        "reason": "The centre of the room (Brahmasthan) is traditionally kept open. It also keeps circulation space free.",
        "consensus": "Widely cited.",
    },
    {
        "id": "main-entrance-zone", "title": "Main entrance direction", "category": "vastu",
        "rooms": ["*"], "kind": "opening_zone", "opening_type": "door", "only_main_entrance": True,
        "preferred": ["north", "north_east", "east"], "avoid": ["south_west", "south_east", "south"],
        "reason": "Entrances on the north, north-east or east are traditionally considered auspicious.",
        "consensus": "Widely cited; practical constraints often override it.",
    },
    {
        "id": "window-light", "title": "Windows toward morning light", "category": "vastu",
        "rooms": ["*"], "kind": "any_opening_zone", "opening_type": "window",
        "preferred": ["north", "north_east", "east"],
        "reason": "Openings to the north and east are traditionally preferred for gentle morning light and ventilation.",
        "consensus": "Commonly cited.",
    },
    # ---- practical (not Vastu) ------------------------------------------
    {
        "id": "door-clearance", "title": "Door swing kept clear", "category": "practical",
        "rooms": ["*"], "kind": "door_clearance",
        "reason": "Furniture should not block the area in front of a door. This is a practical safety/usability check, not a Vastu rule.",
        "consensus": "Practical guideline.",
    },
]


def load_rules() -> list[dict[str, Any]]:
    """Defaults, merged with an optional JSON override file (by rule ``id``)."""
    rules = {r["id"]: deepcopy(r) for r in DEFAULT_RULES}
    path = os.getenv("VASTU_RULES_FILE", "").strip()
    if path:
        try:
            overrides = json.loads(Path(path).read_text(encoding="utf-8"))
            for entry in overrides:
                rid = entry.get("id")
                if not rid:
                    continue
                if entry.get("enabled") is False:
                    rules.pop(rid, None)
                elif rid in rules:
                    rules[rid].update(entry)
                else:
                    rules[rid] = entry
        except (OSError, ValueError) as exc:   # a broken override must be loud, not silent
            log.error("Could not load VASTU_RULES_FILE=%s: %s", path, exc)
            raise RuntimeError(f"Invalid VASTU_RULES_FILE: {exc}") from exc
    return list(rules.values())


def rule_catalog() -> dict:
    rules = load_rules()
    return {
        "rules": rules,
        "available_room_types": sorted({r for rule in rules for r in rule["rooms"] if r != "*"}),
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Evidence / confidence
# ---------------------------------------------------------------------------

def _confidence(p) -> str:
    if p.confirmed or p.position_source == "user":
        return "user_confirmed"
    if p.position_source in ("reconstructed", "redesign") or p.source == "reconstructed":
        return "estimated"
    return "unverified"


def _evidence(p, **extra) -> dict:
    return {
        "position_source": p.position_source,
        "dimensions_source": p.dims_source,
        "confidence": _confidence(p),
        **extra,
    }


def _label(p) -> str:
    return p.label or display_label(p.item)


def _where(zone: str, top: str) -> str:
    return ori.describe_plan_cell(*ori.plan_cell_for_zone(zone, top))


def _zone_names(zones: list[str]) -> str:
    return ", ".join(ori.zone_label(z) for z in zones)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _result(rule, status, subject=None, *, severity=None, observed=None, expected=None,
            evidence=None, recommendation=None, suggested_zones=None, detail=None):
    needs_confirmation = status != "satisfied" and (evidence or {}).get("confidence", "user_confirmed") != "user_confirmed"
    return {
        "rule_id": rule["id"],
        "title": rule["title"],
        "category": rule["category"],
        "status": status,
        "severity": severity,
        "subject": subject,
        "observed": observed,
        "expected": expected,
        "detail": detail,
        "reason": rule["reason"],
        "consensus": rule.get("consensus"),
        "evidence": evidence or {},
        "recommendation": recommendation,
        "suggested_zones": suggested_zones or [],
        "requires_confirmation": bool(needs_confirmation) if status == "violated" else status == "indeterminate",
    }


def _zone_of(p, layout: RoomLayout, top: str) -> str:
    return ori.zone_for_point(p.x + p.width / 2, p.y + p.length / 2, layout.width, layout.length, top)


def _eval_item_zone(rule, layout, top):
    out = []
    for p in layout.placements:
        if p.item not in rule["items"]:
            continue
        zone = _zone_of(p, layout, top)
        subject = {"id": p.id, "item": p.item, "label": _label(p)}
        ev = _evidence(p, center=[round(p.x + p.width / 2, 2), round(p.y + p.length / 2, 2)])
        pref, avoid = rule.get("preferred", []), rule.get("avoid", [])
        if zone in pref:
            out.append(_result(rule, "satisfied", subject, observed={"zone": zone}, expected={"preferred": pref}, evidence=ev))
        else:
            major = zone in avoid
            targets = [z for z in pref if z != zone]
            where = _where(targets[0], top) if targets else None
            rec = (
                f"Consider moving the {_label(p).lower()} toward the {_zone_names(targets[:2])} zone"
                + (f" ({where} of the plan)" if where else "") + "."
            ) if targets else f"Consider moving the {_label(p).lower()} out of the {ori.zone_label(zone)} zone."
            out.append(_result(
                rule, "violated", subject, severity="major" if major else "minor",
                observed={"zone": zone}, expected={"preferred": pref, "avoid": avoid},
                evidence=ev, recommendation=rec, suggested_zones=targets,
                detail=("Sits in a zone this rule asks to avoid." if major else "Not in a preferred zone for this rule."),
            ))
    return out


def _edge_direction(edge: str | None, top: str) -> str | None:
    return ori.edge_directions(top)[edge] if edge else None


def _eval_direction(rule, layout, top, field: str, noun: str):
    out = []
    for p in layout.placements:
        if p.item not in rule["items"]:
            continue
        subject = {"id": p.id, "item": p.item, "label": _label(p)}
        edge = getattr(p, field)
        direction = _edge_direction(edge, top)
        ev = _evidence(p, **{field: edge})
        if direction is None:
            out.append(_result(
                rule, "indeterminate", subject, evidence=ev, expected={"preferred": rule["preferred"]},
                detail=f"The {noun} of the {_label(p).lower()} has not been recorded, so this rule cannot be judged.",
                recommendation=f"Record which wall the {noun} of the {_label(p).lower()} is toward.",
            ))
        elif direction in rule["preferred"]:
            out.append(_result(rule, "satisfied", subject, observed={"direction": direction}, expected={"preferred": rule["preferred"]}, evidence=ev))
        else:
            major = direction in rule.get("avoid", [])
            prefs = rule["preferred"]
            target_edges = [e for e in ori.EDGES if ori.edge_directions(top)[e] in prefs]
            out.append(_result(
                rule, "violated", subject, severity="major" if major else "minor",
                observed={"direction": direction}, expected={"preferred": prefs, "avoid": rule.get("avoid", [])},
                evidence=ev, suggested_zones=[],
                detail=f"The {noun} is toward {direction}.",
                recommendation=(
                    f"Consider rotating the {_label(p).lower()} so its {noun} is toward "
                    f"{' or '.join(prefs)} (the {' or '.join(target_edges)} edge of the plan)."
                ),
            ))
    return out


def _opening_zone(o, layout, top):
    return ori.wall_zone(o.wall, o.offset + o.width / 2, layout.width, layout.length, top)


def _eval_opening_zone(rule, layout, top):
    openings = [o for o in layout.openings if o.type == rule["opening_type"]]
    if rule.get("only_main_entrance"):
        openings = [o for o in openings if o.is_main_entrance]
        if not openings:
            return []  # not applicable unless an entrance has been marked
    out = []
    for o in openings:
        zone = _opening_zone(o, layout, top)
        subject = {"id": o.id, "item": o.type, "label": o.type.title()}
        ev = {"confidence": "user_confirmed" if o.provenance == "user_provided" else "estimated", "wall": o.wall}
        pref, avoid = rule.get("preferred", []), rule.get("avoid", [])
        if zone in pref:
            out.append(_result(rule, "satisfied", subject, observed={"zone": zone}, expected={"preferred": pref}, evidence=ev))
        else:
            out.append(_result(
                rule, "violated", subject, severity="major" if zone in avoid else "minor",
                observed={"zone": zone}, expected={"preferred": pref, "avoid": avoid}, evidence=ev,
                detail="Structural openings are rarely movable.",
                recommendation=("Structural openings usually cannot move; if this matters to you, treat it as context for furniture placement "
                                "rather than something to change."),
            ))
    return out


def _eval_any_opening(rule, layout, top):
    openings = [o for o in layout.openings if o.type == rule["opening_type"]]
    if not openings:
        return [_result(rule, "indeterminate", None, detail=f"No {rule['opening_type']}s have been recorded for this room.",
                        recommendation=f"Add the {rule['opening_type']}s to the floor plan so this rule can be checked.")]
    zones = [_opening_zone(o, layout, top) for o in openings]
    good = [z for z in zones if z in rule["preferred"]]
    ev = {"confidence": "user_confirmed" if all(o.provenance == "user_provided" for o in openings) else "estimated"}
    if good:
        return [_result(rule, "satisfied", None, observed={"zones": zones}, expected={"preferred": rule["preferred"]}, evidence=ev)]
    return [_result(rule, "violated", None, severity="minor", observed={"zones": zones}, expected={"preferred": rule["preferred"]},
                    evidence=ev, detail="No window faces a preferred direction.",
                    recommendation="Windows are structural; consider light-coloured, light-weight window treatments to maximise available light.")]


def _eval_heavy_avoid(rule, layout, top):
    out = []
    for p in layout.placements:
        if not is_heavy(p.item):
            continue
        zone = _zone_of(p, layout, top)
        if zone in rule["avoid"]:
            subject = {"id": p.id, "item": p.item, "label": _label(p)}
            ev = _evidence(p)
            out.append(_result(
                rule, "violated", subject, severity="minor", observed={"zone": zone}, expected={"avoid": rule["avoid"]},
                evidence=ev, detail=f"Heavy furniture is in the {ori.zone_label(zone)} zone.",
                recommendation=f"Consider relocating the {_label(p).lower()} away from the {ori.zone_label(zone)} zone.",
            ))
    if not out and any(is_heavy(p.item) for p in layout.placements):
        out.append(_result(rule, "satisfied", None, observed={"zone": None}, expected={"avoid": rule["avoid"]}))
    return out


def _rect_distance(a, b) -> float:
    dx = max(b.x - (a.x + a.width), a.x - (b.x + b.width), 0.0)
    dy = max(b.y - (a.y + a.length), a.y - (b.y + b.length), 0.0)
    return math.hypot(dx, dy)


def _eval_separation(rule, layout, top):
    first, second = rule["items"][0], rule["items"][1]
    a = [p for p in layout.placements if p.item == first]
    b = [p for p in layout.placements if p.item == second]
    out = []
    for pa in a:
        for pb in b:
            dist = _rect_distance(pa, pb)
            subject = {"id": pa.id, "item": f"{first}+{second}", "label": f"{_label(pa)} / {_label(pb)}"}
            ev = _evidence(pa, gap_metres=round(dist, 2))
            if dist >= rule["min_distance"]:
                out.append(_result(rule, "satisfied", subject, observed={"gap_m": round(dist, 2)}, expected={"min_gap_m": rule["min_distance"]}, evidence=ev))
            else:
                out.append(_result(rule, "violated", subject, severity="minor", observed={"gap_m": round(dist, 2)},
                                   expected={"min_gap_m": rule["min_distance"]}, evidence=ev,
                                   recommendation=f"Leave at least {rule['min_distance']:.1f} m between the {first} and the {second}."))
    return out


def door_swing_rect(o, layout: RoomLayout) -> tuple[float, float, float, float]:
    """(x, y, w, l) of the clear area in front of a door, as a plan rectangle."""
    w = o.width
    if o.wall == "bottom":
        return (o.offset, 0.0, w, w)
    if o.wall == "top":
        return (o.offset, layout.length - w, w, w)
    if o.wall == "left":
        return (0.0, o.offset, w, w)
    return (layout.width - w, o.offset, w, w)


def _overlap(a, b) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def _eval_door_clearance(rule, layout, top):
    doors = [o for o in layout.openings if o.type == "door"]
    if not doors:
        return []
    out, blocked_any = [], False
    for d in doors:
        zone_rect = door_swing_rect(d, layout)
        for p in layout.placements:
            if _overlap(zone_rect, (p.x, p.y, p.width, p.length)):
                blocked_any = True
                out.append(_result(
                    rule, "violated", {"id": p.id, "item": p.item, "label": _label(p)}, severity="major",
                    observed={"overlaps_door_wall": d.wall}, evidence=_evidence(p),
                    detail=f"The {_label(p).lower()} sits inside the swing area of the door on the {d.wall} wall.",
                    recommendation=f"Move the {_label(p).lower()} so the door can open fully.",
                ))
    if not blocked_any:
        out.append(_result(rule, "satisfied", None, observed={"doors_checked": len(doors)}))
    return out


_DISPATCH = {
    "item_zone": _eval_item_zone,
    "opening_zone": _eval_opening_zone,
    "any_opening_zone": _eval_any_opening,
    "heavy_zone_avoid": _eval_heavy_avoid,
    "separation": _eval_separation,
    "door_clearance": _eval_door_clearance,
}


def _applies(rule, room_type: str) -> bool:
    return "*" in rule["rooms"] or room_type in rule["rooms"]


def evaluate(layout: RoomLayout) -> dict:
    """Evaluate a layout against every applicable rule."""
    orientation = layout.resolved_orientation()
    top = orientation.top_edge_direction
    rules = load_rules()

    results: list[dict] = []
    applicable_ids: list[str] = []
    for rule in rules:
        if not _applies(rule, layout.room_type):
            continue
        kind = rule["kind"]
        if kind == "head_direction":
            found = _eval_direction(rule, layout, top, "headboard_edge", "headboard")
        elif kind == "facing_direction":
            found = _eval_direction(rule, layout, top, "facing_edge", "facing direction")
        else:
            found = _DISPATCH[kind](rule, layout, top)
        if found:
            applicable_ids.append(rule["id"])
            results.extend(found)

    satisfied = [r for r in results if r["status"] == "satisfied"]
    violated = [r for r in results if r["status"] == "violated"]
    indeterminate = [r for r in results if r["status"] == "indeterminate"]
    vastu_only = [r for r in violated if r["category"] == "vastu"]
    evaluated = len(satisfied) + len(violated)

    recommendations = [
        {
            "rule_id": r["rule_id"], "title": r["title"], "subject": r["subject"],
            "text": r["recommendation"], "reason": r["reason"], "severity": r["severity"],
            "zones": r["suggested_zones"], "requires_confirmation": r["requires_confirmation"],
            "category": r["category"],
        }
        for r in violated + indeterminate if r.get("recommendation")
    ]

    edges = orientation.edges
    item_zones = [
        {"id": p.id, "item": p.item, "label": _label(p), "zone": _zone_of(p, layout, top)} for p in layout.placements
    ]
    opening_zones = [
        {"id": o.id, "type": o.type, "wall": o.wall, "zone": _opening_zone(o, layout, top), "is_main_entrance": o.is_main_entrance}
        for o in layout.openings
    ]

    return {
        "room_summary": {
            "room_type": layout.room_type,
            "name": layout.name,
            "dimensions_metres": {"width": layout.width, "length": layout.length},
            "dimensions_source": layout.dimensions_source,
            "orientation": orientation.to_dict(),
            "orientation_note": (
                f"The top of the plan is {edges['top']}; north is on the {orientation.north_edge} edge."
            ),
            "furniture_count": len(layout.placements),
            "openings": {"doors": sum(o.type == "door" for o in layout.openings), "windows": sum(o.type == "window" for o in layout.openings)},
            "item_zones": item_zones,
            "opening_zones": opening_zones,
        },
        "applicable_rules": applicable_ids,
        "results": results,
        "observations": [
            f"{z['label']} is in the {ori.zone_label(z['zone'])} zone." for z in item_zones
        ],
        "conflicts": [r for r in violated],
        "indeterminate": indeterminate,
        "recommendations": recommendations,
        "summary": {
            "rules_evaluated": evaluated,
            "satisfied": len(satisfied),
            "violated": len(violated),
            "violated_vastu": len(vastu_only),
            "indeterminate": len(indeterminate),
            "ratio_satisfied": round(len(satisfied) / evaluated, 3) if evaluated else None,
            "note": ("Counts cover only rules that could be evaluated from the recorded data; "
                     "indeterminate rules are listed separately and are not counted for or against the layout."),
        },
        "limitations": [
            "Zones use the furniture centre point on a 3x3 grid of the room.",
            "Edge directions are snapped to the four cardinal directions; rooms rotated away from the compass axes are approximated.",
            "Facing and headboard directions are only judged when the user has recorded them.",
        ],
        "disclaimer": DISCLAIMER,
    }

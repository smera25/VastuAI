"""
Redesign planner + structured redesign specification.

The planner produces a *geometric* proposed layout (editable, renderable) from:
  * the current structured layout (room, openings, furniture, orientation),
  * the same Vastu rule data the evaluator uses (single source of truth),
  * the user's preferences.

The resulting spec - ``proposed_layout`` + ``design`` - is the ONE source of
truth for both the redesigned floor plan and the image-generation prompt, so
the two outputs cannot diverge.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from app import orientation as ori
from app import vastu_rules
from app.furniture import CATALOG, default_size, display_label, is_heavy
from app.schemas import FurniturePlacement, RedesignPreferences, RoomLayout

# ---------------------------------------------------------------------------
# Style presets (palette / materials / mood). Unknown styles fall back to the generic entry.
# ---------------------------------------------------------------------------
STYLES: dict[str, dict] = {
    "modern": {"palette": ["warm white", "charcoal grey", "soft oak", "muted brass"], "materials": ["matte laminate", "light oak veneer", "linen upholstery", "brushed metal"], "mood": "clean lines, uncluttered, calm"},
    "minimalist": {"palette": ["off-white", "pale grey", "natural wood", "black accents"], "materials": ["plain plaster walls", "pale wood", "cotton linen"], "mood": "very sparse, functional, lots of open floor"},
    "scandinavian": {"palette": ["white", "light birch", "soft sage", "warm grey"], "materials": ["light birch wood", "wool throws", "linen", "woven cotton rugs"], "mood": "bright, cosy, natural"},
    "contemporary": {"palette": ["greige", "deep green", "walnut", "soft gold"], "materials": ["walnut veneer", "boucle fabric", "glass", "metal"], "mood": "current, sophisticated, balanced"},
    "bohemian": {"palette": ["terracotta", "mustard", "deep teal", "cream"], "materials": ["rattan", "jute", "macrame", "mixed-pattern textiles"], "mood": "layered, warm, eclectic with plants"},
    "traditional": {"palette": ["ivory", "deep maroon", "teak brown", "antique gold"], "materials": ["carved teak", "silk or cotton brocade", "brass fittings"], "mood": "classic, warm, richly detailed"},
}
GENERIC_STYLE = {"palette": ["warm neutrals", "natural wood"], "materials": ["natural wood", "cotton fabric"], "mood": "balanced and comfortable"}

# Indicative planning ranges (INR) for NEW or REPLACED items only. These are rough placeholders for
# budgeting conversations, NOT market quotes; prices vary widely by city, brand and material.
PRICE_RANGES_INR: dict[str, tuple[int, int]] = {
    "bed": (15000, 60000), "single_bed": (9000, 30000), "nightstand": (2000, 8000), "wardrobe": (12000, 50000),
    "dresser": (8000, 30000), "storage": (5000, 20000), "bookshelf": (4000, 15000), "desk": (5000, 20000),
    "chair": (1500, 8000), "sofa": (20000, 80000), "armchair": (8000, 30000), "table": (3000, 12000),
    "coffee_table": (3000, 12000), "dining_table": (10000, 45000), "tv_unit": (6000, 25000),
    "counter": (15000, 60000), "stove": (6000, 30000), "refrigerator": (20000, 70000), "sink": (5000, 25000),
    "plant": (300, 2000), "other": (2000, 10000),
}

TALL_ITEMS = {"wardrobe", "bookshelf", "storage", "refrigerator", "dresser", "counter"}
WALL_BOUND = {"wardrobe", "bookshelf", "storage", "refrigerator", "dresser", "counter", "tv_unit", "sofa",
              "stove", "sink", "desk", "bed", "single_bed"}
PRIORITY = ["bed", "single_bed", "sofa", "wardrobe", "refrigerator", "stove", "sink", "counter", "desk", "dining_table",
            "bookshelf", "storage", "dresser", "tv_unit", "armchair", "nightstand", "table", "coffee_table", "chair", "plant"]
STEP = 0.1


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _rects_overlap(a, b, gap=0.0) -> bool:
    return not (a[0] + a[2] + gap <= b[0] or b[0] + b[2] + gap <= a[0] or a[1] + a[3] + gap <= b[1] or b[1] + b[3] + gap <= a[1])


def _window_rect(o, room: RoomLayout, depth: float = 0.45):
    if o.wall == "bottom":
        return (o.offset, 0.0, o.width, depth)
    if o.wall == "top":
        return (o.offset, room.length - depth, o.width, depth)
    if o.wall == "left":
        return (0.0, o.offset, depth, o.width)
    return (room.width - depth, o.offset, depth, o.width)


def _edge_distance(x, y, w, l, room: RoomLayout) -> dict[str, float]:
    return {"left": x, "right": room.width - (x + w), "bottom": y, "top": room.length - (y + l)}


def _candidates(item: str, w: float, l: float, room: RoomLayout):
    """Yield (x, y, w, l, against_edge|None). Wall-bound items hug a wall; free items use a coarse grid too."""
    dims = [(w, l)] + ([(l, w)] if abs(w - l) > 1e-6 else [])
    seen = set()
    for (cw, cl) in dims:
        if cw > room.width + 1e-6 or cl > room.length + 1e-6:
            continue
        xs = [round(i * STEP, 3) for i in range(int((room.width - cw) / STEP) + 1)]
        ys = [round(i * STEP, 3) for i in range(int((room.length - cl) / STEP) + 1)]
        if xs[-1] < room.width - cw - 1e-6:
            xs.append(round(room.width - cw, 3))
        if ys[-1] < room.length - cl - 1e-6:
            ys.append(round(room.length - cl, 3))
        walls = {
            "bottom": [(x, 0.0) for x in xs], "top": [(x, round(room.length - cl, 3)) for x in xs],
            "left": [(0.0, y) for y in ys], "right": [(round(room.width - cw, 3), y) for y in ys],
        }
        for edge, pts in walls.items():
            for (x, y) in pts:
                key = (x, y, cw, cl, edge)
                if key not in seen:
                    seen.add(key)
                    yield key
        if item not in WALL_BOUND:
            for x in xs[::2]:
                for y in ys[::2]:
                    key = (x, y, cw, cl, None)
                    if key not in seen:
                        seen.add(key)
                        yield key


def _attrs_for(item: str, edge: str | None) -> dict:
    """Derive headboard / facing edges from the wall an item is placed against."""
    if edge is None:
        return {}
    if item in ("bed", "single_bed"):
        return {"headboard_edge": edge}
    if item in ("desk", "stove"):
        return {"facing_edge": edge}                       # the user faces the wall they work/cook against
    if item in ("sofa", "tv_unit", "armchair"):
        return {"facing_edge": ori.EDGES[(ori.EDGES.index(edge) + 2) % 4]}   # front faces into the room
    return {}


# ---------------------------------------------------------------------------
# Scoring (reads the SAME rule data as the evaluator)
# ---------------------------------------------------------------------------

def _score_vastu(rules, room_type, item, zone, head_dir, face_dir) -> float:
    s = 0.0
    for r in rules:
        if "*" not in r["rooms"] and room_type not in r["rooms"]:
            continue
        kind = r["kind"]
        if kind == "item_zone" and item in r.get("items", []):
            s += 3 if zone in r["preferred"] else (-5 if zone in r.get("avoid", []) else -1)
        elif kind == "head_direction" and item in r.get("items", []) and head_dir:
            s += 3 if head_dir in r["preferred"] else (-5 if head_dir in r.get("avoid", []) else -1)
        elif kind == "facing_direction" and item in r.get("items", []) and face_dir:
            s += 2 if face_dir in r["preferred"] else (-3 if face_dir in r.get("avoid", []) else -0.5)
        elif kind == "heavy_zone_avoid" and is_heavy(item) and zone in r.get("avoid", []):
            s -= 2
    return s


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def _priority(item: str) -> int:
    return PRIORITY.index(item) if item in PRIORITY else len(PRIORITY)


def plan_layout(layout: RoomLayout, prefs: RedesignPreferences) -> tuple[RoomLayout, list[dict], list[str], list[dict]]:
    """Returns (proposed_layout, changes, warnings, unplaced)."""
    top = layout.resolved_orientation().top_edge_direction
    edges = ori.edge_directions(top)
    rules = vastu_rules.load_rules() if prefs.follow_vastu else []
    warnings: list[str] = []

    gap = 0.9 if prefs.wheelchair_clearance else 0.3
    # Items to place: existing (retain or replace) + additions
    work: list[dict] = []
    counters: dict[str, int] = {}

    def new_id(item):
        counters[item] = counters.get(item, 0) + 1
        return f"{item}-new{counters[item]}"

    for i, p in enumerate(layout.placements):
        pid = p.id or f"{p.item}-{i + 1}"
        work.append({"id": pid, "item": p.item, "label": p.label or display_label(p.item), "orig": p,
                     "w": p.width, "l": p.length, "replace": pid in prefs.replace, "added": False,
                     "dims_source": p.dims_source or "default"})
    for t in prefs.add:
        item = t if t in CATALOG else "other"
        w, l = default_size(item)
        work.append({"id": new_id(item), "item": item, "label": display_label(item), "orig": None, "w": w, "l": l,
                     "replace": False, "added": True, "dims_source": "default"})

    work.sort(key=lambda it: (_priority(it["item"]), -(it["w"] * it["l"])))

    doors = [o for o in layout.openings if o.type == "door"]
    windows = [o for o in layout.openings if o.type == "window"]
    door_zones = [vastu_rules.door_swing_rect(d, layout) for d in doors]
    window_zones = [_window_rect(w, layout) for w in windows]

    placed: list[dict] = []
    unplaced: list[dict] = []
    relaxed = False

    for it in work:
        item, w, l = it["item"], it["w"], it["l"]
        orig = it["orig"]
        best, best_score = None, -1e9
        for attempt_gap in (gap, 0.1):
            for (x, y, cw, cl, edge) in _candidates(item, w, l, layout):
                rect = (x, y, cw, cl)
                if any(_rects_overlap(rect, z) for z in door_zones):
                    continue
                if item in TALL_ITEMS and any(_rects_overlap(rect, z) for z in window_zones):
                    continue
                if any(_rects_overlap(rect, (q["x"], q["y"], q["width"], q["length"]), attempt_gap if not _is_pair_adjacent(item, q["item"]) else 0.0) for q in placed):
                    continue
                if item == "nightstand":
                    beds = [q for q in placed if q["item"] in ("bed", "single_bed")]
                    if beds and not any(_rects_overlap(rect, (q["x"], q["y"], q["width"], q["length"]), 0.12) for q in beds):
                        continue
                    if edge is None:
                        continue
                attrs = _attrs_for(item, edge)
                if item in ("bed", "single_bed") and edge is None:
                    continue
                zone = ori.zone_for_point(x + cw / 2, y + cl / 2, layout.width, layout.length, top)
                head = edges[attrs["headboard_edge"]] if "headboard_edge" in attrs else None
                face = edges[attrs["facing_edge"]] if "facing_edge" in attrs else None
                score = _score_vastu(rules, layout.room_type, item, zone, head, face)
                # Practical terms
                if item in WALL_BOUND and edge is not None:
                    score += 0.5
                if item in ("sink", "stove"):
                    other = "stove" if item == "sink" else "sink"
                    for q in placed:
                        if q["item"] == other and vastu_rules._rect_distance(_R(x, y, cw, cl), _R(q["x"], q["y"], q["width"], q["length"])) < 1.0:
                            score -= 5
                # Prefer small movement for retained items (replaced items may move freely)
                if orig is not None and not it["replace"]:
                    dist = math.hypot((x + cw / 2) - (orig.x + orig.width / 2), (y + cl / 2) - (orig.y + orig.length / 2))
                    score -= 0.4 * dist
                    if dist < 0.15 and abs(cw - orig.width) < 1e-6:
                        score += 0.6
                if score > best_score + 1e-9:
                    best, best_score = (x, y, cw, cl, edge, attrs), score
            if best:
                if attempt_gap != gap:
                    relaxed = True
                break
        if best is None:
            unplaced.append({"id": it["id"], "item": item, "label": it["label"],
                             "reason": "No valid position was found that respects door swing, windows and spacing."})
            continue
        x, y, cw, cl, edge, attrs = best
        placed.append({"id": it["id"], "item": item, "label": it["label"], "x": round(x, 3), "y": round(y, 3),
                       "width": round(cw, 3), "length": round(cl, 3), **attrs, "_it": it})

    if relaxed:
        warnings.append("The room is tight: spacing between some items was reduced"
                        + (" below the wheelchair-friendly clearance you asked for." if prefs.wheelchair_clearance else " to fit everything."))
    if unplaced:
        warnings.append(f"{len(unplaced)} item(s) could not be fitted: " + ", ".join(u["label"] for u in unplaced) + ".")

    # Build placements + changes
    out_placements, changes = [], []
    for q in placed:
        it = q.pop("_it")
        orig = it["orig"]
        if it["added"]:
            status = "added"
        elif it["replace"]:
            status = "replaced"
        else:
            same = (abs(q["x"] - orig.x) < 0.15 and abs(q["y"] - orig.y) < 0.15
                    and abs(q["width"] - orig.width) < 1e-6 and abs(q["length"] - orig.length) < 1e-6)
            status = "keep" if same else "moved"
        out_placements.append(FurniturePlacement(
            item=q["item"], id=q["id"], label=q["label"], x=q["x"], y=q["y"], width=q["width"], length=q["length"],
            headboard_edge=q.get("headboard_edge"), facing_edge=q.get("facing_edge"),
            source="redesign", position_source="redesign", confirmed=False,
            dims_source=it["dims_source"] if it["dims_source"] in ("user", "estimated", "default") else "default",
            status=status,
        ))
        entry = {"id": q["id"], "item": q["item"], "label": q["label"], "status": status,
                 "to": {"x": q["x"], "y": q["y"], "width": q["width"], "length": q["length"],
                        "zone": ori.zone_for_point(q["x"] + q["width"] / 2, q["y"] + q["length"] / 2, layout.width, layout.length, top)}}
        if orig is not None:
            entry["from"] = {"x": orig.x, "y": orig.y, "width": orig.width, "length": orig.length,
                             "zone": ori.zone_for_point(orig.x + orig.width / 2, orig.y + orig.length / 2, layout.width, layout.length, top)}
        changes.append(entry)

    proposed = RoomLayout(
        room_type=layout.room_type, width=layout.width, length=layout.length, orientation=layout.orientation,
        openings=layout.openings, placements=out_placements, dimensions_source=layout.dimensions_source, name=layout.name,
    )
    return proposed, changes, warnings, unplaced


class _R:   # light rect adapter for vastu_rules._rect_distance
    def __init__(self, x, y, w, l):
        self.x, self.y, self.width, self.length = x, y, w, l


def _is_pair_adjacent(a: str, b: str) -> bool:
    return {a, b} in ({"bed", "nightstand"}, {"single_bed", "nightstand"})


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def estimate_budget(changes: list[dict], prefs: RedesignPreferences) -> dict:
    new_items = [c for c in changes if c["status"] in ("added", "replaced")]
    if not new_items:
        return {"status": "no_purchases_needed", "total_inr": [0, 0], "items": [],
                "note": "Only existing furniture is being rearranged, so no purchases are implied."}
    items = [{"id": c["id"], "label": c["label"], "status": c["status"], "range_inr": list(PRICE_RANGES_INR.get(c["item"], PRICE_RANGES_INR["other"]))} for c in new_items]
    lo, hi = sum(i["range_inr"][0] for i in items), sum(i["range_inr"][1] for i in items)
    out = {"status": "estimated", "total_inr": [lo, hi], "items": items,
           "note": "Indicative planning ranges for new/replaced items only - not quotes. Actual prices vary widely by city, brand and material. Delivery, installation, painting and decor are not included."}
    if prefs.budget_inr:
        out["user_budget_inr"] = prefs.budget_inr
        out["within_budget"] = ("yes" if hi <= prefs.budget_inr else "possibly" if lo <= prefs.budget_inr else "no")
    return out


# ---------------------------------------------------------------------------
# Layout description from the reference photo's viewpoint (for the image model)
# ---------------------------------------------------------------------------

def _view_coords(x, y, w, l, room: RoomLayout, view_edge: str):
    """(lateral a, depth b, lateral extent, depth extent) with the viewer facing ``view_edge``."""
    W, L = room.width, room.length
    cx, cy = x + w / 2, y + l / 2
    if view_edge == "top":
        return cx, cy, w, l, W, L
    if view_edge == "right":
        return L - cy, cx, l, w, L, W
    if view_edge == "bottom":
        return W - cx, L - cy, w, l, W, L
    return cy, W - cx, l, w, L, W          # left


def side_of_edge(edge: str, view_edge: str) -> str:
    """Which side of the viewer's frame (far/right/near/left) a plan edge lies on."""
    k = (ori.EDGES.index(edge) - ori.EDGES.index(view_edge)) % 4
    return ("far wall", "right wall", "near wall at the front of the view", "left wall")[k]


def describe_layout(layout: RoomLayout, view_edge: str) -> list[str]:
    """Describe every planned item from the reference camera's viewpoint.

    Furniture near the viewer is described as foreground furniture inside the
    visible frame, never as being behind the camera.
    """
    lines: list[str] = []
    for p in layout.placements:
        a, b, ext_a, ext_b, A, B = _view_coords(
            p.x, p.y, p.width, p.length, layout, view_edge
        )
        lateral = (
            "on the left" if a < A / 3
            else "on the right" if a > 2 * A / 3
            else "near the centre"
        )
        depth = (
            "in the foreground" if b < B / 3
            else "toward the back" if b > 2 * B / 3
            else "in the middle of the room"
        )

        touches: list[str] = []
        if b + ext_b / 2 >= B - 0.15:
            touches.append("against the far wall")
        if a - ext_a / 2 <= 0.15:
            touches.append("against the left wall")
        if a + ext_a / 2 >= A - 0.15:
            touches.append("against the right wall")

        # A placement along the near edge is still part of the room. Do not
        # describe it as behind the camera, which can make the image model omit it.
        if b - ext_b / 2 <= 0.15:
            touches.append("near the front edge of the room, fully inside the visible frame")

        location = f"{lateral}, {depth}"
        if touches:
            location += ", " + " and ".join(touches)
        lines.append(
            f"{p.label or display_label(p.item)}: {location} "
            f"(approximately {p.width:.1f} x {p.length:.1f} m)"
        )
    return lines


def describe_openings(layout: RoomLayout, view_edge: str) -> list[str]:
    return [f"{o.type.title()}: on the {side_of_edge(o.wall, view_edge)}, about {o.width:.1f} m wide" for o in layout.openings]


# ---------------------------------------------------------------------------
# Spec + prompt
# ---------------------------------------------------------------------------

def build_design(prefs: RedesignPreferences) -> dict:
    preset = STYLES.get(prefs.style.strip().lower(), GENERIC_STYLE)
    return {
        "style": prefs.style, "palette": prefs.color_palette or preset["palette"],
        "palette_source": "user" if prefs.color_palette else "style_default",
        "materials": preset["materials"], "mood": preset["mood"],
        "storage_preference": prefs.storage_preference, "budget_label": prefs.budget_label,
        "functional_requirements": prefs.functional_requirements, "accessibility": prefs.accessibility,
        "notes": prefs.notes,
    }


def build_prompt(spec: dict, has_reference_image: bool) -> str:
    """Build a clear visual brief from the saved structured redesign spec."""
    layout = RoomLayout.model_validate(spec["proposed_layout"])
    d, view = spec["design"], spec["preferences"]["reference_view_edge"]
    room = layout.room_type.replace("_", " ")

    if view in ("top", "bottom"):
        dimensions = f"{layout.width:.1f} m wide x {layout.length:.1f} m deep"
    else:
        dimensions = f"{layout.length:.1f} m wide x {layout.width:.1f} m deep"

    lines = [
        f"Create a photorealistic, fully furnished interior-design photograph of a {room} "
        f"in a {d['style']} style. The room is approximately {dimensions}. "
        "Use a natural eye-level wide-angle interior photograph, with the room and its furniture clearly visible."
    ]

    if has_reference_image:
        lines.append(
            "Use the supplied reference photo as the visual starting point. Preserve the same room architecture, "
            "wall positions, ceiling, floor, windows, doors, room proportions, lighting direction, and camera viewpoint. "
            "Redesign the room by ADDING the furniture listed below. The output must visibly differ from the empty reference photo. "
            "Do not return the original empty room, and do not merely clean up or recolour it."
        )
    else:
        lines.append(
            "Invent plausible room architecture that matches the listed openings and show the room fully furnished."
        )

    furniture_lines = describe_layout(layout, view)
    if furniture_lines:
        lines.append(
            "MANDATORY FURNITURE: Include every item below. Each item must be physically inside the room "
            "and clearly visible in the image. Keep furniture in the foreground inside the frame when specified; "
            "never put furniture behind the camera, outside the room, or outside the image. Do not omit listed items."
        )
        lines.append("FURNITURE LAYOUT (follow as closely as possible):")
        lines.extend(f"- {item}" for item in furniture_lines)
    else:
        lines.append("No furniture is specified; leave the room unfurnished.")

    openings = describe_openings(layout, view)
    if openings:
        lines.append("FIXED ARCHITECTURAL OPENINGS; preserve their positions:")
        lines.extend(f"- {opening}" for opening in openings)

    lines.append(f"COLOUR PALETTE: {', '.join(d['palette'])}.")
    lines.append(f"MATERIALS: {', '.join(d['materials'])}. MOOD: {d['mood']}.")

    if d.get("storage_preference") == "maximum":
        lines.append("Show generous, well-integrated storage.")
    elif d.get("storage_preference") == "minimal":
        lines.append("Keep storage minimal and visually light, without omitting required furniture.")

    if d.get("functional_requirements"):
        lines.append("Functional needs: " + "; ".join(d["functional_requirements"]) + ".")
    if d.get("accessibility"):
        lines.append("Accessibility and circulation: " + "; ".join(d["accessibility"]) + ". Keep walkways clear.")
    if d.get("notes"):
        lines.append("Additional instructions from the client: " + d["notes"])

    lines.append(
        "Natural daylight, realistic furniture scale, coherent perspective, high-quality architectural photography. "
        "Show an unmistakably furnished redesign while preserving the reference room's fixed architecture. "
        "No text, labels, watermarks, people, collage, split screen, or floor-plan graphics."
    )
    return "\n".join(lines)


def create_redesign(layout: RoomLayout, prefs: RedesignPreferences) -> dict:
    before = vastu_rules.evaluate(layout)
    proposed, changes, warnings, unplaced = plan_layout(layout, prefs)
    after = vastu_rules.evaluate(proposed)

    key = lambda r: (r["rule_id"], (r.get("subject") or {}).get("id") or (r.get("subject") or {}).get("label"))
    before_viol = {key(r) for r in before["results"] if r["status"] == "violated"}
    after_viol = {key(r) for r in after["results"] if r["status"] == "violated"}
    resolved = sorted(str(k[0]) for k in before_viol - after_viol)
    introduced = sorted(str(k[0]) for k in after_viol - before_viol)
    remaining = [r for r in after["results"] if r["status"] == "violated"]

    moved = sum(c["status"] == "moved" for c in changes)
    kept = sum(c["status"] == "keep" for c in changes)
    spec = {
        "id": uuid.uuid4().hex[:16],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_layout": layout.model_dump(),
        "preferences": prefs.model_dump(),
        "design": build_design(prefs),
        "proposed_layout": proposed.model_dump(),
        "changes": changes,
        "unplaced": unplaced,
        "vastu": {
            "followed": prefs.follow_vastu,
            "before": before["summary"], "after": after["summary"],
            "resolved_rule_ids": resolved, "introduced_rule_ids": introduced,
            "remaining_conflicts": remaining, "report_after": after,
        },
        "budget": estimate_budget(changes, prefs),
        "summary": {
            "kept": kept, "moved": moved, "added": sum(c["status"] == "added" for c in changes),
            "replaced": sum(c["status"] == "replaced" for c in changes),
            "headline": _headline(before["summary"], after["summary"], moved, prefs),
        },
        "warnings": warnings + ([] if prefs.follow_vastu else ["Vastu guidance was switched off for this redesign."]),
        "visualization": None,
    }
    return spec


def _headline(before: dict, after: dict, moved: int, prefs: RedesignPreferences) -> str:
    if not prefs.follow_vastu:
        return f"Layout rearranged ({moved} item(s) moved) without Vastu constraints."
    b, a = before["violated_vastu"], after["violated_vastu"]
    if a < b:
        return f"{b - a} Vastu conflict(s) resolved ({b} -> {a}) by moving {moved} item(s)."
    if a == b:
        return f"No change in Vastu conflicts ({a}); the room's constraints limited what could be improved."
    return f"Vastu conflicts rose from {b} to {a} to satisfy other constraints; review the details."

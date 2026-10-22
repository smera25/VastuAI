"""
Server-side floor-plan renderer (PNG / vector PDF) built with matplotlib.

The web app draws its own interactive SVG; this renderer exists for exports,
the legacy ``GET /floorplan`` endpoint, and the ``floorplan_png_base64`` field
of ``/room-layout/analyze``. Every direction label comes from
``app.orientation`` - there is no direction logic in this file.

Plan convention: x grows right, y grows up, origin bottom-left, bird's-eye view.
"""
from __future__ import annotations

import math
from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon, Rectangle

from app import orientation as ori
from app.furniture import CATALOG, default_size, display_label, normalize_item

SUPPORTED_ROOMS = {"bedroom", "living_room", "kitchen", "study_room", "dining_room", "other"}
VALID_DIRECTIONS = set(ori.CARDINALS)

# Kept for backward compatibility with older imports.
FURNITURE_SIZES = {k: (v["width"], v["length"]) for k, v in CATALOG.items()}
FURNITURE_COLORS = {k: v["color"] for k, v in CATALOG.items()}

PAPER = "#faf7f2"
INK = "#2b2b2a"
MUTED = "#7b7a72"
ACCENT = "#6b7f5e"
WINDOW = "#6fa0b5"
DOOR = "#8a6d4b"

CHANGE_COLORS = {"moved": "#c27c3a", "added": "#4f8a64", "replaced": "#8a5fb0"}


def _validate(width, length, room_type, output_format, top_direction):
    if not (2 <= width <= 15 and 2 <= length <= 15):
        raise ValueError("Room width and length must be between 2 and 15 metres.")
    room_type = str(room_type).strip().lower()
    if room_type not in SUPPORTED_ROOMS:
        raise ValueError("Unsupported room type.")
    output_format = str(output_format).strip().lower()
    if output_format not in {"png", "pdf"}:
        raise ValueError("Output format must be png or pdf.")
    try:
        top_direction = ori.normalize_direction(top_direction)
    except ori.OrientationError as exc:
        raise ValueError("north_direction must be north, east, south, or west.") from exc
    return room_type, output_format, top_direction


def _validate_placements(placements, width, length):
    validated = []
    for placement in placements or []:
        raw = str(placement.get("item", "")).strip()
        item = normalize_item(raw)
        if not item:
            raise ValueError("Furniture item names cannot be empty.")
        if item not in CATALOG:
            # Unknown types are allowed when the caller supplies dimensions.
            if "width" not in placement or "length" not in placement:
                raise ValueError(
                    f"Unsupported furniture item '{item}'. Supported items: "
                    f"{', '.join(CATALOG)}; or supply width and length."
                )
        dw, dl = default_size(item)
        x = float(placement.get("x", 0.2))
        y = float(placement.get("y", 0.2))
        w = float(placement.get("width", dw))
        l = float(placement.get("length", dl))
        if w <= 0 or l <= 0:
            raise ValueError(f"Dimensions for '{item}' must be positive.")
        if x < -1e-6 or y < -1e-6 or x + w > width + 1e-6 or y + l > length + 1e-6:
            raise ValueError(f"'{item}' extends outside the room boundary. Adjust its position or dimensions.")
        validated.append({
            "item": item,
            "label": placement.get("label") or (display_label(item) if item in CATALOG else raw.replace("_", " ").title()),
            "x": x, "y": y, "width": w, "length": l,
            "facing_edge": placement.get("facing_edge"),
            "headboard_edge": placement.get("headboard_edge"),
            "status": placement.get("status"),
        })
    return validated


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _opening_geometry(opening: dict, width: float, length: float):
    wall, off, w = opening["wall"], float(opening["offset"]), float(opening["width"])
    if wall == "bottom":
        return (off, 0.0), (off + w, 0.0), (0.0, 1.0)
    if wall == "top":
        return (off, length), (off + w, length), (0.0, -1.0)
    if wall == "left":
        return (0.0, off), (0.0, off + w), (1.0, 0.0)
    return (width, off), (width, off + w), (-1.0, 0.0)


def _draw_opening(ax, opening: dict, width: float, length: float):
    p0, p1, n = _opening_geometry(opening, width, length)
    # Break the wall.
    ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=PAPER, linewidth=7, solid_capstyle="butt", zorder=4)
    if opening["type"] == "window":
        t = ((p1[0] - p0[0]), (p1[1] - p0[1]))
        for shift in (-0.04, 0.0, 0.04):
            ax.plot(
                [p0[0] + n[0] * shift, p1[0] + n[0] * shift],
                [p0[1] + n[1] * shift, p1[1] + n[1] * shift],
                color=WINDOW, linewidth=1.6, zorder=5,
            )
        return
    # Door: leaf + swing arc.
    w = float(opening["width"])
    leaf_end = (p0[0] + n[0] * w, p0[1] + n[1] * w)
    ax.plot([p0[0], leaf_end[0]], [p0[1], leaf_end[1]], color=DOOR, linewidth=2, zorder=5)
    a_t = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    a_n = math.degrees(math.atan2(n[1], n[0]))
    theta1, theta2 = (a_t, a_n) if (a_n - a_t) % 360 == 90 else (a_n, a_t)
    ax.add_patch(Arc(p0, 2 * w, 2 * w, theta1=theta1, theta2=theta2, color=DOOR, linewidth=1, linestyle=(0, (3, 2)), zorder=5))
    if opening.get("is_main_entrance"):
        # Small triangle outside the wall (cannot collide with the edge label pills).
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        tx, ty = (p1[0] - p0[0]) / w, (p1[1] - p0[1]) / w
        tip = (mid[0] - n[0] * 0.05, mid[1] - n[1] * 0.05)
        base = (mid[0] - n[0] * 0.17, mid[1] - n[1] * 0.17)
        ax.add_patch(Polygon([tip, (base[0] - tx * 0.08, base[1] - ty * 0.08), (base[0] + tx * 0.08, base[1] + ty * 0.08)],
                             closed=True, facecolor=DOOR, edgecolor=DOOR, zorder=6))


def _draw_front_marker(ax, p: dict):
    """Small tick on the edge an item faces (or a headboard is against)."""
    edge = p.get("facing_edge") or p.get("headboard_edge")
    if not edge:
        return
    x, y, w, l = p["x"], p["y"], p["width"], p["length"]
    seg = {
        "top": ([x + w * 0.2, x + w * 0.8], [y + l] * 2),
        "bottom": ([x + w * 0.2, x + w * 0.8], [y] * 2),
        "left": ([x] * 2, [y + l * 0.2, y + l * 0.8]),
        "right": ([x + w] * 2, [y + l * 0.2, y + l * 0.8]),
    }[edge]
    ax.plot(seg[0], seg[1], color=INK, linewidth=3 if p.get("headboard_edge") else 1.6, solid_capstyle="round", zorder=6)


def _draw_compass_rose(ax, cx, cy, radius, orientation: ori.Orientation):
    """Mini compass rose; the N arrow points at the edge that faces north."""
    ax.add_patch(Circle((cx, cy), radius, fill=False, edgecolor=MUTED, linewidth=1, zorder=3))
    rot = orientation.north_arrow_rotation            # clockwise from "up"
    for k, letter in enumerate(("N", "E", "S", "W")):
        ang = math.radians(rot + 90 * k)             # clockwise from up
        dx, dy = math.sin(ang), math.cos(ang)
        if k == 0:
            ax.add_patch(FancyArrowPatch(
                (cx - dx * radius * 0.55, cy - dy * radius * 0.55),
                (cx + dx * radius * 0.95, cy + dy * radius * 0.95),
                arrowstyle="-|>", mutation_scale=11, color=INK, linewidth=1.8, zorder=6,
            ))
            ax.text(cx + dx * radius * 1.5, cy + dy * radius * 1.5, "N", ha="center", va="center",
                    fontsize=10, fontweight="bold", color=INK, zorder=6)
        else:
            ax.text(cx + dx * radius * 1.45, cy + dy * radius * 1.45, letter, ha="center", va="center",
                    fontsize=7, color=MUTED, zorder=6)


def _draw_dimension(ax, p0, p1, text, estimated, text_xy, rotation=0):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="<->", mutation_scale=7, color=MUTED, linewidth=0.9,
        linestyle=(0, (3, 2)) if estimated else "-",
    ))
    ax.text(text_xy[0], text_xy[1], text, ha="center", va="center", rotation=rotation, fontsize=9,
            color=INK, style="italic" if estimated else "normal",
            bbox={"facecolor": PAPER, "edgecolor": "none", "pad": 1.5}, zorder=7)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_floorplan(
    width: float = 4.0,
    length: float = 3.5,
    room_type: str = "bedroom",
    output_format: str = "png",
    placements: list[dict] | None = None,
    north_direction: str = "north",
    *,
    top_edge_direction: str | None = None,
    openings: list[dict] | None = None,
    dimensions_source: str = "user_provided",
    title: str | None = None,
    subtitle: str | None = None,
    show_legend: bool = True,
) -> bytes:
    """
    Render a floor plan.

    ``top_edge_direction`` is the compass direction of the TOP edge of the
    drawing. ``north_direction`` is the deprecated name for the same value and
    is used only when ``top_edge_direction`` is not given.
    """
    top = top_edge_direction or north_direction
    room_type, output_format, top = _validate(width, length, room_type, output_format, top)
    orientation = ori.Orientation(top_edge_direction=top)
    edges = orientation.edges
    items = _validate_placements(placements, width, length)
    openings = [o if isinstance(o, dict) else o.model_dump() for o in (openings or [])]
    estimated = dimensions_source != "user_provided"

    margin = 1.25
    fig_w = 8.0
    fig_h = max(5.5, min(10.5, fig_w * (length + 2 * margin + 0.6) / (width + 2 * margin + 0.6)))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=PAPER)
    ax.set_facecolor(PAPER)

    try:
        # Floor + furniture + walls
        ax.add_patch(Rectangle((0, 0), width, length, facecolor="#fffdf9", edgecolor="none", zorder=1))

        for p in items:
            change = p.get("status")
            edge_color = CHANGE_COLORS.get(change, INK)
            ax.add_patch(Rectangle(
                (p["x"], p["y"]), p["width"], p["length"],
                facecolor=CATALOG.get(p["item"], CATALOG["other"])["color"],
                edgecolor=edge_color, linewidth=2.2 if change in CHANGE_COLORS else 1.0,
                linestyle="--" if change == "added" else "-", alpha=0.95, zorder=3,
            ))
            _draw_front_marker(ax, p)
            small = min(p["width"], p["length"]) < 0.5
            ax.text(p["x"] + p["width"] / 2, p["y"] + p["length"] / 2, p["label"], ha="center", va="center",
                    fontsize=6.5 if small else 8, color=INK, zorder=7,
                    rotation=90 if p["length"] > p["width"] * 1.8 else 0)

        ax.add_patch(Rectangle((0, 0), width, length, fill=False, edgecolor=INK, linewidth=4, zorder=4))
        for opening in openings:
            _draw_opening(ax, opening, width, length)

        # Edge labels - taken straight from the orientation module.
        pill = {"facecolor": "#eef1e8", "edgecolor": ACCENT, "boxstyle": "round,pad=0.25", "linewidth": 0.8}
        ax.text(width / 2, length + 0.32, edges["top"].upper(), ha="center", va="bottom", fontsize=9, color=ACCENT, fontweight="bold", bbox=pill)
        ax.text(width / 2, -0.32, edges["bottom"].upper(), ha="center", va="top", fontsize=9, color=ACCENT, fontweight="bold", bbox=pill)
        ax.text(-0.32, length / 2, edges["left"].upper(), ha="right", va="center", rotation=90, fontsize=9, color=ACCENT, fontweight="bold", bbox=pill)
        ax.text(width + 0.32, length / 2, edges["right"].upper(), ha="left", va="center", rotation=270, fontsize=9, color=ACCENT, fontweight="bold", bbox=pill)

        # Compass rose in the top-right outside corner.
        _draw_compass_rose(ax, width + 0.75, length + 0.7, 0.34, orientation)

        # Dimensions (offset well clear of the edge labels).
        approx = "~" if estimated else ""
        _draw_dimension(ax, (0, -0.85), (width, -0.85), f"{approx}{width:.2f} m", estimated, (width / 2, -1.05))
        _draw_dimension(ax, (-0.85, 0), (-0.85, length), f"{approx}{length:.2f} m", estimated, (-1.05, length / 2), rotation=90)

        # 1 m scale bar
        ax.plot([0, 1.0], [-0.55, -0.55], color=INK, linewidth=2, zorder=6)
        ax.text(0.5, -0.42, "1 m", ha="center", va="bottom", fontsize=6.5, color=MUTED)

        ax.set_xlim(-1.45, width + 1.45)
        ax.set_ylim(-1.45 - (0.35 if show_legend else 0), length + 1.35)
        ax.set_aspect("equal")
        ax.axis("off")

        head = title or f"{room_type.replace('_', ' ').title()} floor plan"
        note = subtitle or (
            f"Top of drawing: {edges['top'].upper()}  ·  "
            + ("Dimensions are estimates, not measurements" if estimated else "Dimensions supplied by the user")
        )
        ax.set_title(f"{head}\n{note}", fontsize=11, color=INK, pad=14)

        if show_legend:
            handles = [
                Rectangle((0, 0), 1, 1, facecolor=CATALOG["other"]["color"], edgecolor=INK, label="Furniture"),
                Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=DOOR, label="Door (swing; ▲ main entrance)"),
                Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=WINDOW, label="Window"),
            ]
            if any(i.get("status") in CHANGE_COLORS for i in items):
                handles += [Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=c, label=k.title()) for k, c in CHANGE_COLORS.items()]
            ax.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=7.5,
                      bbox_to_anchor=(0.5, -0.02), labelcolor=MUTED)

        buffer = BytesIO()
        fig.savefig(buffer, format=output_format, dpi=180, bbox_inches="tight", facecolor=PAPER)
        return buffer.getvalue()
    finally:
        plt.close(fig)

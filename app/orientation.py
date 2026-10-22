"""
Centralised orientation mapping.

This is the SINGLE source of truth for relating a floor plan's drawn edges
to real-world compass directions. Floor-plan rendering, Vastu zone
evaluation, redesign planning, and the frontend (which mirrors this module in
``frontend/src/lib/orientation.js`` and is tested against the same fixtures in
``shared/orientation-cases.json``) all go through it.

Conventions
-----------
Plan coordinates: x grows to the RIGHT, y grows toward the TOP of the drawing,
origin at the bottom-left corner. The plan is a bird's-eye view.

``top_edge_direction`` is the real-world compass direction represented by the
TOP edge of the drawing. Because the plan is a view from above, the compass
sequence around the room is always clockwise:

    top -> right -> bottom -> left   ==   T, T+90, T+180, T+270 degrees

Worked example (the case from the project brief):

    top_edge_direction = east
    top    = east
    right  = south
    bottom = west
    left   = north          <- north is on the LEFT, not the top

Historical note: the original code called this value ``north_direction``,
which reads as "where north is" but actually meant "what the top edge is".
``north_direction`` is still accepted by the API as a deprecated alias.
"""

from __future__ import annotations

from dataclasses import dataclass

CARDINALS: tuple[str, ...] = ("north", "east", "south", "west")  # clockwise
EDGES: tuple[str, ...] = ("top", "right", "bottom", "left")      # clockwise

# Unit vectors in (east, north) space, aligned with CARDINALS.
_COMPASS_VECTORS: tuple[tuple[int, int], ...] = ((0, 1), (1, 0), (0, -1), (-1, 0))

# (east_sign, north_sign) -> eight-wind zone name (plus the centre).
_ZONE_BY_SIGNS: dict[tuple[int, int], str] = {
    (0, 1): "north",
    (1, 1): "north_east",
    (1, 0): "east",
    (1, -1): "south_east",
    (0, -1): "south",
    (-1, -1): "south_west",
    (-1, 0): "west",
    (-1, 1): "north_west",
    (0, 0): "center",
}

ZONES: tuple[str, ...] = tuple(_ZONE_BY_SIGNS.values())


class OrientationError(ValueError):
    """Raised for invalid or contradictory orientation input."""


class OrientationConflict(OrientationError):
    """Raised when two orientation inputs disagree with each other."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def normalize_direction(direction: str) -> str:
    value = str(direction).strip().lower()
    if value not in CARDINALS:
        raise OrientationError(
            f"Direction must be one of {', '.join(CARDINALS)}; got {direction!r}."
        )
    return value


def normalize_edge(edge: str) -> str:
    value = str(edge).strip().lower()
    if value not in EDGES:
        raise OrientationError(
            f"Edge must be one of {', '.join(EDGES)}; got {edge!r}."
        )
    return value


def rotate_direction(direction: str, quarter_turns: int) -> str:
    """Rotate a cardinal direction clockwise by ``quarter_turns`` * 90 deg."""
    index = CARDINALS.index(normalize_direction(direction))
    return CARDINALS[(index + quarter_turns) % 4]


def opposite_direction(direction: str) -> str:
    return rotate_direction(direction, 2)


# ---------------------------------------------------------------------------
# Edge <-> compass mapping
# ---------------------------------------------------------------------------

def edge_directions(top_edge_direction: str) -> dict[str, str]:
    """Compass direction of each drawn edge, given the top edge's direction."""
    top = normalize_direction(top_edge_direction)
    return {
        "top": top,
        "right": rotate_direction(top, 1),
        "bottom": rotate_direction(top, 2),
        "left": rotate_direction(top, 3),
    }


def edge_for_direction(top_edge_direction: str, direction: str) -> str:
    """Which drawn edge faces the given compass direction (inverse mapping)."""
    top_index = CARDINALS.index(normalize_direction(top_edge_direction))
    target_index = CARDINALS.index(normalize_direction(direction))
    return EDGES[(target_index - top_index) % 4]


def north_edge(top_edge_direction: str) -> str:
    return edge_for_direction(top_edge_direction, "north")


def north_arrow_rotation_degrees(top_edge_direction: str) -> int:
    """
    Clockwise rotation from "pointing up the page" to "pointing at north".

    top=north -> 0, top=east -> 270 (points left), top=south -> 180,
    top=west -> 90 (points right).
    """
    return (EDGES.index(north_edge(top_edge_direction)) * 90) % 360


def top_edge_from_facing(facing_direction: str, facing_edge: str = "top") -> str:
    """
    Derive the top edge's compass direction from what the user is facing.

    ``facing_direction`` - compass direction the user (or the reference photo)
    is facing. ``facing_edge`` - the drawn edge that represents the wall being
    faced. If you face east and that wall is drawn on the RIGHT edge, the top
    edge must be north.
    """
    offset = EDGES.index(normalize_edge(facing_edge))
    return rotate_direction(facing_direction, -offset)


def heading_to_cardinal(heading_degrees: float) -> str:
    """Nearest cardinal direction for a compass heading (0=N, 90=E, ...)."""
    index = int(((heading_degrees % 360) + 45) // 90) % 4
    return CARDINALS[index]


# ---------------------------------------------------------------------------
# Plan geometry -> compass
# ---------------------------------------------------------------------------

def plan_offset_to_compass(dx: float, dy: float, top_edge_direction: str) -> tuple[float, float]:
    """
    Convert a plan-space offset (dx right, dy up) to (east, north) offsets.

    This is the rotation that every directional calculation depends on.
    """
    top_index = CARDINALS.index(normalize_direction(top_edge_direction))
    up_e, up_n = _COMPASS_VECTORS[top_index]
    right_e, right_n = _COMPASS_VECTORS[(top_index + 1) % 4]
    return (dx * right_e + dy * up_e, dx * right_n + dy * up_n)


def _sign(value: float, tolerance: float) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def zone_for_point(
    x: float,
    y: float,
    room_width: float,
    room_length: float,
    top_edge_direction: str,
) -> str:
    """
    Vastu zone (8 directions + centre) containing a plan point.

    The room is divided into a 3x3 grid in plan space; each cell is then
    mapped to a compass zone through :func:`plan_offset_to_compass`.
    """
    if room_width <= 0 or room_length <= 0:
        raise OrientationError("Room dimensions must be positive.")

    col = _sign(x - room_width / 2, room_width / 6)   # -1 left, 0 mid, +1 right
    row = _sign(y - room_length / 2, room_length / 6)  # -1 bottom, 0 mid, +1 top
    east, north = plan_offset_to_compass(col, row, top_edge_direction)
    return _ZONE_BY_SIGNS[(int(east), int(north))]


def wall_zone(
    edge: str,
    offset: float,
    room_width: float,
    room_length: float,
    top_edge_direction: str,
) -> str:
    """Zone of a point ``offset`` metres along a wall (for doors/windows)."""
    edge = normalize_edge(edge)
    if edge == "top":
        return zone_for_point(offset, room_length, room_width, room_length, top_edge_direction)
    if edge == "bottom":
        return zone_for_point(offset, 0.0, room_width, room_length, top_edge_direction)
    if edge == "left":
        return zone_for_point(0.0, offset, room_width, room_length, top_edge_direction)
    return zone_for_point(room_width, offset, room_width, room_length, top_edge_direction)


# ---------------------------------------------------------------------------
# Orientation value object + request resolution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Orientation:
    """Resolved, validated orientation for one floor plan."""

    top_edge_direction: str
    source: str = "manual"            # manual | device_compass | reconstruction | legacy
    heading_degrees: float | None = None
    confirmed: bool = True

    def __post_init__(self):
        object.__setattr__(self, "top_edge_direction", normalize_direction(self.top_edge_direction))

    @property
    def edges(self) -> dict[str, str]:
        return edge_directions(self.top_edge_direction)

    @property
    def north_edge(self) -> str:
        return north_edge(self.top_edge_direction)

    @property
    def north_arrow_rotation(self) -> int:
        return north_arrow_rotation_degrees(self.top_edge_direction)

    def zone(self, x: float, y: float, width: float, length: float) -> str:
        return zone_for_point(x, y, width, length, self.top_edge_direction)

    def to_dict(self) -> dict:
        return {
            "top_edge_direction": self.top_edge_direction,
            "edges": self.edges,
            "north_edge": self.north_edge,
            "north_arrow_rotation_degrees": self.north_arrow_rotation,
            "source": self.source,
            "heading_degrees": self.heading_degrees,
            "confirmed": self.confirmed,
        }


def resolve_orientation(
    *,
    top_edge_direction: str | None = None,
    north_direction: str | None = None,        # deprecated alias
    facing_direction: str | None = None,
    facing_edge: str | None = None,
    heading_degrees: float | None = None,
    manual_compass_direction: str | None = None,
    source: str | None = None,
    confirmed: bool = True,
) -> Orientation:
    """
    Resolve all supported ways of describing orientation into one value.

    Accepted, in order of authority:
      1. ``top_edge_direction`` (or its deprecated alias ``north_direction``)
      2. ``facing_direction`` + ``facing_edge`` (default edge: top)

    If several are supplied they must agree, otherwise
    :class:`OrientationConflict` is raised - the app never silently picks one.
    A compass ``heading_degrees`` is cross-checked against
    ``manual_compass_direction`` (the direction the person says they are
    facing); it is evidence, not a replacement for confirmation.
    """
    candidates: dict[str, str] = {}

    explicit = top_edge_direction or north_direction
    if top_edge_direction and north_direction and (
        normalize_direction(top_edge_direction) != normalize_direction(north_direction)
    ):
        raise OrientationConflict(
            "top_edge_direction and the deprecated north_direction disagree.",
            {"top_edge_direction": top_edge_direction, "north_direction": north_direction},
        )
    if explicit:
        candidates["top_edge_direction"] = normalize_direction(explicit)

    if facing_direction:
        candidates["facing_direction"] = top_edge_from_facing(
            facing_direction, facing_edge or "top"
        )

    if heading_degrees is not None:
        heading_cardinal = heading_to_cardinal(heading_degrees)
        if manual_compass_direction is None:
            raise OrientationError(
                "A manual compass direction is required when a compass "
                "heading is provided."
            )
        if heading_cardinal != normalize_direction(manual_compass_direction):
            raise OrientationConflict(
                "The compass heading and the manually selected direction "
                "disagree. Check the phone orientation and try again.",
                {
                    "compass_heading_degrees": heading_degrees,
                    "compass_cardinal_direction": heading_cardinal,
                    "manual_compass_direction": manual_compass_direction,
                    "directions_match": False,
                },
            )

    if not candidates:
        raise OrientationError(
            "Orientation is required: provide top_edge_direction, or "
            "facing_direction (+ facing_edge)."
        )

    distinct = set(candidates.values())
    if len(distinct) > 1:
        raise OrientationConflict(
            "The supplied orientation inputs contradict each other.",
            {"derived_top_edge_directions": candidates},
        )

    resolved_source = source or (
        "device_compass" if heading_degrees is not None else "manual"
    )
    return Orientation(
        top_edge_direction=distinct.pop(),
        source=resolved_source,
        heading_degrees=heading_degrees,
        confirmed=confirmed,
    )


# ---------------------------------------------------------------------------
# Inverse zone mapping (zone -> where it sits on the drawing)
# ---------------------------------------------------------------------------

def plan_cell_for_zone(zone: str, top_edge_direction: str) -> tuple[int, int]:
    """
    Inverse of :func:`zone_for_point` on the 3x3 grid: returns (col, row) with
    col in {-1 left, 0 middle, 1 right} and row in {-1 bottom, 0 middle, 1 top}.
    """
    if zone not in ZONES:
        raise OrientationError(f"Unknown zone {zone!r}.")
    for col in (-1, 0, 1):
        for row in (-1, 0, 1):
            east, north = plan_offset_to_compass(col, row, top_edge_direction)
            if _ZONE_BY_SIGNS[(int(east), int(north))] == zone:
                return col, row
    raise OrientationError(f"Zone {zone!r} has no cell.")  # unreachable


def describe_plan_cell(col: int, row: int) -> str:
    """Human description of a 3x3 cell, e.g. 'top-right corner', 'left side'."""
    if col == 0 and row == 0:
        return "centre of the room"
    vertical = {1: "top", -1: "bottom", 0: ""}[row]
    horizontal = {1: "right", -1: "left", 0: ""}[col]
    if vertical and horizontal:
        return f"{vertical}-{horizontal} corner"
    return f"{vertical or horizontal} side"


def zone_label(zone: str) -> str:
    return {
        "north": "North", "north_east": "North-East", "east": "East",
        "south_east": "South-East", "south": "South", "south_west": "South-West",
        "west": "West", "north_west": "North-West", "center": "Centre",
    }[zone]

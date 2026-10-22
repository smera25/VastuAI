"""
Pydantic schemas shared by every router.

Backward compatibility: the original ``RoomLayoutRequest`` body
(``north_direction`` + ``placements`` with x/y/width/length) still validates.
New fields are all optional.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app import orientation as ori
from app.furniture import normalize_item

RoomType = Literal["bedroom", "living_room", "kitchen", "study_room", "dining_room", "other"]
CardinalDirection = Literal["north", "east", "south", "west"]
PlanEdge = Literal["top", "right", "bottom", "left"]
OpeningType = Literal["door", "window"]
Provenance = Literal["detected", "user_confirmed", "user_provided", "estimated", "reconstructed", "default_estimate"]

ROOM_TYPES: tuple[str, ...] = (
    "bedroom", "living_room", "kitchen", "study_room", "dining_room", "other",
)


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------

class OrientationInput(BaseModel):
    """
    How the client describes the room's orientation.

    Provide ``top_edge_direction`` directly, OR ``facing_direction`` (+
    ``facing_edge``). ``north_direction`` is the deprecated alias for
    ``top_edge_direction`` (it never meant "where north is").
    """

    top_edge_direction: CardinalDirection | None = None
    north_direction: CardinalDirection | None = Field(
        default=None, description="DEPRECATED alias of top_edge_direction."
    )
    facing_direction: CardinalDirection | None = Field(
        default=None, description="Compass direction the user / reference photo faces."
    )
    facing_edge: PlanEdge = Field(
        default="top", description="Drawn edge representing the wall being faced."
    )
    compass_heading_degrees: float | None = Field(default=None, ge=0, le=360)
    manual_compass_direction: CardinalDirection | None = None
    source: Literal["manual", "device_compass", "reconstruction", "legacy"] | None = None
    confirmed: bool = True

    def resolve(self) -> ori.Orientation:
        return ori.resolve_orientation(
            top_edge_direction=self.top_edge_direction,
            north_direction=self.north_direction,
            facing_direction=self.facing_direction,
            facing_edge=self.facing_edge,
            heading_degrees=self.compass_heading_degrees,
            manual_compass_direction=self.manual_compass_direction,
            source=self.source,
            confirmed=self.confirmed,
        )


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------

class FurniturePlacement(BaseModel):
    """An axis-aligned footprint in plan coordinates (metres, origin bottom-left)."""

    item: str = Field(min_length=1, max_length=50)
    x: float = Field(ge=0, le=30)
    y: float = Field(ge=0, le=30)
    width: float = Field(gt=0, le=30)
    length: float = Field(gt=0, le=30)

    # Optional enrichment (all new; legacy requests omit them).
    id: str | None = None
    label: str | None = None
    facing_edge: PlanEdge | None = Field(
        default=None, description="Drawn edge the front of the item points toward."
    )
    headboard_edge: PlanEdge | None = Field(
        default=None, description="Beds only: drawn edge the headboard is against."
    )
    source: Literal["detected", "user_added", "reconstructed", "redesign"] | None = None
    confirmed: bool | None = None
    position_source: Literal["user", "reconstructed", "redesign"] | None = None
    dims_source: Literal["user", "estimated", "default"] | None = None
    status: Literal["keep", "moved", "added", "replaced", "removed"] | None = None

    @field_validator("item")
    @classmethod
    def _norm_item(cls, v: str) -> str:
        v = normalize_item(v)
        if not v:
            raise ValueError("Furniture item names cannot be empty.")
        return v


class Opening(BaseModel):
    """A door or window on one wall of the plan."""

    id: str | None = None
    type: OpeningType
    wall: PlanEdge
    offset: float = Field(ge=0, le=30, description="Metres from the wall's start (left for top/bottom walls, bottom for left/right walls).")
    width: float = Field(gt=0, le=10)
    is_main_entrance: bool = False
    provenance: Literal["user_provided", "estimated"] = "user_provided"


class RoomLayout(BaseModel):
    """Everything needed to draw and evaluate a room - the shared source of truth."""

    room_type: RoomType
    width: float = Field(gt=0, le=15, description="Room width (plan x) in metres.")
    length: float = Field(gt=0, le=15, description="Room length (plan y) in metres.")
    orientation: OrientationInput
    openings: list[Opening] = Field(default_factory=list)
    placements: list[FurniturePlacement] = Field(default_factory=list)
    dimensions_source: Literal["user_provided", "estimated", "reconstructed"] = "user_provided"
    name: str | None = None

    @model_validator(mode="after")
    def _within_room(self) -> "RoomLayout":
        for p in self.placements:
            if p.x + p.width > self.width + 1e-6 or p.y + p.length > self.length + 1e-6:
                raise ValueError(f"'{p.item}' extends outside the room boundary.")
        for o in self.openings:
            wall_len = self.width if o.wall in ("top", "bottom") else self.length
            if o.offset + o.width > wall_len + 1e-6:
                raise ValueError(f"A {o.type} on the {o.wall} wall extends past the wall.")
        return self

    def resolved_orientation(self) -> ori.Orientation:
        return self.orientation.resolve()


# ---------------------------------------------------------------------------
# Vastu
# ---------------------------------------------------------------------------

class VastuRequest(BaseModel):
    """
    ``POST /vastu/analyze`` body. Two accepted forms:

    * legacy: ``room_type`` + ``placements: {"bed": "south", ...}``
    * structured: ``layout`` (full RoomLayout) - used by the web app.
    """

    room_type: RoomType | None = None
    placements: dict[str, str] | None = Field(
        default=None,
        description="LEGACY: furniture items and their directions.",
        examples=[{"bed": "south", "wardrobe": "west"}],
    )
    layout: RoomLayout | None = None

    @model_validator(mode="after")
    def _one_form(self) -> "VastuRequest":
        if self.layout is None and (self.room_type is None or self.placements is None):
            raise ValueError("Provide either `layout`, or the legacy `room_type` + `placements`.")
        return self


# ---------------------------------------------------------------------------
# Room-layout (legacy-compatible combined endpoint)
# ---------------------------------------------------------------------------

class RoomLayoutRequest(BaseModel):
    room_type: RoomType
    width: float = Field(gt=0, le=15, description="Room width in metres.")
    length: float = Field(gt=0, le=15, description="Room length in metres.")

    # `north_direction` is kept for backward compatibility. It means the
    # real-world direction of the TOP edge of the drawing.
    north_direction: CardinalDirection | None = Field(
        default=None,
        description="DEPRECATED alias of top_edge_direction (direction of the drawing's top edge).",
    )
    top_edge_direction: CardinalDirection | None = Field(
        default=None, description="Real-world direction represented by the top edge of the drawing."
    )
    facing_direction: CardinalDirection | None = None
    facing_edge: PlanEdge = "top"
    compass_heading_degrees: float | None = Field(default=None, ge=0, le=360)
    manual_compass_direction: CardinalDirection | None = None

    placements: list[FurniturePlacement] = Field(min_length=1)
    openings: list[Opening] = Field(default_factory=list)

    def orientation_input(self) -> OrientationInput:
        return OrientationInput(
            top_edge_direction=self.top_edge_direction,
            north_direction=self.north_direction,
            facing_direction=self.facing_direction,
            facing_edge=self.facing_edge,
            compass_heading_degrees=self.compass_heading_degrees,
            manual_compass_direction=self.manual_compass_direction,
        )


# ---------------------------------------------------------------------------
# Room analysis job
# ---------------------------------------------------------------------------

class FurnitureCandidate(BaseModel):
    """A furniture item the user has confirmed (or added) before analysis."""

    id: str
    item: str
    label: str | None = None
    source: Literal["detected", "user_added"] = "user_added"
    width: float | None = Field(default=None, gt=0, le=15)
    length: float | None = Field(default=None, gt=0, le=15)
    dims_source: Literal["user", "estimated", "default"] = "default"
    # Manual position (plan coordinates) if the user already placed it.
    x: float | None = Field(default=None, ge=0, le=30)
    y: float | None = Field(default=None, ge=0, le=30)

    @field_validator("item")
    @classmethod
    def _norm_item(cls, v: str) -> str:
        return normalize_item(v)


class AnalysisMetadata(BaseModel):
    """JSON sent alongside the uploaded photos in ``POST /room-analysis/jobs``."""

    room_type: RoomType
    name: str | None = None
    width: float | None = Field(default=None, gt=0, le=15)
    length: float | None = Field(default=None, gt=0, le=15)
    orientation: OrientationInput | None = None
    openings: list[Opening] = Field(default_factory=list)
    furniture: list[FurnitureCandidate] = Field(default_factory=list)
    run_vggt: bool = True
    run_detection: bool = True


# ---------------------------------------------------------------------------
# Redesign
# ---------------------------------------------------------------------------

class RedesignPreferences(BaseModel):
    style: str = Field(default="modern", max_length=60)
    color_palette: list[str] = Field(default_factory=list, max_length=8)
    budget_inr: float | None = Field(default=None, ge=0, le=1e9)
    budget_label: str | None = Field(default=None, max_length=60)
    retain: list[str] = Field(default_factory=list, description="Furniture ids to keep.")
    replace: list[str] = Field(default_factory=list, description="Furniture ids to replace.")
    add: list[str] = Field(default_factory=list, description="Furniture types to add.")
    storage_preference: Literal["minimal", "moderate", "maximum"] = "moderate"
    functional_requirements: list[str] = Field(default_factory=list, max_length=20)
    accessibility: list[str] = Field(default_factory=list, max_length=10)
    wheelchair_clearance: bool = False
    notes: str = Field(default="", max_length=1500)
    follow_vastu: bool = True
    reference_view_edge: PlanEdge = Field(
        default="top",
        description="Plan edge the reference photo faces (used to describe the layout to the image model).",
    )


class RedesignPlanRequest(BaseModel):
    layout: RoomLayout
    preferences: RedesignPreferences = Field(default_factory=RedesignPreferences)


def error_body(code: str, message: str, **extra: Any) -> dict:
    """Uniform machine-readable error payload used by new endpoints."""
    return {"code": code, "message": message, **extra}

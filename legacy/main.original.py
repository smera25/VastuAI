
import base64
from io import BytesIO
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.room_analyzer import analyze_room_image
from floorplan import create_floorplan
from vastu_engine import (
    DIRECTIONAL_RULES,
    analyze_vastu,
    analyze_vastu_coordinates,
)


# ============================================================
# APPLICATION SETUP
# ============================================================

app = FastAPI(
    title="Vastu AI Backend",
    description=(
        "Room image analysis, preliminary floor plans, "
        "and Vastu-aware room-layout analysis."
    ),
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# CONFIGURATION
# ============================================================

RoomType = Literal["bedroom", "living_room", "kitchen"]
CardinalDirection = Literal["north", "east", "south", "west"]

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_ROOM_IMAGES = 6


# ============================================================
# OPENAPI CUSTOMIZATION
# ============================================================

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        openapi_version="3.0.3",
    )

    # Keep multi-image uploads represented as binary files in Swagger.
    body_name = (
        "Body_analyze_room_multiple_analyze_room_multiple_post"
    )

    body_schema = (
        schema.get("components", {})
        .get("schemas", {})
        .get(body_name)
    )

    if body_schema:
        files_schema = (
            body_schema.get("properties", {})
            .get("files")
        )

        if files_schema:
            files_schema["items"] = {
                "type": "string",
                "format": "binary",
            }

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# ============================================================
# SHARED IMAGE VALIDATION AND ANALYSIS
# ============================================================

async def read_and_analyze_image(file: UploadFile) -> dict:
    """Validate an uploaded image and analyze its visible objects."""

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"{file.filename}: upload a JPG, PNG, or WEBP image."
            ),
        )

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"{file.filename}: the uploaded file is empty.",
        )

    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{file.filename}: image must be smaller than 10 MB."
            ),
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()

        analysis = analyze_room_image(image_bytes)

    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not analyze {file.filename}: {exc}",
        ) from exc

    return analysis


# ============================================================
# HOME AND HEALTH
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Welcome to Vastu AI",
        "status": "running",
        "version": app.version,
        "features": [
            "Single-image room analysis",
            "Multi-image room analysis",
            "Preliminary floor-plan generation",
            "PNG and PDF export",
            "Configurable traditional Vastu rules",
            "Compass and manual direction validation",
            "Coordinate-based room-layout analysis",
        ],
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


# ============================================================
# SINGLE-IMAGE ROOM ANALYSIS
# ============================================================

@app.post("/analyze-room")
async def analyze_room(
    file: Annotated[UploadFile, File(...)],
):
    analysis = await read_and_analyze_image(file)

    return {
        "filename": file.filename,
        "status": "uploaded_successfully",
        "image_analysis": analysis,
        "geometry_status": "not_reconstructed",
        "next_step": (
            "Provide or verify room dimensions and furniture positions "
            "before generating a coordinate-based floor plan."
        ),
    }


# ============================================================
# MULTI-IMAGE ROOM ANALYSIS
# ============================================================

@app.post("/analyze-room-multiple")
async def analyze_room_multiple(
    files: list[UploadFile] = File(
        ...,
        description="Upload between 1 and 6 room images.",
    ),
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one room image.",
        )

    if len(files) > MAX_ROOM_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload no more than {MAX_ROOM_IMAGES} images.",
        )

    analyzed_images = []

    for file in files:
        analysis = await read_and_analyze_image(file)

        analyzed_images.append({
            "filename": file.filename,
            "status": "analyzed",
            "image_analysis": analysis,
        })

    total_detections = sum(
        item["image_analysis"].get("detected_object_count", 0)
        for item in analyzed_images
    )

    return {
        "status": "multi_image_analysis_completed",
        "image_count": len(analyzed_images),
        "total_detections_across_images": total_detections,
        "images": analyzed_images,
        "geometry_status": "not_reconstructed",
        "note": (
            "Images are analyzed independently. The same physical "
            "object may appear in multiple images. Room dimensions "
            "and a shared coordinate system are not reconstructed "
            "by this endpoint."
        ),
    }


# ============================================================
# FLOOR PLAN GENERATION AND EXPORT
# ============================================================

@app.get("/floorplan")
def generate_floorplan(
    width: float = 4.0,
    length: float = 3.5,
    room_type: RoomType = "bedroom",
    format: Literal["png", "pdf"] = "png",
    north_direction: CardinalDirection = "north",
):
    """
    Generate a preliminary floor plan.

    north_direction identifies the real-world direction represented
    by the top edge of the drawing.
    """

    if not (2 <= width <= 15 and 2 <= length <= 15):
        raise HTTPException(
            status_code=400,
            detail=(
                "Room width and length must each be between "
                "2 and 15 metres."
            ),
        )

    try:
        file_bytes = create_floorplan(
            width=width,
            length=length,
            room_type=room_type,
            output_format=format,
            north_direction=north_direction,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    media_type = (
        "image/png" if format == "png" else "application/pdf"
    )

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename=floorplan.{format}"
        },
    )


# ============================================================
# VASTU RULES
# ============================================================

@app.get("/vastu/rules")
def get_vastu_rules():
    return {
        "available_room_types": list(DIRECTIONAL_RULES.keys()),
        "rules": DIRECTIONAL_RULES,
        "note": (
            "These are configurable traditional Vastu preferences. "
            "They do not automatically determine room orientation."
        ),
    }


# ============================================================
# BASIC VASTU ANALYSIS
# ============================================================

class VastuRequest(BaseModel):
    room_type: RoomType

    placements: dict[str, str] = Field(
        ...,
        description="Furniture items and their directions.",
        examples=[{"bed": "south", "wardrobe": "west"}],
    )


@app.post("/vastu/analyze")
def vastu_analysis(request: VastuRequest):
    try:
        return analyze_vastu(
            room_type=request.room_type,
            placements=request.placements,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ============================================================
# FURNITURE AND ROOM LAYOUT MODELS
# ============================================================

class FurniturePlacement(BaseModel):
    item: str = Field(min_length=1, max_length=50)
    x: float = Field(ge=0, le=15)
    y: float = Field(ge=0, le=15)
    width: float = Field(gt=0, le=15)
    length: float = Field(gt=0, le=15)


class RoomLayoutRequest(BaseModel):
    room_type: RoomType

    width: float = Field(
        gt=0,
        le=15,
        description="Room width in metres.",
    )

    length: float = Field(
        gt=0,
        le=15,
        description="Room length in metres.",
    )

    north_direction: CardinalDirection = Field(
        ...,
        description=(
            "Real-world cardinal direction represented by the "
            "top edge of the floor-plan drawing."
        ),
    )

    compass_heading_degrees: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description=(
            "Compass heading in degrees: 0=north, 90=east, "
            "180=south, 270=west."
        ),
    )

    manual_compass_direction: CardinalDirection | None = Field(
        default=None,
        description=(
            "Manually observed cardinal direction toward which "
            "the phone was pointing when its compass heading was read."
        ),
    )

    placements: list[FurniturePlacement] = Field(min_length=1)


# ============================================================
# COMPASS UTILITIES
# ============================================================

CARDINAL_DIRECTIONS = [
    "north",
    "east",
    "south",
    "west",
]


def heading_to_cardinal(heading: float) -> str:
    """Map a compass heading to its nearest cardinal direction."""

    normalized_heading = heading % 360
    index = int((normalized_heading + 45) // 90) % 4

    return CARDINAL_DIRECTIONS[index]


def validate_orientation(
    heading: float | None,
    manual_direction: str | None,
) -> dict:
    """Compare a live compass heading with a manually selected direction."""

    result = {
        "status": "orientation_not_confirmed",
        "compass_heading_degrees": heading,
        "compass_cardinal_direction": None,
        "manual_compass_direction": manual_direction,
        "directions_match": None,
    }

    if heading is None:
        if manual_direction is not None:
            result["status"] = "manual_direction_only"
        return result

    if manual_direction is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "A manual compass direction is required when a "
                "compass heading is provided."
            ),
        )

    compass_direction = heading_to_cardinal(heading)

    result["compass_cardinal_direction"] = compass_direction
    result["directions_match"] = (
        compass_direction == manual_direction
    )

    if compass_direction != manual_direction:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "The compass heading and manual direction disagree. "
                    "Check the phone orientation and try again."
                ),
                "orientation_check": result,
            },
        )

    result["status"] = "confirmed_by_two_inputs"
    return result


# ============================================================
# COMBINED ROOM LAYOUT AND VASTU ANALYSIS
# ============================================================

@app.post("/room-layout/analyze")
def analyze_room_layout(request: RoomLayoutRequest):
    """
    Generate a preliminary floor plan and coordinate-based Vastu report.

    Coordinate convention:
      - x=0 is the left edge of the drawing.
      - y=0 is the bottom edge of the drawing.
      - north_direction identifies the real-world direction of the
        drawing's top edge.
      - Furniture coordinates are not rotated.
    """

    if not (
        2 <= request.width <= 15
        and 2 <= request.length <= 15
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Room width and length must each be between "
                "2 and 15 metres."
            ),
        )

    placements = [
        placement.model_dump()
        for placement in request.placements
    ]

    # Validate all furniture positions against the room boundary.
    for placement in placements:
        item = placement["item"].strip().lower()
        placement["item"] = item

        if not item:
            raise HTTPException(
                status_code=400,
                detail="Furniture item names cannot be empty.",
            )

        if (
            placement["x"] + placement["width"] > request.width
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{item}' extends beyond the room width. "
                    "Check its x-coordinate and width."
                ),
            )

        if (
            placement["y"] + placement["length"] > request.length
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{item}' extends beyond the room length. "
                    "Check its y-coordinate and length."
                ),
            )

    # The compass checks phone heading against the manual direction.
    # It does not independently determine which room wall is the top.
    orientation_check = validate_orientation(
        heading=request.compass_heading_degrees,
        manual_direction=request.manual_compass_direction,
    )

    try:
        # Use the same top-edge direction as the Vastu engine.
        # RoomType and CardinalDirection are Literal strings, not Enum objects.
        floorplan_png = create_floorplan(
            width=request.width,
            length=request.length,
            room_type=request.room_type,
            output_format="png",
            placements=placements,
            north_direction=request.north_direction,
        )

        vastu_result = analyze_vastu_coordinates(
            room_type=request.room_type,
            placements=placements,
            room_width=request.width,
            room_length=request.length,
            north_direction=request.north_direction,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "status": "layout_and_vastu_analysis_completed",
        "room_type": request.room_type,
        "dimensions_metres": {
            "width": request.width,
            "length": request.length,
        },
        "north_direction": request.north_direction,
        "orientation_check": orientation_check,
        "coordinate_convention": {
            "origin": "bottom_left",
            "x_axis": "right",
            "y_axis": "up",
            "top_edge_direction": request.north_direction,
            "furniture_coordinates_rotated": False,
        },
        "placements": placements,
        "layout_status": "generated_from_user_coordinates",
        "vastu_analysis": vastu_result,
        "floorplan_png_base64": base64.b64encode(
            floorplan_png
        ).decode("utf-8"),
        "next_steps": [
            "Review the preliminary floor plan.",
            "Add door and window positions when available.",
            "Add furniture-facing and headboard direction analysis.",
            "Integrate the AI room redesign service.",
        ],
        "limitations": [
            "Room geometry is not reconstructed automatically from photos.",
            "Room dimensions and furniture positions are user-supplied.",
            "Compass heading validates the phone direction, not the room geometry.",
            "The top-edge direction must be supplied correctly by the user.",
            "Furniture-facing and bed headboard directions are not inferred.",
            "Traditional Vastu recommendations are configurable preferences, "
            "not scientifically established requirements.",
        ],
    }

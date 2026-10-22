"""
Vastu AI backend - FastAPI application.

Endpoint map
------------
Original (contracts preserved):
  GET  /                         service info
  GET  /health                   health + honest capability report (VGGT / YOLO / image provider)
  POST /analyze-room             single photo -> YOLO detections
  POST /analyze-room-multiple    several photos -> per-photo YOLO + furniture candidates
  GET  /floorplan                PNG/PDF floor plan from query parameters
  GET  /vastu/rules              Vastu rule catalogue
  POST /vastu/analyze            Vastu analysis (legacy direction map OR structured layout)
  POST /room-layout/analyze      coordinate layout + Vastu report + floor-plan PNG (base64)
New:
  POST /floorplan                render a structured layout to PNG/PDF
  POST /room-analysis/jobs       photos + context -> VGGT/YOLO/geometry job  (poll GET /jobs/{id})
  GET  /jobs/{job_id}
  POST /redesign/plan            proposed layout + Vastu before/after + budget + design spec
  GET  /redesign/{id}            stored spec
  GET  /redesign/{id}/floorplan  proposed/current floor plan image or PDF
  POST /redesign/{id}/visualize  AI image from the same spec (job)
  GET  /redesign/{id}/visualization.png
"""
from __future__ import annotations

import base64
import logging
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app import image_providers, room_analyzer, vastu_rules, vggt_service
from app import orientation as ori
from app.config import settings
from app.ingest import normalise_image_bytes, read_upload
from app.room_analyzer import analyze_room_image, furniture_candidates
from app.routers import analysis as analysis_router
from app.routers import redesign as redesign_router
from app.schemas import (
    CardinalDirection,
    RoomLayout,
    RoomLayoutRequest,
    RoomType,
    VastuRequest,
    error_body,
)
from floorplan import create_floorplan
from vastu_engine import DIRECTIONAL_RULES, analyze_vastu, analyze_vastu_coordinates

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vastu")
settings.ensure_dirs()

# ============================================================
# APPLICATION SETUP
# ============================================================

app = FastAPI(
    title="Vastu AI Backend",
    description=(
        "Room photo analysis (VGGT + YOLO), orientation-aware floor plans, "
        "a configurable Vastu rules engine, and AI interior redesign."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router.router)
app.include_router(redesign_router.router)


@app.exception_handler(ori.OrientationConflict)
async def _orientation_conflict(_: Request, exc: ori.OrientationConflict):
    return JSONResponse(status_code=422, content={"detail": error_body("orientation_conflict", str(exc), details=exc.details)})


@app.exception_handler(ori.OrientationError)
async def _orientation_error(_: Request, exc: ori.OrientationError):
    return JSONResponse(status_code=422, content={"detail": error_body("orientation_invalid", str(exc))})


@app.exception_handler(image_providers.ImageProviderError)
async def _provider_error(_: Request, exc: image_providers.ImageProviderError):
    return JSONResponse(status_code=exc.status_code, content={"detail": error_body(exc.code, exc.message, hint=exc.hint)})


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    # Keep FastAPI's standard 422 body (list of issues); just log it for debugging.
    log.info("Validation failed for %s %s: %s", request.method, request.url.path, exc.errors()[:3])
    return await request_validation_exception_handler(request, exc)


# ============================================================
# OPENAPI CUSTOMIZATION
# ============================================================

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes, openapi_version="3.0.3")
    # Keep multi-image uploads represented as binary files in Swagger.
    for body_name in (
        "Body_analyze_room_multiple_analyze_room_multiple_post",
        "Body_create_room_analysis_job_room_analysis_jobs_post",
    ):
        files_schema = schema.get("components", {}).get("schemas", {}).get(body_name, {}).get("properties", {}).get("files")
        if files_schema:
            files_schema["items"] = {"type": "string", "format": "binary"}
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# ============================================================
# HOME AND HEALTH
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Welcome to Vastu AI",
        "status": "running",
        "version": app.version,
        "docs": "/docs",
        "features": [
            "Single- and multi-image room analysis (YOLO)",
            "VGGT-based geometry reconstruction (when torch + weights are available)",
            "Orientation-aware floor plans (PNG / PDF)",
            "Configurable traditional Vastu rules engine",
            "Constraint-based redesign planner",
            "AI redesign visualization (when an image provider is configured)",
        ],
    }


@app.get("/health")
def health():
    detection_ok, detection_reason = room_analyzer.detection_available()
    vggt = vggt_service.availability()
    provider = image_providers.provider_status()
    return {
        "status": "healthy",
        "version": app.version,
        "capabilities": {
            "object_detection": {"available": detection_ok, "reason": detection_reason, "model": "YOLOv8n"},
            "geometry_reconstruction": {
                "available": vggt["available"], "reason": vggt["reason"], "note": vggt.get("note"),
                "model": vggt["model_id"], "weights_cached": vggt["weights_cached"],
            },
            "image_generation": {"available": provider["configured"], "provider": provider["active"], "reason": provider["reason"]},
        },
        "limits": {
            "max_image_mb": settings.max_image_bytes // (1024 * 1024),
            "max_photos": settings.max_room_images,
            "vggt_max_photos": settings.vggt_max_images,
        },
    }


# ============================================================
# SHARED IMAGE VALIDATION AND ANALYSIS (legacy endpoints)
# ============================================================

async def read_and_analyze_image(file: UploadFile) -> dict:
    """Validate an uploaded image and analyze its visible objects."""
    data, name = await read_upload(file)
    normalise_image_bytes(data, name)           # raises 400 for undecodable / tiny images
    ok, reason = room_analyzer.detection_available()
    if not ok:
        raise HTTPException(503, detail=error_body("detection_unavailable", reason))
    try:
        return analyze_room_image(data)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, detail=f"Could not analyze {name}: {exc}") from exc


# ============================================================
# SINGLE-IMAGE ROOM ANALYSIS
# ============================================================

@app.post("/analyze-room")
async def analyze_room(file: Annotated[UploadFile, File(...)]):
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
    files: list[UploadFile] = File(..., description="Upload between 1 and 12 room images."),
):
    """Fast, independent YOLO pass over each photo. Used to pre-fill the furniture review step."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one room image.")
    if len(files) > settings.max_room_images:
        raise HTTPException(status_code=400, detail=f"Upload no more than {settings.max_room_images} images.")

    analyzed_images, per_image = [], []
    for file in files:
        analysis = await read_and_analyze_image(file)
        analyzed_images.append({"filename": file.filename, "status": "analyzed", "image_analysis": analysis})
        per_image.append(analysis["detected_objects"])

    total_detections = sum(i["image_analysis"].get("detected_object_count", 0) for i in analyzed_images)
    return {
        "status": "multi_image_analysis_completed",
        "image_count": len(analyzed_images),
        "total_detections_across_images": total_detections,
        "images": analyzed_images,
        "furniture_candidates": furniture_candidates(per_image),
        "geometry_status": "not_reconstructed",
        "note": (
            "Images are analyzed independently. The same physical object may appear in multiple images "
            "(furniture_candidates uses the maximum count seen in any one photo as an estimate for you to confirm). "
            "Room dimensions and a shared coordinate system are not reconstructed by this endpoint - use "
            "POST /room-analysis/jobs for that."
        ),
    }


# ============================================================
# FLOOR PLAN GENERATION AND EXPORT
# ============================================================

def _floorplan_response(data: bytes, fmt: str) -> Response:
    return Response(
        content=data,
        media_type="image/png" if fmt == "png" else "application/pdf",
        headers={"Content-Disposition": f"inline; filename=floorplan.{fmt}"},
    )


@app.get("/floorplan")
def generate_floorplan(
    width: float = 4.0,
    length: float = 3.5,
    room_type: RoomType = "bedroom",
    format: Literal["png", "pdf"] = "png",
    top_edge_direction: CardinalDirection | None = None,
    north_direction: CardinalDirection = "north",
):
    """
    Generate a preliminary floor plan.

    ``top_edge_direction`` is the compass direction represented by the TOP edge of the drawing.
    ``north_direction`` is its DEPRECATED alias (same meaning - it does not say where north is drawn).
    """
    if not (2 <= width <= 15 and 2 <= length <= 15):
        raise HTTPException(400, detail="Room width and length must each be between 2 and 15 metres.")
    try:
        data = create_floorplan(width=width, length=length, room_type=room_type, output_format=format,
                                top_edge_direction=top_edge_direction or north_direction)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return _floorplan_response(data, format)


class FloorplanRenderRequest(BaseModel):
    layout: RoomLayout
    format: Literal["png", "pdf"] = "png"
    title: str | None = None


@app.post("/floorplan")
def render_floorplan(req: FloorplanRenderRequest):
    """Render a structured layout (room, openings, furniture, confirmed orientation) to PNG or PDF."""
    layout = req.layout
    if not (2 <= layout.width <= 15 and 2 <= layout.length <= 15):
        raise HTTPException(400, detail="Room width and length must each be between 2 and 15 metres.")
    try:
        data = create_floorplan(
            width=layout.width, length=layout.length, room_type=layout.room_type, output_format=req.format,
            placements=[p.model_dump() for p in layout.placements], openings=[o.model_dump() for o in layout.openings],
            top_edge_direction=layout.resolved_orientation().top_edge_direction,
            dimensions_source=layout.dimensions_source, title=req.title,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return _floorplan_response(data, req.format)


# ============================================================
# VASTU RULES
# ============================================================

@app.get("/vastu/rules")
def get_vastu_rules():
    catalog = vastu_rules.rule_catalog()
    return {
        "available_room_types": list(DIRECTIONAL_RULES.keys()),
        "rules": DIRECTIONAL_RULES,            # legacy 4-direction preferences (unchanged shape)
        "rule_catalog": catalog["rules"],      # structured 8-zone rules used by the engine
        "zones": list(ori.ZONES),
        "note": (
            "These are configurable traditional Vastu preferences. "
            "They do not automatically determine room orientation."
        ),
        "disclaimer": catalog["disclaimer"],
    }


# ============================================================
# VASTU ANALYSIS
# ============================================================

@app.post("/vastu/analyze")
def vastu_analysis(request: VastuRequest):
    """
    Two request forms:
      * legacy ``{room_type, placements: {item: direction}}`` -> original response shape
      * structured ``{layout: RoomLayout}`` -> full rules-engine report
    """
    if request.layout is not None:
        return vastu_rules.evaluate(request.layout)
    try:
        return analyze_vastu(room_type=request.room_type, placements=request.placements)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================
# COMBINED ROOM LAYOUT AND VASTU ANALYSIS
# ============================================================

@app.post("/room-layout/analyze")
def analyze_room_layout(request: RoomLayoutRequest):
    """
    Generate a preliminary floor plan and coordinate-based Vastu report.

    Coordinate convention:
      - x=0 is the left edge of the drawing; y=0 is the bottom edge.
      - ``top_edge_direction`` (alias ``north_direction``) is the real-world
        direction of the drawing's TOP edge.
      - Furniture coordinates are not rotated.
    """
    if not (2 <= request.width <= 15 and 2 <= request.length <= 15):
        raise HTTPException(400, detail="Room width and length must each be between 2 and 15 metres.")

    placements = [p.model_dump() for p in request.placements]
    for placement in placements:
        item = placement["item"]
        if placement["x"] + placement["width"] > request.width:
            raise HTTPException(400, detail=f"'{item}' extends beyond the room width. Check its x-coordinate and width.")
        if placement["y"] + placement["length"] > request.length:
            raise HTTPException(400, detail=f"'{item}' extends beyond the room length. Check its y-coordinate and length.")

    # One resolution path for orientation; conflicts are reported, never silently resolved.
    try:
        orientation = request.orientation_input().resolve()
    except ori.OrientationConflict as exc:
        raise HTTPException(422, detail={"message": str(exc), "orientation_check": exc.details}) from exc
    except ori.OrientationError as exc:
        raise HTTPException(422, detail=error_body("orientation_required", str(exc))) from exc

    orientation_check = {
        "status": (
            "confirmed_by_two_inputs" if request.compass_heading_degrees is not None
            else "manual_direction_only" if request.manual_compass_direction else "orientation_not_confirmed"
        ),
        "compass_heading_degrees": request.compass_heading_degrees,
        "compass_cardinal_direction": ori.heading_to_cardinal(request.compass_heading_degrees) if request.compass_heading_degrees is not None else None,
        "manual_compass_direction": request.manual_compass_direction,
        "directions_match": True if request.compass_heading_degrees is not None else None,
    }
    top = orientation.top_edge_direction

    try:
        layout = RoomLayout(
            room_type=request.room_type, width=request.width, length=request.length,
            orientation={"top_edge_direction": top}, openings=request.openings, placements=request.placements,
        )
        floorplan_png = create_floorplan(
            width=request.width, length=request.length, room_type=request.room_type, output_format="png",
            placements=placements, openings=[o.model_dump() for o in request.openings], top_edge_direction=top,
        )
        vastu_result = analyze_vastu_coordinates(
            room_type=request.room_type, placements=placements, room_width=request.width,
            room_length=request.length, north_direction=top,
        )
        vastu_report = vastu_rules.evaluate(layout)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    return {
        "status": "layout_and_vastu_analysis_completed",
        "room_type": request.room_type,
        "dimensions_metres": {"width": request.width, "length": request.length},
        "north_direction": top,                       # legacy key: direction of the TOP edge
        "top_edge_direction": top,
        "orientation": orientation.to_dict(),
        "orientation_check": orientation_check,
        "coordinate_convention": {
            "origin": "bottom_left", "x_axis": "right", "y_axis": "up",
            "top_edge_direction": top, "edges": orientation.edges, "furniture_coordinates_rotated": False,
        },
        "placements": placements,
        "openings": [o.model_dump() for o in request.openings],
        "layout_status": "generated_from_user_coordinates",
        "vastu_analysis": vastu_result,               # legacy 4-direction summary
        "vastu_report": vastu_report,                 # structured rules-engine report
        "floorplan_png_base64": base64.b64encode(floorplan_png).decode("utf-8"),
        "next_steps": [
            "Review the floor plan and confirm the orientation.",
            "Run POST /redesign/plan to generate a proposed layout.",
        ],
        "limitations": [
            "Room geometry is not reconstructed automatically by this endpoint; dimensions and positions are user-supplied.",
            "A compass heading validates the phone direction, not the room geometry.",
            "Furniture-facing and bed headboard directions are only judged when recorded.",
            "Traditional Vastu recommendations are configurable preferences, not scientifically established requirements.",
        ],
    }

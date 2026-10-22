"""AI redesign: structured plan (floor plan) + visualization from the SAME spec."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from app import image_providers as ip
from app import jobs, orientation as ori, redesign, storage
from app.ingest import normalise_image_bytes, read_upload
from app.schemas import RedesignPlanRequest, RoomLayout, error_body
from floorplan import create_floorplan
from io import BytesIO

log = logging.getLogger(__name__)
router = APIRouter(prefix="/redesign", tags=["redesign"])


def _spec_or_404(rid: str) -> dict:
    spec = storage.load_redesign(rid)
    if spec is None:
        raise HTTPException(404, detail=error_body("redesign_not_found", "No redesign with that id."))
    return spec


@router.post("/plan")
def plan_redesign(req: RedesignPlanRequest):
    """Compute the proposed layout, Vastu before/after, budget estimate and design spec."""
    try:
        req.layout.resolved_orientation()
    except ori.OrientationError as exc:
        raise HTTPException(422, detail=error_body("orientation_invalid", str(exc))) from exc
    spec = redesign.create_redesign(req.layout, req.preferences)
    storage.save_redesign(spec["id"], spec)
    return spec


@router.get("/{rid}")
def get_redesign(rid: str):
    return _spec_or_404(rid)


@router.get("/{rid}/floorplan")
def redesign_floorplan(rid: str, which: str = Query("proposed", pattern="^(proposed|current)$"),
                       format: str = Query("png", pattern="^(png|pdf)$")):
    """Render the proposed (or original) floor plan from the stored spec."""
    spec = _spec_or_404(rid)
    layout = RoomLayout.model_validate(spec["proposed_layout" if which == "proposed" else "source_layout"])
    data = create_floorplan(
        width=layout.width, length=layout.length, room_type=layout.room_type, output_format=format,
        placements=[p.model_dump() for p in layout.placements], openings=[o.model_dump() for o in layout.openings],
        top_edge_direction=layout.resolved_orientation().top_edge_direction, dimensions_source=layout.dimensions_source,
        title=("Proposed" if which == "proposed" else "Current") + f" {layout.room_type.replace('_', ' ')} layout",
    )
    return Response(data, media_type="image/png" if format == "png" else "application/pdf",
                    headers={"Content-Disposition": f"inline; filename={which}-floorplan.{format}"})


@router.post("/{rid}/visualize", status_code=202)
async def visualize(rid: str, reference_image: UploadFile | None = File(default=None)):
    """
    Generate the redesigned room visualization from the stored spec (+ optional reference photo).
    Returns an explicit 503 if no image provider is configured - never a placeholder.
    """
    spec = _spec_or_404(rid)
    try:
        provider = ip.get_provider()
    except ip.ImageProviderError as exc:
        raise HTTPException(exc.status_code, detail=error_body(exc.code, exc.message, hint=exc.hint)) from exc

    reference_jpeg = None
    if reference_image is not None:
        data, name = await read_upload(reference_image)
        img = normalise_image_bytes(data, name)
        img.thumbnail((2048, 2048))
        buf = BytesIO(); img.save(buf, "JPEG", quality=92); reference_jpeg = buf.getvalue()

    prompt = redesign.build_prompt(spec, has_reference_image=reference_jpeg is not None)

    def work(ctx: jobs.JobContext):
        ctx.start("brief", "Building the design brief from the redesign spec")
        ctx.done("brief")
        ctx.start("generate", f"Generating with {provider.name} ({provider.model}). This can take a minute or two.")
        try:
            result = provider.generate(prompt, reference_jpeg)
        except ip.ImageProviderError as exc:
            raise jobs.JobError(exc.code, exc.message, hint=exc.hint) from exc
        storage.visualization_path(rid).write_bytes(result.png_bytes)
        ctx.done("generate")
        ctx.start("save")
        viz = {
            "image_url": f"/redesign/{rid}/visualization.png", "provider": result.provider, "model": result.model,
            "prompt": prompt, "reference_image_used": reference_jpeg is not None,
            "generated_at": datetime.now(timezone.utc).isoformat(), "disclaimer": ip.DISCLAIMER,
        }
        latest = storage.load_redesign(rid) or spec
        latest["visualization"] = viz
        storage.save_redesign(rid, latest)
        ctx.done("save")
        return viz

    job = jobs.submit("redesign_visualization",
                      [("brief", "Preparing the design brief"), ("generate", "Generating the redesigned room image"), ("save", "Saving the result")],
                      work)
    return {"job_id": job.id, "status": job.status, "status_url": f"/jobs/{job.id}", "provider": provider.name}


@router.get("/{rid}/visualization.png")
def get_visualization(rid: str):
    try:
        path = storage.visualization_path(rid)
    except ValueError:
        path = None
    if path is None or not path.is_file():
        raise HTTPException(404, detail=error_body("visualization_not_found", "No visualization has been generated for this redesign yet."))
    return FileResponse(path, media_type="image/png")

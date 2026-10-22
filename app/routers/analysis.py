"""Room-analysis jobs: photos + confirmed context -> structured layout (VGGT + YOLO + geometry)."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app import jobs, pipeline, storage
from app.config import settings
from app.ingest import ingest_uploads
from app.orientation import OrientationConflict, OrientationError
from app.schemas import AnalysisMetadata, error_body

router = APIRouter(tags=["room analysis"])


@router.post("/room-analysis/jobs", status_code=202)
async def create_room_analysis_job(
    files: list[UploadFile] = File(..., description="Photos of the SAME room (1-12). Photo 1 is the reference view."),
    metadata: str = Form(..., description="JSON matching AnalysisMetadata."),
):
    """
    Validate the photos synchronously (bad input fails here with a 4xx), then run
    detection + reconstruction in the background. Poll ``GET /jobs/{job_id}``.
    """
    try:
        meta = AnalysisMetadata.model_validate(json.loads(metadata))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, detail=error_body("invalid_metadata", f"The metadata JSON is invalid: {exc}")) from exc

    if meta.orientation is not None:
        try:
            meta.orientation.resolve()
        except OrientationConflict as exc:
            raise HTTPException(422, detail=error_body("orientation_conflict", str(exc), details=exc.details)) from exc
        except OrientationError as exc:
            raise HTTPException(422, detail=error_body("orientation_invalid", str(exc))) from exc

    job_id = uuid.uuid4().hex[:16]
    settings.ensure_dirs()
    images = await ingest_uploads(files, storage.job_dir(job_id) / "images")
    job = jobs.submit("room_analysis", pipeline.STAGES, lambda ctx: pipeline.run_room_analysis(ctx, images, meta), job_id=job_id)
    return {"job_id": job.id, "status": job.status, "status_url": f"/jobs/{job.id}", "photos_accepted": len(images)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail=error_body("job_not_found", "Unknown or expired job. Jobs are kept in memory and lost on server restart; please resubmit."))
    return job.public()

"""
Room-analysis pipeline: photos + user-confirmed context -> structured layout.

Honesty rules baked in:
  * Never returns reconstructed geometry unless VGGT really ran on the photos.
  * Never invents dimensions: with neither reconstruction nor user measurements
    the room is reported as ``needs_manual_input``.
  * Never invents compass directions: orientation is only what the user confirmed.
  * Every placed item records HOW it was placed (user / reconstructed) and every
    unplaced item is returned in ``unplaced`` rather than being given a guess.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from app import geometry as geo
from app import room_analyzer, vggt_service
from app.config import settings
from app.furniture import default_size, display_label
from app.ingest import IngestedImage
from app.jobs import JobContext
from app.schemas import AnalysisMetadata

log = logging.getLogger(__name__)

STAGES = [
    ("images", "Validating and preparing photos"),
    ("detection", "Detecting furniture and objects"),
    ("reconstruction", "Analyzing room geometry (VGGT)"),
    ("layout", "Preparing the current floor plan"),
]


def _sample_for_vggt(images: list[IngestedImage]) -> list[IngestedImage]:
    cap = settings.vggt_max_images
    if len(images) <= cap:
        return images
    idx = np.linspace(0, len(images) - 1, cap).round().astype(int)   # keep photo 1 (the reference) and spread the rest
    return [images[i] for i in sorted(set(idx.tolist()))]


def run_room_analysis(ctx: JobContext, images: list[IngestedImage], meta: AnalysisMetadata) -> dict:
    warnings: list[str] = []
    ctx.start("images")
    ctx.done("images", f"{len(images)} photo(s) accepted")

    # ---- detection -----------------------------------------------------------
    detections: list[list[dict]] = []
    if not meta.run_detection:
        ctx.skip("detection", "Object detection was turned off for this run.")
    else:
        ok, why = room_analyzer.detection_available()
        if not ok:
            ctx.skip("detection", why)
            warnings.append(f"Object detection did not run: {why}")
        else:
            ctx.start("detection", f"Running YOLO on {len(images)} photo(s)")
            try:
                for img in images:
                    with Image.open(img.path) as im:
                        detections.append(room_analyzer.detect_objects(np.array(im.convert("RGB"))))
                total = sum(len(d) for d in detections)
                ctx.done("detection", f"{total} object(s) found across {len(images)} photo(s)")
            except Exception as exc:
                log.exception("Detection failed")
                detections = []
                ctx.fail("detection", f"YOLO failed: {exc}")
                warnings.append(f"Object detection failed: {exc}")

    # ---- reconstruction ----------------------------------------------------------
    recon_result = None
    recon = None
    vggt_out = None
    vggt_subset: list[IngestedImage] = []
    recon_error = None
    if not meta.run_vggt:
        ctx.skip("reconstruction", "Geometry reconstruction was turned off for this run.")
    elif len(images) < 2:
        ctx.skip("reconstruction", "Reconstruction needs at least 2 overlapping photos.")
        warnings.append("Only one photo was provided, so room geometry could not be reconstructed.")
    else:
        info = vggt_service.availability()
        if not info["available"]:
            ctx.skip("reconstruction", info["reason"])
            recon_error = info["reason"]
        else:
            vggt_subset = _sample_for_vggt(images)
            note = f"Running VGGT on {len(vggt_subset)} photo(s) on {vggt_service.settings.vggt_device}"
            if info.get("note"):
                note += f". {info['note']}"
            ctx.start("reconstruction", note)
            try:
                vggt_out = vggt_service.run_vggt([i.path for i in vggt_subset], [(i.width, i.height) for i in vggt_subset])
                recon_result, recon = geo.reconstruct_room(
                    vggt_out.points, vggt_out.conf, vggt_out.valid, vggt_out.extrinsics,
                    user_width=meta.width, user_length=meta.length,
                )
                ctx.done("reconstruction", f"Footprint estimated from {recon_result['metrics']['points_used']} 3D points (confidence: {recon_result['confidence']})")
            except Exception as exc:
                log.exception("Reconstruction failed")
                recon_error = str(exc)
                recon_result = recon = None
                ctx.fail("reconstruction", recon_error)
        if recon_error:
            warnings.append(f"Automatic reconstruction did not run: {recon_error}")

    # ---- layout --------------------------------------------------------------------
    ctx.start("layout")
    if recon_result:
        room = {**recon_result["room"]}
        warnings.extend(recon_result["warnings"])
    elif meta.width and meta.length:
        room = {"width": meta.width, "length": meta.length, "dimensions_source": "user_provided"}
    else:
        room = None
        warnings.append("No room dimensions are available. Enter the width and length to build the floor plan.")

    # Localise detections in the plan frame (only possible with a real reconstruction).
    localised: dict[str, list[dict]] = {}
    if recon is not None and vggt_out is not None and detections:
        cands: list[dict] = []
        centers = geo.camera_centers(vggt_out.extrinsics)
        index_of = {img.index: k for k, img in enumerate(vggt_subset)}
        for img_idx, dets in enumerate(detections):
            k = index_of.get(img_idx)
            if k is None:
                continue
            m = vggt_out.mappings[k]
            for det in dets:
                mapping = room_analyzer.COCO_TO_FURNITURE.get(det["label"])
                if not mapping:
                    continue
                b = det["bounding_box"]
                loc = geo.localize_detection(
                    recon, vggt_out.points[k], vggt_out.conf[k], vggt_out.valid[k],
                    m.bbox(b["x_min"], b["y_min"], b["x_max"], b["y_max"]), mapping["type"], centers[k],
                )
                if loc:
                    cands.append({**loc, "item": mapping["type"], "seen_in": [img_idx]})
        for m in geo.merge_candidates(cands):
            localised.setdefault(m["item"], []).append(m)
        for lst in localised.values():
            lst.sort(key=lambda m: -m["n_points"])

    placements, unplaced = [], []
    for cand in meta.furniture:
        w, l = (cand.width, cand.length) if (cand.width and cand.length) else default_size(cand.item)
        dims_source = cand.dims_source if (cand.width and cand.length) else "default"
        base = {"id": cand.id, "item": cand.item, "label": cand.label or display_label(cand.item),
                "source": cand.source, "confirmed": True, "dims_source": dims_source}
        if room is None:
            unplaced.append({**base, "width": w, "length": l, "reason": "Room dimensions are not available yet."})
        elif cand.x is not None and cand.y is not None:
            w, l = min(w, room["width"]), min(l, room["length"])
            placements.append({**base, "x": round(min(cand.x, room["width"] - w), 3), "y": round(min(cand.y, room["length"] - l), 3),
                               "width": w, "length": l, "position_source": "user"})
        elif localised.get(cand.item):
            hit = localised[cand.item].pop(0)
            fp = geo.place_footprint(cand.item, hit["x"], hit["y"], room["width"], room["length"],
                                     dims=(w, l) if dims_source == "user" else None)
            placements.append({**base, **fp, "position_source": "reconstructed",
                               "seen_in_photos": hit["seen_in"]})
        else:
            unplaced.append({**base, "width": w, "length": l,
                             "reason": "Its position could not be determined from the photos; place it on the floor plan."})

    if any(p["position_source"] == "reconstructed" for p in placements):
        warnings.append("Furniture positions marked 'reconstructed' are estimates from the photos (typically within about 0.5-1 m). Please check and adjust them.")
    if unplaced:
        warnings.append(f"{len(unplaced)} item(s) still need to be placed on the floor plan by you.")

    geometry_status = "reconstructed" if recon_result else "not_reconstructed"
    ctx.done("layout", "Floor plan prepared" if room else "Waiting for room dimensions")

    return {
        "geometry_status": geometry_status,
        "reconstruction_completeness": "partial_estimate" if recon_result else "none",
        "geometry": recon_result,
        "reconstruction_unavailable_reason": recon_error,
        "layout_status": (
            "reconstructed_estimate" if recon_result else ("manual_dimensions" if room else "needs_manual_input")
        ),
        "room": room,
        "orientation": meta.orientation.resolve().to_dict() if meta.orientation else None,
        "openings": [o.model_dump() for o in meta.openings],
        "placements": placements,
        "unplaced": unplaced,
        "detections": [
            {"photo_index": i, "filename": images[i].filename, "objects": d} for i, d in enumerate(detections)
        ],
        "furniture_candidates": room_analyzer.furniture_candidates(detections) if detections else [],
        "warnings": warnings,
        "limitations": [
            "VGGT yields an approximate, non-metric reconstruction; real dimensions come from your measurements.",
            "Doors and windows are not detected automatically; add them on the floor plan.",
            "Compass directions are never inferred from the photos; they come from the orientation you confirmed.",
        ],
    }

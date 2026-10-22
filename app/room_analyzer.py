"""
YOLO-based object detection for room photos.

Object detection is NOT room reconstruction: it yields labelled boxes in image
pixels and nothing about real-world size or position.
"""
from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageStat

from app.config import ROOT_DIR
from app.furniture import COCO_TO_FURNITURE, display_label

log = logging.getLogger(__name__)

YOLO_WEIGHTS = ROOT_DIR / "yolov8n.pt"


def detection_available() -> tuple[bool, str | None]:
    if importlib.util.find_spec("ultralytics") is None:
        return False, "The 'ultralytics' package is not installed (pip install ultralytics)."
    return True, None


@lru_cache(maxsize=1)
def get_yolo_model():
    """Load YOLO once. Uses the bundled weights next to the project, else downloads by name."""
    from ultralytics import YOLO   # lazy: the API must start even without ultralytics

    return YOLO(str(YOLO_WEIGHTS) if YOLO_WEIGHTS.is_file() else "yolov8n.pt")


def detect_objects(image_rgb: np.ndarray, conf: float = 0.25) -> list[dict]:
    """Run YOLO on an RGB array; returns boxes in the array's pixel coordinates."""
    model = get_yolo_model()
    results = model.predict(source=image_rgb, device="cpu", conf=conf, verbose=False)
    detected = []
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detected.append({
                "label": result.names[class_id],
                "confidence": round(float(box.conf[0].item()), 3),
                "bounding_box": {"x_min": round(x1, 1), "y_min": round(y1, 1), "x_max": round(x2, 1), "y_max": round(y2, 1)},
            })
    return detected


def analyze_room_image(image_bytes: bytes) -> dict:
    """Basic image properties + visible objects. (Public contract of the original endpoint.)"""
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")

    width, height = image.size
    brightness = ImageStat.Stat(image).mean
    aspect_ratio = round(width / height, 3)
    average_brightness = round(sum(brightness) / 3, 1)

    if aspect_ratio > 1.25:
        orientation_hint = "landscape"
    elif aspect_ratio < 0.8:
        orientation_hint = "portrait"
    else:
        orientation_hint = "approximately_square"

    detected_objects = detect_objects(np.array(image))

    return {
        "image_width": width,
        "image_height": height,
        "aspect_ratio": aspect_ratio,
        "orientation_hint": orientation_hint,
        "average_brightness": average_brightness,
        "detected_objects": detected_objects,
        "detected_object_count": len(detected_objects),
        "detection_model": "YOLOv8n",
        "geometry_status": "not_reconstructed",
        "message": (
            "Image properties and visible objects were analyzed. "
            "Bounding boxes are measured in image pixels. "
            "Room boundaries, real-world dimensions, and full "
            "room geometry have not been reconstructed."
        ),
    }


def furniture_candidates(per_image: list[list[dict]]) -> list[dict]:
    """
    Collapse per-photo detections into furniture CANDIDATES for the user to confirm.

    The same physical object appears in several overlapping photos, so the best
    available estimate of how many exist is the MAXIMUM count seen in any single
    photo (not the sum). It is still only an estimate - the user confirms it.
    """
    by_type: dict[str, dict] = {}
    for img_idx, detections in enumerate(per_image):
        counts: dict[str, int] = {}
        for det in detections:
            mapping = COCO_TO_FURNITURE.get(det["label"])
            if not mapping:
                continue
            counts[mapping["type"]] = counts.get(mapping["type"], 0) + 1
            entry = by_type.setdefault(mapping["type"], {
                "item": mapping["type"], "label": display_label(mapping["type"]),
                "estimated_count": 0, "max_confidence": 0.0, "photos": [],
                "coco_label": det["label"], "mapping_uncertain": bool(mapping.get("uncertain")),
            })
            entry["max_confidence"] = max(entry["max_confidence"], det["confidence"])
            if img_idx not in entry["photos"]:
                entry["photos"].append(img_idx)
        for item, n in counts.items():
            by_type[item]["estimated_count"] = max(by_type[item]["estimated_count"], n)
    return sorted(by_type.values(), key=lambda c: -c["max_confidence"])


from io import BytesIO
from functools import lru_cache

import numpy as np
from PIL import Image, ImageStat
from ultralytics import YOLO


@lru_cache(maxsize=1)
def get_yolo_model():
    """
    Load YOLO only once and reuse it for subsequent requests.
    The model weights are downloaded automatically if unavailable.
    """
    return YOLO("yolov8n.pt")


def analyze_room_image(image_bytes: bytes) -> dict:
    """
    Extract basic image properties and detect visible objects with YOLO.

    Note:
    Object detection does not reconstruct room geometry or dimensions.
    """
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

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

    # Convert the image into a NumPy array for YOLO.
    image_array = np.array(image)

    # Run object detection on the CPU.
    model = get_yolo_model()
    results = model.predict(
        source=image_array,
        device="cpu",
        conf=0.25,
        verbose=False,
    )

    detected_objects = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            class_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            detected_objects.append({
                "label": result.names[class_id],
                "confidence": round(confidence, 3),
                "bounding_box": {
                    "x_min": round(x1, 1),
                    "y_min": round(y1, 1),
                    "x_max": round(x2, 1),
                    "y_max": round(y2, 1),
                },
            })

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

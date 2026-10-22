"""Furniture catalogue: default footprints, display metadata, and YOLO (COCO) label mapping."""
from __future__ import annotations

# width = extent along the plan's x axis, length = extent along y (metres).
# These are *typical* sizes used only as defaults/estimates - never as measurements.
CATALOG: dict[str, dict] = {
    "bed":          {"label": "Bed",          "width": 1.6, "length": 2.0, "heavy": True,  "color": "#c9d6cf", "category": "sleep"},
    "single_bed":   {"label": "Single bed",   "width": 1.0, "length": 2.0, "heavy": True,  "color": "#c9d6cf", "category": "sleep"},
    "nightstand":   {"label": "Nightstand",   "width": 0.45, "length": 0.4, "heavy": False, "color": "#dcd0bb", "category": "sleep"},
    "wardrobe":     {"label": "Wardrobe",     "width": 1.2, "length": 0.6, "heavy": True,  "color": "#d9c7a3", "category": "storage"},
    "dresser":      {"label": "Dresser",      "width": 1.0, "length": 0.5, "heavy": True,  "color": "#d9c7a3", "category": "storage"},
    "storage":      {"label": "Storage unit", "width": 0.9, "length": 0.45, "heavy": True, "color": "#d9c7a3", "category": "storage"},
    "bookshelf":    {"label": "Bookshelf",    "width": 0.9, "length": 0.35, "heavy": True, "color": "#d9c7a3", "category": "storage"},
    "desk":         {"label": "Desk",         "width": 1.2, "length": 0.6, "heavy": False, "color": "#e6dcb8", "category": "work"},
    "chair":        {"label": "Chair",        "width": 0.5, "length": 0.5, "heavy": False, "color": "#cfe0c3", "category": "seating"},
    "sofa":         {"label": "Sofa",         "width": 2.0, "length": 0.85, "heavy": True, "color": "#bfd3d6", "category": "seating"},
    "armchair":     {"label": "Armchair",     "width": 0.8, "length": 0.8, "heavy": False, "color": "#bfd3d6", "category": "seating"},
    "table":        {"label": "Table",        "width": 0.8, "length": 0.8, "heavy": False, "color": "#e3d5b5", "category": "table"},
    "coffee_table": {"label": "Coffee table", "width": 1.0, "length": 0.55, "heavy": False, "color": "#e3d5b5", "category": "table"},
    "dining_table": {"label": "Dining table", "width": 1.4, "length": 0.9, "heavy": False, "color": "#e3d5b5", "category": "table"},
    "tv_unit":      {"label": "TV / TV unit", "width": 1.4, "length": 0.4, "heavy": False, "color": "#cfcfca", "category": "media"},
    "counter":      {"label": "Counter",      "width": 2.0, "length": 0.6, "heavy": True,  "color": "#d4d4cf", "category": "kitchen"},
    "stove":        {"label": "Stove / hob",  "width": 0.6, "length": 0.6, "heavy": False, "color": "#e4b9a8", "category": "kitchen"},
    "refrigerator": {"label": "Refrigerator", "width": 0.7, "length": 0.7, "heavy": True,  "color": "#cfe3e6", "category": "kitchen"},
    "sink":         {"label": "Sink",         "width": 0.6, "length": 0.6, "heavy": False, "color": "#cfe3e6", "category": "kitchen"},
    "plant":        {"label": "Plant",        "width": 0.4, "length": 0.4, "heavy": False, "color": "#c5dcb4", "category": "decor"},
    "other":        {"label": "Other item",   "width": 0.6, "length": 0.6, "heavy": False, "color": "#e1ddd3", "category": "other"},
}

# YOLOv8 (COCO) label -> our furniture type. Anything not listed is ignored as non-furniture.
# `uncertain=True` means the COCO class is only a loose proxy, so the UI must ask for confirmation.
COCO_TO_FURNITURE: dict[str, dict] = {
    "bed":          {"type": "bed"},
    "couch":        {"type": "sofa"},
    "chair":        {"type": "chair"},
    "dining table": {"type": "dining_table"},
    "tv":           {"type": "tv_unit"},
    "refrigerator": {"type": "refrigerator"},
    "sink":         {"type": "sink"},
    "potted plant": {"type": "plant"},
    "oven":         {"type": "stove", "uncertain": True},
}


def default_size(item: str) -> tuple[float, float]:
    entry = CATALOG.get(item, CATALOG["other"])
    return entry["width"], entry["length"]


def display_label(item: str) -> str:
    entry = CATALOG.get(item)
    return entry["label"] if entry else item.replace("_", " ").title()


def is_heavy(item: str) -> bool:
    return bool(CATALOG.get(item, {}).get("heavy", False))


def normalize_item(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")

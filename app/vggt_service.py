"""
VGGT inference wrapper.

VGGT (facebook/VGGT-1B) predicts camera poses, depth and per-pixel 3D points
from a set of photos. This module loads it lazily (importing torch and ~5 GB of
weights only when a reconstruction is actually requested) and converts its raw
output into numpy arrays that ``app.geometry`` consumes.

It never fabricates output: if torch, the weights or enough photos are missing,
``availability()`` says exactly why and callers must fall back honestly.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import ROOT_DIR, settings

log = logging.getLogger(__name__)

VGGT_SRC = ROOT_DIR / "vggt"            # the cloned facebookresearch/vggt repo
TARGET = 518                            # VGGT's working resolution
_load_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pure helpers (no torch)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PadMapping:
    """Where an original image sits inside VGGT's 518x518 'pad'-mode tensor."""
    scale_x: float
    scale_y: float
    pad_left: int
    pad_top: int
    new_w: int
    new_h: int

    def valid_mask(self) -> np.ndarray:
        m = np.zeros((TARGET, TARGET), dtype=bool)
        m[self.pad_top:self.pad_top + self.new_h, self.pad_left:self.pad_left + self.new_w] = True
        return m

    def bbox(self, x1, y1, x2, y2) -> tuple[float, float, float, float]:
        return (x1 * self.scale_x + self.pad_left, y1 * self.scale_y + self.pad_top,
                x2 * self.scale_x + self.pad_left, y2 * self.scale_y + self.pad_top)


def pad_mapping(width: int, height: int) -> PadMapping:
    """
    Mirror of the arithmetic in ``vggt.utils.load_fn.load_and_preprocess_images(mode='pad')``:
    longest side -> 518 (other side rounded to a multiple of 14), then centre-padded to a square.
    """
    if width >= height:
        new_w = TARGET
        new_h = round(height * (new_w / width) / 14) * 14
    else:
        new_h = TARGET
        new_w = round(width * (new_h / height) / 14) * 14
    h_pad, w_pad = TARGET - new_h, TARGET - new_w
    return PadMapping(new_w / width, new_h / height, w_pad // 2, h_pad // 2, new_w, new_h)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def _weights_cached() -> bool:
    if settings.vggt_weights_path:
        return Path(settings.vggt_weights_path).is_file()
    try:
        from huggingface_hub import try_to_load_from_cache
        for name in ("model.safetensors", "pytorch_model.bin", "model.pt"):
            hit = try_to_load_from_cache(settings.vggt_model_id, name)
            if isinstance(hit, str):
                return True
    except Exception:    # huggingface_hub absent or cache unreadable -> unknown
        return False
    return False


def availability() -> dict:
    """Cheap, torch-free report of whether VGGT can run (used by /health and the pipeline)."""
    info = {
        "enabled_setting": settings.vggt_enabled,
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "vggt_source_present": (VGGT_SRC / "vggt" / "models" / "vggt.py").is_file(),
        "weights_cached": _weights_cached(),
        "model_id": settings.vggt_model_id,
        "device_setting": settings.vggt_device,
        "available": False,
        "reason": None,
    }
    if settings.vggt_enabled == "false":
        info["reason"] = "VGGT is disabled (VGGT_ENABLED=false)."
    elif not info["torch_installed"]:
        info["reason"] = "PyTorch is not installed. Install torch/torchvision (see README) to enable VGGT reconstruction."
    elif not info["vggt_source_present"]:
        info["reason"] = "The VGGT source (./vggt/vggt/models/vggt.py) was not found."
    elif importlib.util.find_spec("huggingface_hub") is None and not settings.vggt_weights_path:
        info["reason"] = "huggingface_hub is not installed and VGGT_WEIGHTS_PATH is not set."
    else:
        info["available"] = True
        if not info["weights_cached"] and not settings.vggt_weights_path:
            info["note"] = "Model weights are not cached yet; the first run downloads about 5 GB from Hugging Face."
    return info


# ---------------------------------------------------------------------------
# Model + inference (torch imported lazily)
# ---------------------------------------------------------------------------

def _add_vggt_to_path() -> None:
    p = str(VGGT_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)


def _device():
    import torch
    if settings.vggt_device == "cpu":
        return torch.device("cpu")
    if settings.vggt_device == "cuda" or torch.cuda.is_available():
        if not torch.cuda.is_available():
            raise RuntimeError("VGGT_DEVICE=cuda but CUDA is not available.")
        return torch.device("cuda")
    return torch.device("cpu")


@lru_cache(maxsize=1)
def _load_model():
    import torch
    _add_vggt_to_path()
    from vggt.models.vggt import VGGT

    device = _device()
    log.info("Loading VGGT (%s) on %s ...", settings.vggt_model_id, device)
    if settings.vggt_weights_path:
        model = VGGT()
        path = settings.vggt_weights_path
        if path.endswith(".safetensors"):
            from safetensors.torch import load_file
            state = load_file(path)
        else:
            state = torch.load(path, map_location="cpu")
        model.load_state_dict(state)
    else:
        model = VGGT.from_pretrained(settings.vggt_model_id)
    model = model.to(device).eval()
    return model, device


@dataclass
class VGGTOutput:
    points: np.ndarray        # (S,518,518,3)  world points, first-camera frame, arbitrary scale
    conf: np.ndarray          # (S,518,518)
    valid: np.ndarray         # (S,518,518) bool - real image content (not padding)
    extrinsics: np.ndarray    # (S,3,4) camera-from-world, OpenCV convention
    intrinsics: np.ndarray    # (S,3,3)
    mappings: list[PadMapping]
    device: str


def run_vggt(image_paths: list[Path], sizes: list[tuple[int, int]]) -> VGGTOutput:
    """Run VGGT on photos (needs >= 2). Raises with a precise reason on any failure."""
    info = availability()
    if not info["available"]:
        raise RuntimeError(info["reason"])
    if len(image_paths) < 2:
        raise RuntimeError("VGGT reconstruction needs at least 2 overlapping photos.")

    import torch
    _add_vggt_to_path()
    from vggt.utils.geometry import unproject_depth_map_to_point_map
    from vggt.utils.load_fn import load_and_preprocess_images
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    with _load_lock:
        model, device = _load_model()
        images = load_and_preprocess_images([str(p) for p in image_paths], mode="pad").to(device)
        log.info("VGGT input tensor %s on %s", tuple(images.shape), device)
        with torch.inference_mode():
            if device.type == "cuda":
                dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
                with torch.autocast("cuda", dtype=dtype):
                    pred = model(images)
            else:
                pred = model(images)

        extri, intri = pose_encoding_to_extri_intri(pred["pose_enc"], images.shape[-2:])
        extri_np = extri.squeeze(0).float().cpu().numpy()
        intri_np = intri.squeeze(0).float().cpu().numpy()
        depth = pred["depth"].squeeze(0).float().cpu().numpy()
        conf = pred["depth_conf"].squeeze(0).float().cpu().numpy()
        # The VGGT authors recommend unprojecting depth with the predicted cameras over the point head.
        points = unproject_depth_map_to_point_map(depth, extri_np, intri_np)

    mappings = [pad_mapping(w, h) for (w, h) in sizes]
    valid = np.stack([m.valid_mask() for m in mappings])
    return VGGTOutput(points=points, conf=conf, valid=valid, extrinsics=extri_np, intrinsics=intri_np,
                      mappings=mappings, device=str(device))

"""
Room geometry from VGGT-style outputs (camera poses + per-pixel 3D points).

Pure numpy - no torch - so it is unit-testable without model weights.

What this DOES NOT claim
------------------------
* VGGT output has an arbitrary (non-metric) scale. Metric dimensions come
  only from user-supplied measurements; otherwise a camera-height assumption
  is used and the result is labelled ``estimated``.
* Photos rarely cover every wall. The rectangle fitted here is the extent of
  what was SEEN; ``perimeter_coverage`` reports how much of the boundary had
  supporting points, and low coverage downgrades confidence.
* Compass directions never come from pixels. The plan's top edge is, by
  construction, the wall the REFERENCE camera (photo 1) faces; mapping that to
  a compass direction is the job of the user-confirmed orientation.
* Doors and windows are not detected here.

Frames
------
World (VGGT/OpenCV): camera x-right, y-down, z-forward, expressed in the first
camera's frame. Plan: x right, y up, bird's-eye view, metres, origin bottom-left.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.furniture import default_size

ASSUMED_CAMERA_HEIGHT_M = 1.4   # used ONLY when the user gave no dimensions; flagged as an assumption
MIN_USABLE_POINTS = 2000


class GeometryError(RuntimeError):
    """Raised when geometry cannot be reconstructed from the given data."""


# ---------------------------------------------------------------------------
# Camera helpers (extrinsics are camera-from-world, OpenCV convention)
# ---------------------------------------------------------------------------

def camera_centers(extrinsics: np.ndarray) -> np.ndarray:
    R, t = extrinsics[:, :3, :3], extrinsics[:, :3, 3]
    return -np.einsum("sji,sj->si", R, t)          # -R^T t


def camera_up_world(extrinsics: np.ndarray) -> np.ndarray:
    return -extrinsics[:, 1, :3]                    # R^T @ (0,-1,0) = -row1(R)


def camera_forward_world(extrinsics: np.ndarray) -> np.ndarray:
    return extrinsics[:, 2, :3]                     # R^T @ (0,0,1) = row2(R)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise GeometryError("Degenerate vector while building the reconstruction frame.")
    return v / n


# ---------------------------------------------------------------------------
# Floor plane
# ---------------------------------------------------------------------------

@dataclass
class FloorFit:
    normal: np.ndarray        # unit, pointing UP (toward the cameras)
    point: np.ndarray         # a point on the floor
    camera_height: float      # in reconstruction units
    inlier_ratio: float
    method: str


def _heights(points: np.ndarray, normal: np.ndarray, origin: np.ndarray) -> np.ndarray:
    return (points - origin) @ normal


def fit_floor_plane(points: np.ndarray, centers: np.ndarray, up_hint: np.ndarray,
                    rng: np.random.Generator, iterations: int = 400) -> FloorFit:
    """
    Find the floor: a near-horizontal plane below the cameras.

    1. RANSAC finds the dominant near-horizontal plane normal.
    2. Heights along that normal are histogrammed; the LOWEST substantial peak
       below the cameras is the floor (beds/tables form higher peaks).
    3. The plane is refined by SVD on that peak's inliers.
    """
    if len(points) < 200:
        raise GeometryError("Too few confident 3D points to find the floor.")
    up_hint = _unit(up_hint)
    scale = float(np.median(np.linalg.norm(points - np.median(points, axis=0), axis=1)))
    tau = max(1e-4, 0.02 * scale)

    best_normal, best_count = None, -1
    n_pts = len(points)
    cos_limit = np.cos(np.radians(25))
    for _ in range(iterations):
        idx = rng.choice(n_pts, 3, replace=False)
        p0, p1, p2 = points[idx]
        n = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(n)
        if norm < 1e-12:
            continue
        n = n / norm
        if n @ up_hint < 0:
            n = -n
        if n @ up_hint < cos_limit:
            continue
        count = int(np.sum(np.abs(_heights(points, n, p0)) < tau))
        if count > best_count:
            best_count, best_normal = count, n
    if best_normal is None:
        # No horizontal plane was found; fall back to the camera-derived up vector.
        best_normal, method = up_hint, "camera_up_fallback"
    else:
        method = "ransac_histogram"

    cam_ref = float(np.mean(centers @ best_normal))
    h = points @ best_normal                     # signed distance along the normal (arbitrary origin)
    below = h[h < cam_ref - tau]
    if len(below) < 100:
        raise GeometryError("No surface was found below the cameras; cannot locate the floor.")

    bins = max(10, int(np.ceil((below.max() - below.min()) / (2 * tau))))
    counts, edges = np.histogram(below, bins=min(bins, 400))
    threshold = 0.35 * counts.max()
    peak_bins = [i for i, c in enumerate(counts) if c >= threshold and (i == 0 or c >= counts[i - 1]) and (i == len(counts) - 1 or c >= counts[i + 1])]
    floor_bin = min(peak_bins) if peak_bins else int(np.argmax(counts))
    floor_level = 0.5 * (edges[floor_bin] + edges[floor_bin + 1])

    inliers = points[np.abs(h - floor_level) < 2.5 * tau]
    if len(inliers) < 100:
        inliers = points[np.abs(h - floor_level) < 5 * tau]
    if len(inliers) < 50:
        raise GeometryError("Floor plane has too little supporting evidence.")
    centroid = inliers.mean(axis=0)
    _, _, vt = np.linalg.svd(inliers - centroid, full_matrices=False)
    normal = vt[2]
    if normal @ best_normal < 0:
        normal = -normal
    if normal @ best_normal < cos_limit:
        normal = best_normal                      # SVD wandered off; keep the RANSAC normal

    cam_height = float(np.mean((centers - centroid) @ normal))
    if cam_height <= 0:
        raise GeometryError("Cameras are not above the detected floor; reconstruction is unreliable.")
    return FloorFit(normal=normal, point=centroid, camera_height=cam_height,
                    inlier_ratio=len(inliers) / len(points), method=method)


# ---------------------------------------------------------------------------
# Footprint rectangle
# ---------------------------------------------------------------------------

def _ground_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0, 0]) if abs(normal[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = _unit(np.cross(normal, helper))
    e2 = np.cross(normal, e1)
    return e1, e2


def _min_area_rectangle(xy: np.ndarray, trim: float = 1.0) -> tuple[float, float, float, float]:
    """Angle (rad) minimising the trimmed bounding-box area; returns (angle, a_min, a_max, b_min, b_max) packed."""
    best = None
    for deg in np.arange(0, 90, 1.0):
        th = np.radians(deg)
        c, s = np.cos(th), np.sin(th)
        a = xy[:, 0] * c + xy[:, 1] * s
        b = -xy[:, 0] * s + xy[:, 1] * c
        a0, a1 = np.percentile(a, [trim, 100 - trim])
        b0, b1 = np.percentile(b, [trim, 100 - trim])
        area = (a1 - a0) * (b1 - b0)
        if best is None or area < best[0]:
            best = (area, th, a0, a1, b0, b1)
    return best[1:]


def _perimeter_coverage(xy_rot: np.ndarray, a0, a1, b0, b1, bins: int = 36) -> float:
    cx, cy = (a0 + a1) / 2, (b0 + b1) / 2
    ang = np.arctan2(xy_rot[:, 1] - cy, xy_rot[:, 0] - cx)
    # only points near the boundary count as "wall evidence"
    margin_a, margin_b = 0.12 * (a1 - a0), 0.12 * (b1 - b0)
    near = (
        (xy_rot[:, 0] < a0 + margin_a) | (xy_rot[:, 0] > a1 - margin_a)
        | (xy_rot[:, 1] < b0 + margin_b) | (xy_rot[:, 1] > b1 - margin_b)
    )
    hist, _ = np.histogram(ang[near], bins=bins, range=(-np.pi, np.pi))
    return float(np.mean(hist >= max(15, 0.0015 * near.sum())))


def _yaw_coverage_degrees(forwards_ground: np.ndarray) -> float:
    angles = np.sort(np.degrees(np.arctan2(forwards_ground[:, 1], forwards_ground[:, 0])) % 360)
    if len(angles) < 2:
        return 0.0
    gaps = np.diff(np.concatenate([angles, [angles[0] + 360]]))
    return float(360 - gaps.max())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@dataclass
class Reconstruction:
    """Everything needed to place detections in the plan frame."""
    origin_ground: np.ndarray      # plan origin in ground coords (a_r, a_u) at room centre
    r_axis: np.ndarray             # 3D unit vector, plan +x
    u_axis: np.ndarray             # 3D unit vector, plan +y
    normal: np.ndarray
    floor_point: np.ndarray
    scale: float                   # metres per reconstruction unit
    centre_r: float
    centre_u: float
    width: float
    length: float
    camera_height: float = 1.0     # reconstruction units

    def to_plan(self, pts: np.ndarray) -> np.ndarray:
        rel = pts - self.floor_point
        x = (rel @ self.r_axis - self.centre_r) * self.scale + self.width / 2
        y = (rel @ self.u_axis - self.centre_u) * self.scale + self.length / 2
        return np.stack([x, y], axis=-1)


def reconstruct_room(
    points: np.ndarray,             # (S,H,W,3)
    conf: np.ndarray,               # (S,H,W)
    valid: np.ndarray,              # (S,H,W) bool - True where the pixel is real image content
    extrinsics: np.ndarray,         # (S,3,4)
    user_width: float | None = None,
    user_length: float | None = None,
    seed: int = 7,
    max_points: int = 60000,
) -> tuple[dict[str, Any], Reconstruction]:
    S = points.shape[0]
    rng = np.random.default_rng(seed)
    warnings: list[str] = []

    centers = camera_centers(extrinsics)
    ups = camera_up_world(extrinsics)
    fwd = camera_forward_world(extrinsics)

    # 1. confident, valid, finite points
    finite = np.isfinite(points).all(axis=-1)
    mask = valid & finite
    if mask.sum() < MIN_USABLE_POINTS:
        raise GeometryError("Too few valid 3D points were produced from the photos.")
    thr = np.percentile(conf[mask], 40)
    mask &= conf >= thr
    pts = points[mask]
    if len(pts) > max_points:
        pts = pts[rng.choice(len(pts), max_points, replace=False)]

    # 2. floor + camera height
    floor = fit_floor_plane(pts, centers, ups.mean(axis=0), rng)
    n = floor.normal

    # 3. footprint
    e1, e2 = _ground_basis(n)
    rel = pts - floor.point
    h = rel @ n
    wall = pts[(h > 0.15 * floor.camera_height) & (h < 2.2 * floor.camera_height)]
    if len(wall) < MIN_USABLE_POINTS // 2:
        raise GeometryError("Too few points above the floor to estimate the room boundary.")
    rel_w = wall - floor.point
    xy = np.stack([rel_w @ e1, rel_w @ e2], axis=1)
    theta, a0, a1, b0, b1 = _min_area_rectangle(xy)
    c, s = np.cos(theta), np.sin(theta)
    ax_a = e1 * c + e2 * s          # 3D axis of rect axis a
    ax_b = -e1 * s + e2 * c         # 3D axis of rect axis b
    xy_rot = np.stack([xy[:, 0] * c + xy[:, 1] * s, -xy[:, 0] * s + xy[:, 1] * c], axis=1)
    coverage = _perimeter_coverage(xy_rot, a0, a1, b0, b1)

    # 4. plan axes: top edge = wall faced by the reference camera (photo 1)
    f0 = fwd[0] - (fwd[0] @ n) * n
    if np.linalg.norm(f0) < 1e-6:
        raise GeometryError("The reference photo points straight up/down; cannot define the plan's top edge.")
    f0 = _unit(f0)
    axes = [ax_a, -ax_a, ax_b, -ax_b]
    u = max(axes, key=lambda v: float(v @ f0))
    r = _unit(np.cross(u, n))                       # right = forward x up (right-handed)
    ext_u = (b1 - b0) if abs(u @ ax_b) > 0.5 else (a1 - a0)
    ext_r = (a1 - a0) if abs(u @ ax_b) > 0.5 else (b1 - b0)
    cen_a, cen_b = (a0 + a1) / 2, (b0 + b1) / 2
    centre_point = floor.point + e1 * (cen_a * c - cen_b * s) + e2 * (cen_a * s + cen_b * c)
    # centre expressed along r/u from the floor point
    centre_r = float((centre_point - floor.point) @ r)
    centre_u = float((centre_point - floor.point) @ u)

    # 5. scale
    dims_source = "estimated"
    dims_assignment = None
    if user_width and user_length:
        direct = abs(np.log((ext_r / ext_u) / (user_width / user_length)))
        swapped = abs(np.log((ext_r / ext_u) / (user_length / user_width)))
        if swapped < direct:
            width_m, length_m, dims_assignment = user_length, user_width, "swapped"
        else:
            width_m, length_m, dims_assignment = user_width, user_length, "as_entered"
        scale = float(np.sqrt(width_m * length_m / (ext_r * ext_u)))
        mism = max(abs(ext_r * scale - width_m) / width_m, abs(ext_u * scale - length_m) / length_m)
        if mism > 0.2:
            warnings.append(
                f"The photographed footprint's proportions differ from your entered dimensions by about {mism:.0%}. "
                "The photos probably do not cover the whole room, or a dimension was mis-entered. "
                "Your measurements were used for the room outline."
            )
        dims_source = "user_provided"
    else:
        scale = ASSUMED_CAMERA_HEIGHT_M / floor.camera_height
        width_m, length_m = ext_r * scale, ext_u * scale
        warnings.append(
            f"No room dimensions were provided, so the scale assumes the phone was held about "
            f"{ASSUMED_CAMERA_HEIGHT_M:.1f} m above the floor. Treat dimensions as rough estimates "
            "(typically off by 20% or more) and enter measured values if you have them."
        )

    width_m, length_m = float(width_m), float(length_m)

    # 6. quality
    yaw = _yaw_coverage_degrees(np.stack([fwd[:, :] @ e1, fwd[:, :] @ e2], axis=1))
    if S < 3:
        warnings.append("Fewer than 3 photos were used; wall coverage is likely incomplete.")
    if coverage < 0.6:
        warnings.append(f"Only about {coverage:.0%} of the room boundary had supporting 3D points, so some walls may be missing or under-sized.")
    if yaw < 250 and S >= 3:
        warnings.append(f"The photos span only about {yaw:.0f}° of viewing directions; capture all four walls and the corners for a fuller reconstruction.")
    if floor.method != "ransac_histogram":
        warnings.append("A horizontal floor plane could not be fitted directly; the camera's up direction was used instead.")

    confidence = "medium" if (coverage >= 0.6 and yaw >= 250 and dims_source == "user_provided" and floor.inlier_ratio > 0.08) else "low"

    result = {
        "room": {
            "width": round(width_m, 3),
            "length": round(length_m, 3),
            "dimensions_source": dims_source,
            "dimensions_assignment": dims_assignment,
            "scale_metres_per_unit": scale,
        },
        "metrics": {
            "photos_used": int(S),
            "points_used": int(len(pts)),
            "floor_inlier_ratio": round(floor.inlier_ratio, 4),
            "floor_method": floor.method,
            "camera_height_units": round(floor.camera_height, 4),
            "perimeter_coverage": round(coverage, 3),
            "yaw_coverage_degrees": round(yaw, 1),
        },
        "confidence": confidence,
        "warnings": warnings,
        "plan_top_edge_is": "the wall faced by the reference photo (photo 1)",
    }
    recon = Reconstruction(
        origin_ground=np.zeros(2), r_axis=r, u_axis=u, normal=n, floor_point=floor.point,
        scale=scale, centre_r=centre_r, centre_u=centre_u, width=width_m, length=length_m,
        camera_height=floor.camera_height,
    )
    return result, recon


# ---------------------------------------------------------------------------
# Detection -> plan placement
# ---------------------------------------------------------------------------

def localize_detection(
    recon: Reconstruction,
    points_img: np.ndarray,       # (H,W,3) for ONE image
    conf_img: np.ndarray,         # (H,W)
    valid_img: np.ndarray,        # (H,W) bool
    bbox_px: tuple[float, float, float, float],   # x1,y1,x2,y2 in this image's tensor pixels
    item: str,
    camera_center: np.ndarray,
    min_points: int = 20,
) -> dict | None:
    """Estimate one detection's plan footprint from the 3D points under its box."""
    H, W = points_img.shape[:2]
    x1, y1, x2, y2 = bbox_px
    x1, x2 = int(max(0, np.floor(x1))), int(min(W, np.ceil(x2)))
    y1, y2 = int(max(0, np.floor(y1))), int(min(H, np.ceil(y2)))
    if x2 - x1 < 3 or y2 - y1 < 3:
        return None
    # The lower part of the box is closest to where the object meets the floor.
    y_low = y1 + int(0.55 * (y2 - y1))
    p = points_img[y_low:y2, x1:x2].reshape(-1, 3)
    c = conf_img[y_low:y2, x1:x2].reshape(-1)
    v = valid_img[y_low:y2, x1:x2].reshape(-1) & np.isfinite(p).all(axis=1)
    if v.sum() < min_points:
        return None
    p, c = p[v], c[v]
    p = p[c >= np.median(c)]

    # A detector box also contains background (walls behind) and floor. Keep only
    # points above the floor, then the nearest-depth cluster = the object itself.
    p = p[(p - recon.floor_point) @ recon.normal > 0.07 * recon.camera_height]
    if len(p) < min_points:
        return None
    dist = np.linalg.norm(p - camera_center, axis=1)
    p = p[dist <= 1.2 * np.percentile(dist, 30)]
    if len(p) < min_points // 2:
        return None
    plan = recon.to_plan(p)

    # Estimate the footprint centre along the viewing direction. The camera sees the NEAR surface:
    # centre = visible near edge + half the object's depth (typical depth, or the visible extent if larger).
    dw, dl = default_size(item)
    cam_plan = recon.to_plan(camera_center[None, :])[0]
    rel = plan - cam_plan
    med = np.median(rel, axis=0)
    norm = np.linalg.norm(med)
    if norm < 1e-6:
        cx, cy = np.median(plan[:, 0]), np.median(plan[:, 1])
    else:
        d = med / norm
        perp = np.array([-d[1], d[0]])
        along, lateral = rel @ d, rel @ perp
        near, far = np.percentile(along, [5, 95])
        depth = max(0.5 * (dw + dl), far - near)
        centre_along = near + depth / 2
        cx, cy = cam_plan + d * centre_along + perp * np.median(lateral)
    return {"x": float(cx), "y": float(cy), "n_points": int(len(p))}


def place_footprint(item: str, cx: float, cy: float, room_w: float, room_l: float,
                    dims: tuple[float, float] | None = None) -> dict:
    """Turn a centre estimate into an in-room axis-aligned footprint (long side parallel to the nearest wall)."""
    w, l = dims or default_size(item)
    if max(w, l) / min(w, l) > 1.3:
        dist_side = min(cx, room_w - cx)
        dist_vert = min(cy, room_l - cy)
        long_is_x = dist_vert < dist_side       # nearer top/bottom wall -> long side runs horizontally
        w, l = (max(w, l), min(w, l)) if long_is_x else (min(w, l), max(w, l))
    w, l = min(w, room_w), min(l, room_l)
    x = float(np.clip(cx - w / 2, 0, room_w - w))
    y = float(np.clip(cy - l / 2, 0, room_l - l))
    return {"x": round(x, 3), "y": round(y, 3), "width": round(w, 3), "length": round(l, 3)}


def merge_candidates(cands: list[dict], radius: float = 0.7) -> list[dict]:
    """Merge detections of the same item type seen in several photos (greedy, by distance)."""
    merged: list[dict] = []
    for cand in sorted(cands, key=lambda c: -c["n_points"]):
        for m in merged:
            if m["item"] == cand["item"] and np.hypot(m["x"] - cand["x"], m["y"] - cand["y"]) < radius:
                tot = m["n_points"] + cand["n_points"]
                m["x"] = (m["x"] * m["n_points"] + cand["x"] * cand["n_points"]) / tot
                m["y"] = (m["y"] * m["n_points"] + cand["y"] * cand["n_points"]) / tot
                m["n_points"] = tot
                m["seen_in"] = sorted(set(m["seen_in"]) | set(cand["seen_in"]))
                break
        else:
            merged.append({**cand, "seen_in": list(cand["seen_in"])})
    return merged

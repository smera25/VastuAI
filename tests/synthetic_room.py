"""
Synthetic ground-truth room for testing app.geometry WITHOUT any model.

Builds a box room (+ one cuboid 'bed'), ray-casts depth from several cameras,
and expresses everything the way VGGT does: in the FIRST camera's frame, at an
arbitrary (non-metric) scale. NOT a real VGGT output - this validates the math only.
"""
import numpy as np

ROOM = (5.0, 4.0, 2.6)                     # east-west, north-south, height (metres)
BED = ((0.6, 1.2, 0.0), (2.2, 3.2, 0.5))   # (min, max) corners in true coords


def _cam_R(yaw_deg):
    """Camera-from-world rotation for a camera looking horizontally at compass yaw (0=north,90=east)."""
    a = np.radians(yaw_deg)
    fwd = np.array([np.sin(a), np.cos(a), 0.0])
    up = np.array([0, 0, 1.0])
    right = np.cross(fwd, up)
    down = -up
    return np.stack([right, down, fwd])


def _ray_box_exit(c, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(d > 0, (hi - c) / d, np.where(d < 0, (lo - c) / d, np.inf))
    return t.min(axis=-1)


def _ray_box_hit(c, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        t1, t2 = (lo - c) / d, (hi - c) / d
    tn = np.minimum(t1, t2)
    tf = np.maximum(t1, t2)
    tn = np.nanmax(np.where(np.isfinite(tn), tn, -np.inf), axis=-1)
    tf = np.nanmin(np.where(np.isfinite(tf), tf, np.inf), axis=-1)
    hit = (tf >= np.maximum(tn, 0)) & (tn > 0)
    return np.where(hit, tn, np.inf)


def build(yaws, cam_xy=(2.5, 2.0), cam_h=1.4, size=64, fov_deg=70, scale=0.4, noise=0.004, seed=3, with_bed=True):
    rng = np.random.default_rng(seed)
    f = (size / 2) / np.tan(np.radians(fov_deg / 2))
    u, v = np.meshgrid(np.arange(size) + 0.5, np.arange(size) + 0.5)
    rays_cam = np.stack([(u - size / 2) / f, (v - size / 2) / f, np.ones_like(u)], axis=-1)
    lo, hi = np.zeros(3), np.array(ROOM)
    bed_lo, bed_hi = np.array(BED[0]), np.array(BED[1])

    C = np.array([cam_xy[0], cam_xy[1], cam_h])
    Rs = [_cam_R(y) for y in yaws]
    R0 = Rs[0]

    pts_all, bed_masks, ext_all = [], [], []
    for R in Rs:
        d = rays_cam @ R                           # world direction = R^T applied to cam-frame ray
        d = d / np.linalg.norm(d, axis=-1, keepdims=True)
        t_wall = _ray_box_exit(C, d, lo, hi)
        t_bed = _ray_box_hit(C, d, bed_lo, bed_hi) if with_bed else np.full(t_wall.shape, np.inf)
        is_bed = t_bed < t_wall
        t = np.where(is_bed, t_bed, t_wall)
        P_true = C + t[..., None] * d
        P_true = P_true + rng.normal(0, noise, P_true.shape)
        # to VGGT frame: cam0 = identity, arbitrary scale
        P = scale * ((P_true - C) @ R0.T)
        pts_all.append(P)
        bed_masks.append(is_bed)
        Ri = R @ R0.T
        ti = scale * (R @ (C - C)).astype(float)    # all cameras share a position here
        ext_all.append(np.concatenate([Ri, ti[:, None]], axis=1))

    points = np.stack(pts_all)
    conf = np.ones(points.shape[:3]) * 5.0
    valid = np.ones(points.shape[:3], dtype=bool)
    return points, conf, valid, np.stack(ext_all), np.stack(bed_masks)


def build_multi_position(cams, size=64, fov_deg=70, scale=0.4, noise=0.004, seed=3, with_bed=True):
    """cams: list of (x, y, yaw_deg, height). Cameras at different positions; frame = first camera."""
    rng = np.random.default_rng(seed)
    f = (size / 2) / np.tan(np.radians(fov_deg / 2))
    u, v = np.meshgrid(np.arange(size) + 0.5, np.arange(size) + 0.5)
    rays_cam = np.stack([(u - size / 2) / f, (v - size / 2) / f, np.ones_like(u)], axis=-1)
    lo, hi = np.zeros(3), np.array(ROOM)
    bed_lo, bed_hi = np.array(BED[0]), np.array(BED[1])
    C0 = np.array([cams[0][0], cams[0][1], cams[0][3]])
    R0 = _cam_R(cams[0][2])
    pts_all, ext_all, masks = [], [], []
    for (x, y, yaw, h) in cams:
        C = np.array([x, y, h]); R = _cam_R(yaw)
        d = rays_cam @ R
        d = d / np.linalg.norm(d, axis=-1, keepdims=True)
        t_wall = _ray_box_exit(C, d, lo, hi)
        t_bed = _ray_box_hit(C, d, bed_lo, bed_hi) if with_bed else np.full(t_wall.shape, np.inf)
        is_bed = t_bed < t_wall
        t = np.where(is_bed, t_bed, t_wall)
        P_true = C + t[..., None] * d + rng.normal(0, noise, t.shape + (3,))
        pts_all.append(scale * ((P_true - C0) @ R0.T))
        Ri = R @ R0.T
        ti = scale * (R @ (C0 - C))
        ext_all.append(np.concatenate([Ri, ti[:, None]], axis=1))
        masks.append(is_bed)
    points = np.stack(pts_all)
    return points, np.full(points.shape[:3], 5.0), np.ones(points.shape[:3], bool), np.stack(ext_all), np.stack(masks)

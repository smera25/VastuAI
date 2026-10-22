"""File-backed persistence for redesign specs and generated visualisations."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings

_ID = re.compile(r"^[a-f0-9]{8,32}$")


def _check(id_: str) -> str:
    if not _ID.match(id_):
        raise ValueError("Invalid id.")
    return id_


def job_dir(job_id: str) -> Path:
    return settings.data_dir / "jobs" / _check(job_id)


def redesign_path(rid: str) -> Path:
    return settings.data_dir / "redesigns" / f"{_check(rid)}.json"


def visualization_path(rid: str) -> Path:
    return settings.data_dir / "visualizations" / f"{_check(rid)}.png"


def save_redesign(rid: str, spec: dict) -> None:
    settings.ensure_dirs()
    redesign_path(rid).write_text(json.dumps(spec), encoding="utf-8")


def load_redesign(rid: str) -> dict | None:
    try:
        p = redesign_path(rid)
    except ValueError:
        return None
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

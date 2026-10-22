"""
Tiny in-memory job runner for slow work (reconstruction, image generation).

One worker thread: the heavy steps are CPU/GPU bound and the expected
deployment is a single machine. Job state lives in memory (documented): a server
restart forgets in-flight jobs, and clients see a 404 and can resubmit.

Progress is REAL: a stage only becomes ``running`` when its code starts and
``done`` / ``skipped`` / ``failed`` when it ends, with the reason attached.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import settings

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")
_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()


@dataclass
class Stage:
    key: str
    label: str
    status: str = "pending"        # pending | running | done | skipped | failed
    detail: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class Job:
    id: str
    kind: str
    stages: list[Stage]
    status: str = "queued"         # queued | running | succeeded | failed
    result: Any = None
    error: dict | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def public(self) -> dict:
        return {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "stages": [s.__dict__.copy() for s in self.stages],
            "result": self.result if self.status == "succeeded" else None,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobContext:
    def __init__(self, job: Job):
        self._job = job

    def _stage(self, key: str) -> Stage:
        for s in self._job.stages:
            if s.key == key:
                return s
        raise KeyError(key)

    def start(self, key: str, detail: str | None = None) -> None:
        with _lock:
            s = self._stage(key)
            s.status, s.detail, s.started_at = "running", detail, time.time()

    def done(self, key: str, detail: str | None = None) -> None:
        with _lock:
            s = self._stage(key)
            s.status, s.finished_at = "done", time.time()
            if detail:
                s.detail = detail

    def skip(self, key: str, reason: str) -> None:
        with _lock:
            s = self._stage(key)
            s.status, s.detail, s.finished_at = "skipped", reason, time.time()

    def fail(self, key: str, reason: str) -> None:
        with _lock:
            s = self._stage(key)
            s.status, s.detail, s.finished_at = "failed", reason, time.time()


def _purge_old() -> None:
    cutoff = time.time() - settings.job_ttl_seconds
    with _lock:
        for jid in [j for j, job in _jobs.items() if job.finished_at and job.finished_at < cutoff]:
            _jobs.pop(jid, None)


def submit(kind: str, stages: list[tuple[str, str]], fn: Callable[[JobContext], Any], job_id: str | None = None) -> Job:
    _purge_old()
    job = Job(id=job_id or uuid.uuid4().hex[:16], kind=kind, stages=[Stage(k, label) for k, label in stages])
    with _lock:
        _jobs[job.id] = job

    def run():
        ctx = JobContext(job)
        with _lock:
            job.status = "running"
        try:
            result = fn(ctx)
            with _lock:
                job.result, job.status, job.finished_at = result, "succeeded", time.time()
        except Exception as exc:       # surfaced to the client, never swallowed
            log.exception("Job %s (%s) failed", job.id, kind)
            code = getattr(exc, "code", "job_failed")
            with _lock:
                for s in job.stages:
                    if s.status == "running":
                        s.status, s.detail, s.finished_at = "failed", str(exc), time.time()
                job.error = {"code": code, "message": str(exc), **getattr(exc, "extra", {})}
                job.status, job.finished_at = "failed", time.time()

    _executor.submit(run)
    return job


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


class JobError(Exception):
    """Raise inside a job fn to fail it with a machine-readable code."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra

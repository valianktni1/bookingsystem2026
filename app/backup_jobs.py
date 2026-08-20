"""Short HTTP requests around the comparatively slow complete-backup build.

The original one-click endpoint kept the browser connection silent while every
PDF and uploaded file was added.  Reverse proxies and mobile browsers can time
out that request even though the application remains healthy.  These jobs let
the browser poll lightweight status responses and only begin the file transfer
after a stable ZIP exists on disk.
"""

from __future__ import annotations

import logging
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .backup import BackupBusyError, create_complete_backup
from .database import SessionLocal
from .services import audit


LOGGER = logging.getLogger(__name__)
JOB_RETENTION = timedelta(hours=24)
JOB_STALE_AFTER = timedelta(hours=2)
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _remove_file(path: Path | None) -> None:
    if path:
        path.unlink(missing_ok=True)


def _cleanup_locked(now: datetime) -> None:
    expired: list[str] = []
    for job_id, job in _JOBS.items():
        status = job["status"]
        if status in {"queued", "preparing"} and now - job["updated_at"] > JOB_STALE_AFTER:
            job.update({
                "status": "failed",
                "message": "The preparation stopped unexpectedly. Please start a new backup.",
                "updated_at": now,
            })
            status = "failed"
        if status in {"ready", "failed"} and now - job["updated_at"] > JOB_RETENTION:
            expired.append(job_id)
    for job_id in expired:
        _remove_file(_JOBS[job_id].get("path"))
        del _JOBS[job_id]


def _cleanup_old_orphans(now: datetime) -> None:
    cutoff = now - JOB_RETENTION
    temp_root = Path(tempfile.gettempdir())
    for path in temp_root.glob("bookingsystem2026-backup-*.zip"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _public(job: dict[str, Any]) -> dict[str, Any]:
    ready = job["status"] == "ready"
    result = {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "filename": job.get("filename") if ready else None,
        "size_bytes": job.get("size_bytes") if ready else None,
        "download_url": (
            f"/api/backups/complete/{job['job_id']}/download" if ready else None
        ),
    }
    if ready:
        result["expires_at"] = (job["updated_at"] + JOB_RETENTION).isoformat()
    return result


def start_complete_backup_job(admin_id: str) -> tuple[dict[str, Any], bool]:
    """Create a job or return the already-running job for this administrator."""
    now = _now()
    _cleanup_old_orphans(now)
    with _JOBS_LOCK:
        _cleanup_locked(now)
        for job in _JOBS.values():
            if job["admin_id"] == admin_id and job["status"] in {"queued", "preparing"}:
                return _public(job), False
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "admin_id": admin_id,
            "status": "queued",
            "progress": 0,
            "message": "Backup preparation is queued",
            "created_at": now,
            "updated_at": now,
            "path": None,
        }
        _JOBS[job_id] = job
        return _public(job), True


def _update_job(job_id: str, **changes: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(changes)
        job["updated_at"] = _now()


def prepare_complete_backup_job(job_id: str) -> None:
    """Run after the start response has returned to the browser."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        admin_id = job["admin_id"]
    _update_job(job_id, status="preparing", progress=1,
                message="Starting the complete private backup")

    def progress(percent: int, message: str) -> None:
        _update_job(job_id, status="preparing", progress=percent, message=message)

    path: Path | None = None
    try:
        with SessionLocal() as db:
            path, filename, manifest = create_complete_backup(db, progress=progress)
            try:
                audit(db, "prepare_complete_backup", "admin", admin_id, {
                    "filename": filename,
                    "database_row_count": manifest["database_row_count"],
                    "uploaded_file_count": manifest["uploaded_file_count"],
                    "generated_pdf_count": manifest["generated_pdf_count"],
                })
                db.commit()
            except Exception:
                db.rollback()
                LOGGER.exception("Complete backup was created but its audit entry could not be saved")
        _update_job(
            job_id,
            status="ready",
            progress=100,
            message="Your complete backup is ready",
            path=path,
            filename=filename,
            size_bytes=path.stat().st_size,
        )
    except BackupBusyError as exc:
        _remove_file(path)
        _update_job(job_id, status="failed", message=str(exc))
    except Exception:
        _remove_file(path)
        LOGGER.exception("Complete backup preparation failed")
        _update_job(
            job_id,
            status="failed",
            message="The backup could not be prepared. Please try again.",
        )


def get_complete_backup_job(job_id: str, admin_id: str) -> dict[str, Any] | None:
    now = _now()
    with _JOBS_LOCK:
        _cleanup_locked(now)
        job = _JOBS.get(job_id)
        if not job or job["admin_id"] != admin_id:
            return None
        if job["status"] == "ready" and not job.get("path", Path()).is_file():
            job.update({
                "status": "failed",
                "message": "The prepared file is no longer available. Please start a new backup.",
                "updated_at": now,
            })
        return _public(job)


def get_complete_backup_file(job_id: str, admin_id: str) -> tuple[Path, str] | None:
    now = _now()
    with _JOBS_LOCK:
        _cleanup_locked(now)
        job = _JOBS.get(job_id)
        if (not job or job["admin_id"] != admin_id or job["status"] != "ready"
                or not job.get("path") or not job["path"].is_file()):
            return None
        return job["path"], job["filename"]

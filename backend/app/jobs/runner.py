"""Scan job dispatch.

Two interchangeable backends are supported:
  * `in-process` (default for local development) runs the scan on the API event
    loop. This is a single-process convenience: a restart drops queued work, and
    scans compete with request handling for CPU.
  * `celery` publishes to the Redis broker and lets dedicated workers execute
    the same `app.discovery.engine.run_scan` entry point.

Both persist progress to the database, so the scan history survives a restart
even when the worker does not.
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.discovery.engine import run_scan, utcnow
from app.models import Scan, ScanEvent, ScanStatus

logger = get_logger("asm.jobs")

_running: dict[str, asyncio.Task] = {}


def enqueue_scan(scan_id: str) -> str:
    """Dispatch a queued scan and return the job identifier."""
    if settings.job_backend == "celery":
        return _enqueue_celery(scan_id)
    return _enqueue_in_process(scan_id)


def _enqueue_in_process(scan_id: str) -> str:
    job_id = f"local-{uuid.uuid4().hex[:12]}"
    task = asyncio.create_task(_run(scan_id, job_id), name=f"scan:{scan_id}")
    _running[job_id] = task
    task.add_done_callback(lambda _task: _running.pop(job_id, None))
    return job_id


async def _run(scan_id: str, job_id: str) -> None:
    try:
        await run_scan(scan_id)
    except Exception as exc:  # a crashed worker must not leave a scan "running" forever
        logger.exception("scan job crashed", extra={"scan_id": scan_id, "job_id": job_id})
        await _mark_failed(scan_id, f"The scan worker stopped unexpectedly: {type(exc).__name__}")


async def _mark_failed(scan_id: str, message: str) -> None:
    try:
        async with session_scope() as session:
            scan = await session.get(Scan, scan_id)
            if scan is None:
                return
            scan.status = ScanStatus.FAILED.value
            scan.error_message = message[:1000]
            scan.finished_at = scan.finished_at or utcnow()
            session.add(
                ScanEvent(
                    company_id=scan.company_id,
                    scan_id=scan.id,
                    level="error",
                    stage="worker",
                    message=message[:2000],
                    occurred_at=utcnow(),
                )
            )
            await session.commit()
    except Exception:  # pragma: no cover - best-effort failure recording
        logger.exception("could not record crashed scan", extra={"scan_id": scan_id})


def _enqueue_celery(scan_id: str) -> str:
    try:
        from app.jobs.tasks import run_scan_task
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "ASM_JOB_BACKEND=celery but the Celery worker dependency is not installed. "
            "Install requirements-prod.txt or switch back to the in-process backend."
        ) from exc
    return run_scan_task.delay(scan_id).id

"""Celery entry point used when `ASM_JOB_BACKEND=celery`.

The worker owns one event loop for its lifetime so the async SQLAlchemy engine's
connection pool stays bound to a single loop.
"""

from __future__ import annotations

import asyncio

from celery import Celery

from app.core.config import settings
from app.discovery.engine import run_scan

celery_app = Celery("asm", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_time_limit=60 * 60,
    task_soft_time_limit=60 * 55,
    worker_max_tasks_per_child=100,
)

_loop: asyncio.AbstractEventLoop | None = None


def _worker_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


@celery_app.task(name="asm.run_scan", bind=True, max_retries=0)
def run_scan_task(self, scan_id: str) -> dict:
    _worker_loop().run_until_complete(run_scan(scan_id))
    return {"scan_id": scan_id, "status": "finished"}

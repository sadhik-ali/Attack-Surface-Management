"""Background job dispatch for discovery scans."""

from app.jobs.runner import enqueue_scan

__all__ = ["enqueue_scan"]

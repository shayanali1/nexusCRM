import asyncio
import concurrent.futures
from typing import Any, Coroutine
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "nexuscrm_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.ai_jobs",
        "app.workers.automation_jobs",
        "app.workers.import_jobs",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    beat_schedule={
        "scan-overdue-tasks-hourly": {
            "task": "app.workers.automation_jobs.scan_overdue_tasks_periodic",
            "schedule": 3600.0,  # Run every hour (3600 seconds)
        },
    },
)


def run_async_in_worker(coro: Coroutine[Any, Any, Any]) -> Any:
    """Helper to run async coroutines safely inside Celery worker threads."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(coro)).result()
    else:
        return asyncio.run(coro)

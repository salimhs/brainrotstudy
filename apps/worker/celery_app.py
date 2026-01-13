"""Celery worker configuration and tasks for BrainRotStudy pipeline."""

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker.tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,  # Process one task at a time
    task_acks_late=True,  # Acknowledge tasks after completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker crashes
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to prevent memory leaks
    broker_connection_retry_on_startup=True,
    result_expires=3600,  # Results expire after 1 hour
)

if __name__ == "__main__":
    app.start()

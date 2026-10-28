"""Celery application configuration for API background tasks."""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv
from kombu import Queue

load_dotenv(Path(__file__).resolve().parent / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "trackflow",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.telemetry_report", "tasks.rfp_intake"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="celery",
    task_queues=(Queue("celery"), Queue("dead_letter")),
    task_routes={
        "tasks.telemetry_report.generate_telemetry_report": {"queue": "celery"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
)

from celery import Celery

from .config import settings

celery = Celery("api_platform", broker=settings.REDIS_URL, backend=settings.REDIS_URL, include=["app.tasks"])
celery.conf.update(
    task_always_eager=settings.CELERY_ALWAYS_EAGER,
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "aggregate-usage": {
            "task": "app.tasks.aggregate_usage",
            "schedule": float(settings.USAGE_FLUSH_SECONDS),
        },
    },
)

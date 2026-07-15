from celery import Celery

from backend.config import settings

celery_app = Celery(
    "message_monitor",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.beat_schedule = {
    "poll-gmail": {"task": "backend.tasks.poll_gmail", "schedule": 60.0},
    "poll-twitter": {"task": "backend.tasks.poll_twitter", "schedule": 300.0},
    "send-digest": {"task": "backend.tasks.send_digest", "schedule": settings.digest_interval_minutes * 60.0},
    "generate-daily-report": {"task": "backend.tasks.generate_daily_report", "schedule": {"hour": 8, "minute": 0}},
}

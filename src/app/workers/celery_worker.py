import os
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..services.result_reporter import bulk_report_results
from ..services.result_reporter import report_result_to_testlink
from ..services.testlink_sync import sync_testcases
from ..services.openqa_runner import update_job_status
from ..database import get_db_session
from ..models import TestJob

# Celery конфигурация
celery_app = Celery(__name__)

# Брокер и бэкенд из .env
celery_app.conf.broker_url = os.getenv(
    "CELERY_BROKER",
    "redis://localhost:6379/0"
)
celery_app.conf.result_backend = os.getenv(
    "CELERY_BACKEND",
    "redis://localhost:6379/0"
)

# Настройки
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,  # По 1 задаче за раз
    task_acks_late=True,
    worker_concurrency=2,
    task_track_started=True,
    task_reject_on_worker_lost=True,
)

# SQLAlchemy для задач
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testauto")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@celery_app.task(bind=True, max_retries=3)
def monitor_openqa_jobs(self, job_id: str):
    """Мониторинг OpenQA jobs"""

    db = get_db_session()
    try:
        update_job_status(job_id, db)

        test_job = db.query(TestJob).filter(TestJob.openqa_job_id == job_id).first()
        if test_job and test_job.openqa_status == "done":
            report_result_to_testlink(test_job.testcase_id, db)

    finally:
        db.close()


@celery_app.task(bind=True)
def periodic_testlink_sync(self):
    """Периодическая синхронизация TestLink"""
    db = SessionLocal()
    try:
        result = sync_testcases(db)
        print(f"Synced {result['synced']} test cases")
    finally:
        db.close()


@celery_app.task
def bulk_report_pending_results(self):
    """Массовое обновление результатов"""
    db = SessionLocal()
    try:
        return bulk_report_results(db)
    finally:
        db.close()


# Периодические задачи (beat schedule)
celery_app.conf.beat_schedule = {
    'sync-testlink-every-hour': {
        'task': 'workers.celery_worker.periodic_testlink_sync',
        'schedule': crontab(hour='*/1'),  # Каждый час
    },
    'report-results-daily': {
        'task': 'workers.celery_worker.bulk_report_pending_results',
        'schedule': crontab(hour=2, minute=0),  # 2:00 UTC
    },
}

# Flower мониторинг (опционально)
if __name__ == "__main__":
    celery_app.start()

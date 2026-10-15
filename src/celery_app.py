from celery import Celery
from celery.signals import setup_logging as celery_setup_logging

from src.core.config import settings
from src.core.logger import setup_logging

celery_setup_logging.connect(lambda **_: setup_logging())

celery_app = Celery(
    "employee-onboarding",
    broker=settings.CELERY_BROKER_URL,
    include=["src.provisioning.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

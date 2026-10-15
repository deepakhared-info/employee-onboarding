import logging
import sys

from src.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())

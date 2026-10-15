from fastapi import FastAPI

from .core.config import settings
from .core.logger import setup_logging
from .routes import router


def get_application():
    setup_logging()
    app = FastAPI(debug=settings.DEBUG)
    app.include_router(router, prefix=settings.API_PREFIX)
    return app


app = get_application()

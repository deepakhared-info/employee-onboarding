from fastapi import FastAPI

from .core.config import settings
from .routes import router


def get_application():
    app = FastAPI(debug=settings.DEBUG)
    app.include_router(router)
    return app


app = get_application()

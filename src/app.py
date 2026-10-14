from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.config import settings
from .provisioning.worker import provisioning_worker
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.PROVISIONING_WORKER_ENABLED:
        await provisioning_worker.start()
    yield
    await provisioning_worker.stop()


def get_application():
    app = FastAPI(debug=settings.DEBUG, lifespan=lifespan)
    app.include_router(router, prefix=settings.API_PREFIX)
    return app


app = get_application()

from fastapi import APIRouter
from src.core.config import settings
from .home.api import router as home_router
from .onboarding.api import router as onboarding_router

router = APIRouter(prefix=settings.API_PREFIX)
router.include_router(home_router, prefix='/v1')
router.include_router(onboarding_router, prefix='/v1')
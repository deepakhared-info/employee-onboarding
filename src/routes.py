from fastapi import APIRouter
from src.core.config import settings
from .home.api import router as home_router
from .onboarding.api import router as onboarding_router
from .provisioning.api import router as provisioning_router

router = APIRouter(prefix='/v1')
router.include_router(home_router, tags=["Home"])
router.include_router(onboarding_router, tags=["Onboarding"])
router.include_router(provisioning_router, tags=["Provisioning"])

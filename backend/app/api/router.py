from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.library import admin_router, public_router, student_router
from app.api.routes.setup import router as setup_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(setup_router)
api_router.include_router(public_router)
api_router.include_router(admin_router)
api_router.include_router(student_router)

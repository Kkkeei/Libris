import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app import models  # noqa: F401

settings = get_settings()
logger = logging.getLogger("libris")


def _bootstrap_first_admin() -> None:
    """
    Optional one-time setup from environment.
    Disabled unless both BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are supplied.
    """
    email = settings.bootstrap_admin_email.strip().lower()
    password = settings.bootstrap_admin_password
    if not email or not password:
        return
    if len(settings.auth_secret_key) < 32:
        raise RuntimeError("AUTH_SECRET_KEY deve ter ao menos 32 caracteres para habilitar a autenticação.")
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        existing = db.scalar(select(User.id).where(User.role == "librarian").limit(1))
        if existing:
            return
        user = User(
            email=email,
            full_name=settings.bootstrap_admin_name.strip() or "Bibliotecária",
            password_hash=hash_password(password),
            role="librarian",
            is_active=True,
        )
        db.add(user)
        db.commit()
        logger.warning("First Libris librarian created from environment bootstrap.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Create missing tables only; never remove persistent records during restart.
    Base.metadata.create_all(bind=engine)
    _bootstrap_first_admin()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API do sistema bibliotecário escolar Libris.",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"],
)


@app.middleware("http")
async def request_deadline_and_logging(request, call_next):
    request_id = request.headers.get("X-Request-ID", "")[:100] or secrets.token_hex(12)
    started = __import__("time").monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled API error: id=%s method=%s path=%s", request_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocorreu um erro interno. Tente novamente e informe o código de suporte.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(round((__import__("time").monotonic() - started) * 1000, 2))
    return response


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": f"{settings.api_v1_prefix}/docs"}

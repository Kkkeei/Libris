import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app import models  # noqa: F401

settings = get_settings()
logger = logging.getLogger("libris")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API do sistema bibliotecário escolar Libris.",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"],
)


@app.middleware("http")
async def request_deadline_and_logging(request: Request, call_next: Callable[..., Any]):
    """Apply a bounded request deadline and provide a request id for support/debugging."""
    request_id = request.headers.get("X-Request-ID", "")[:100] or f"req-{time.time_ns()}"
    request.state.request_id = request_id
    started = time.monotonic()
    try:
        response = await asyncio.wait_for(call_next(request), timeout=30)
    except TimeoutError:
        logger.warning("Request timed out: id=%s method=%s path=%s", request_id, request.method, request.url.path)
        return JSONResponse(
            status_code=504,
            content={"detail": "A operação demorou mais que o esperado. Verifique o estado antes de repetir.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    except Exception:
        logger.exception("Unhandled API error: id=%s method=%s path=%s", request_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocorreu um erro interno. Tente novamente e informe o código de suporte.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(round((time.monotonic() - started) * 1000, 2))
    return response


@app.on_event("startup")
def initialize_database() -> None:
    # Persistence stays on disk; tables are never dropped on restart.
    Base.metadata.create_all(bind=engine)


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": f"{settings.api_v1_prefix}/docs"}

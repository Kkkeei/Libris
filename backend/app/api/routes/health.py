from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", summary="Verifica se a API está respondendo")
def application_health() -> dict[str, str]:
    return {"status": "ok", "service": "libris-api"}


@router.get("/health/db", summary="Verifica a conexão com o banco de dados")
def database_health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "service": "database"},
        ) from exc
    return {"status": "ok", "service": "database"}

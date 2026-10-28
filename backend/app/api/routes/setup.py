import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User

router = APIRouter(prefix="/setup", tags=["configuração inicial"])
logger = logging.getLogger("libris.setup")


class BootstrapRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=200)
    setup_key: str = Field(min_length=24, max_length=256)


class BootstrapResponse(BaseModel):
    created: bool
    message: str


@router.post("/admin", response_model=BootstrapResponse, status_code=201)
def bootstrap_admin(payload: BootstrapRequest):
    """
    Create the first librarian once. Requires LIBRIS_SETUP_KEY configured out-of-band.
    It cannot overwrite or reset existing accounts.
    """
    settings = get_settings()
    configured_key = os.getenv("LIBRIS_SETUP_KEY", "")
    if len(configured_key) < 24 or not secrets.compare_digest(payload.setup_key, configured_key):
        raise HTTPException(status_code=403, detail="Chave de configuração inválida.")
    db: Session = SessionLocal()
    try:
        existing = db.scalar(select(User.id).where(User.role == "librarian").limit(1))
        if existing:
            raise HTTPException(status_code=409, detail="O primeiro acesso já foi configurado.")
        if len(settings.auth_secret_key) < 32:
            raise HTTPException(status_code=503, detail="Defina AUTH_SECRET_KEY antes da configuração inicial.")
        email = payload.email.strip().lower()
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
        user = User(
            email=email,
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role="librarian",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return BootstrapResponse(created=True, message="Acesso inicial da bibliotecária criado.")
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to bootstrap initial librarian")
        raise HTTPException(status_code=500, detail="Não foi possível configurar o primeiro acesso.") from exc
    finally:
        db.close()

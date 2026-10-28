from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, require_librarian, verify_password
from app.db.session import get_db
from app.models import Student, User

router = APIRouter(prefix="/auth", tags=["autenticação"])
settings = get_settings()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    display_name: str


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=200)


class StudentAccountCreate(BaseModel):
    student_id: int
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=200)


def _ensure_secret_configured() -> None:
    if len(settings.auth_secret_key) < 32:
        raise HTTPException(
            status_code=503,
            detail="Autenticação não configurada. Defina AUTH_SECRET_KEY com pelo menos 32 caracteres.",
        )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    _ensure_secret_configured()
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        # Same message for unknown users and wrong passwords.
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    return LoginResponse(
        access_token=create_access_token(user),
        expires_in=settings.access_token_minutes * 60,
        role=user.role,
        display_name=user.full_name,
    )


@router.get("/me")
def me(user: Annotated[User, Depends(require_librarian)]):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_librarian(
    payload: AdminUserCreate,
    _admin: Annotated[User, Depends(require_librarian)],
    db: Annotated[Session, Depends(get_db)],
):
    normalized_email = payload.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == normalized_email)):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    user = User(email=normalized_email, password_hash=hash_password(payload.password),
                full_name=payload.full_name.strip(), role="librarian", is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível criar o usuário. Confira os dados e tente novamente.")
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/student-accounts", status_code=status.HTTP_201_CREATED)
def create_student_account(
    payload: StudentAccountCreate,
    _admin: Annotated[User, Depends(require_librarian)],
    db: Annotated[Session, Depends(get_db)],
):
    student = db.get(Student, payload.student_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=404, detail="Aluno não encontrado ou inativo.")
    username = payload.username.strip().lower()
    email = f"{username}@student.libris.invalid"
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Esse nome de acesso já está vinculado.")
    user = User(email=email, password_hash=hash_password(payload.password),
                full_name=student.full_name, role="student", is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível vincular o acesso.") from exc
    # Store linkage separately via student_id claim will not be enough; avoid implying this account
    # is already tied to a student until the dedicated mapping exists.
    return {"id": user.id, "username": username, "role": user.role, "student_id": student.id}

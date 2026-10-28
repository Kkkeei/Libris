from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, require_librarian, verify_password
from app.db.session import get_db
from app.models import Student, StudentAccount, User

router = APIRouter(prefix="/auth", tags=["autenticação"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=320)
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


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    settings = get_settings()
    if len(settings.auth_secret_key) < 32:
        raise HTTPException(status_code=503, detail="Autenticação não configurada. Defina AUTH_SECRET_KEY.")
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(User.email == username))
    if user is None:
        user = db.scalar(select(User).where(User.email == f"{username}@student.libris.invalid"))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
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
    email = str(payload.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    user = User(email=email, password_hash=hash_password(payload.password), full_name=payload.full_name.strip(), role="librarian", is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível criar o usuário. Confira os dados.") from exc
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
    if db.scalar(select(StudentAccount.id).where(StudentAccount.student_id == student.id)):
        raise HTTPException(status_code=409, detail="Este aluno já possui um acesso vinculado.")
    username = payload.username.strip().lower()
    email = f"{username}@student.libris.invalid"
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Esse nome de acesso já está em uso.")
    user = User(email=email, password_hash=hash_password(payload.password), full_name=student.full_name, role="student", is_active=True)
    db.add(user)
    try:
        db.flush()
        db.add(StudentAccount(student_id=student.id, user_id=user.id))
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível vincular o acesso.") from exc
    return {"id": user.id, "username": username, "role": user.role, "student_id": student.id}

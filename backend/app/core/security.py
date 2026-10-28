from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import User

settings = get_settings()
password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hash.verify(password, stored_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    if len(settings.auth_secret_key) < 32:
        raise RuntimeError("AUTH_SECRET_KEY deve ter ao menos 32 caracteres.")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "role": user.role, "exp": expires, "iat": now}
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or len(settings.auth_secret_key) < 32:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Faça login para continuar.")
    try:
        payload = jwt.decode(credentials.credentials, settings.auth_secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Sua sessão expirou. Entre novamente.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo ou sessão inválida.")
    return user


def require_librarian(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "librarian":
        raise HTTPException(status_code=403, detail="Esta operação é exclusiva da bibliotecária.")
    return user


def require_student(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Esta operação é exclusiva dos alunos.")
    return user

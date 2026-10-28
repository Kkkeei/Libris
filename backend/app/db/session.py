from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite:///")
database_path = settings.database_url.removeprefix("sqlite:///") if is_sqlite else ""

if is_sqlite:
    Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False, "timeout": 15} if is_sqlite else {}
engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    connect_args=connect_args,
)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_integrity(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

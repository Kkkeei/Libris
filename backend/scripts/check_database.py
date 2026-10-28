from pathlib import Path
import shutil
import sys

from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import engine


def backup_sqlite_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        print("This script is only for SQLite deployments.", file=sys.stderr)
        return 2
    path = Path(settings.database_url.removeprefix("sqlite:///"))
    print(f"Database: {path}")
    if not path.exists():
        print("Database file does not exist yet.")
        return 0
    inspector = inspect(engine)
    tables = sorted(t for t in inspector.get_table_names() if t != "alembic_version")
    print("Tables:")
    for table in tables:
        print(f"- {table}: {len(inspector.get_columns(table))} columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

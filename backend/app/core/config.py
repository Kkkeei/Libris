import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Libris API"
    app_version: str = "0.2.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = ""
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    sql_echo: bool = False
    auth_secret_key: str = ""
    access_token_minutes: int = 60 * 8
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Bibliotecária"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def default_persistent_sqlite(cls, value: object) -> str:
        if value is None or not str(value).strip():
            configured = os.getenv("LIBRIS_DATA_DIR")
            data_dir = Path(configured).expanduser() if configured else PROJECT_ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{(data_dir / 'libris.db').resolve().as_posix()}"
        raw = str(value).strip()
        if raw.startswith("sqlite:///"):
            return raw
        if raw.startswith("sqlite://"):
            raise ValueError("DATABASE_URL SQLite deve usar o formato sqlite:///caminho/arquivo.db.")
        raise ValueError("Este projeto utiliza SQLite. Configure DATABASE_URL com sqlite:///caminho/arquivo.db.")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

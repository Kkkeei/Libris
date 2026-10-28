from pathlib import Path
import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    app_name: str = "Libris API"
    app_version: str = "0.2.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = ""
    data_dir: str = ""
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    sql_echo: bool = False
    auth_secret_key: str = ""
    access_token_minutes: int = Field(default=480, ge=5, le=1440)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Bibliotecária"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def normalize_data_dir(cls, value: object) -> str:
        raw = str(value or "").strip()
        if raw:
            return str(Path(raw).expanduser().resolve())
        env_value = os.getenv("LIBRIS_DATA_DIR", "").strip()
        return str(Path(env_value).expanduser().resolve()) if env_value else str(REPOSITORY_ROOT / "data")

    @field_validator("database_url", mode="before")
    @classmethod
    def default_persistent_sqlite(cls, value: object) -> str:
        raw = str(value or "").strip()
        if raw:
            if raw.startswith("sqlite:///"):
                return raw
            raise ValueError("Este projeto utiliza SQLite. DATABASE_URL deve usar sqlite:///caminho/arquivo.db.")
        env_value = os.getenv("LIBRIS_DATA_DIR", "").strip()
        data_dir = Path(env_value).expanduser().resolve() if env_value else REPOSITORY_ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(data_dir / 'libris.db').resolve().as_posix()}"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                import json
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return value


from functools import lru_cache


@lru_cache
def get_settings() -> Settings:
    return Settings()

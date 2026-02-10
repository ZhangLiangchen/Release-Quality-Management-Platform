from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Release Quality Management Platform"
    env: str = "dev"

    database_url: str = "sqlite:///./qms.db"
    jwt_secret: str = "change_me"
    jwt_expire_min: int = 1440

    upload_dir: str = "./uploads"
    upload_public_prefix: str = "/uploads/"

    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

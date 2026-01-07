from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env."""

    openai_api_key: Optional[str] = None
    api_key: Optional[str] = None
    database_url: str = "sqlite:///./ltm.db"
    environment: str = "development"
    allowed_origins: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

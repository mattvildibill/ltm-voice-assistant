from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env."""

    openai_api_key: Optional[str] = None
    api_key: Optional[str] = None
    database_url: str = "sqlite:///./ltm.db"
    environment: str = "development"
    allowed_origins: Optional[str] = None
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_exp_minutes: int = 60 * 24 * 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Sales Agent Platform"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = (
        "mysql+asyncmy://ai_sales_agent:change-me@mysql:3306/ai_sales_agent?charset=utf8mb4"
    )
    redis_url: str = "redis://:change-me@redis:6379/0"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "ai-sales-agent-platform"
    jwt_audience: str = "ai-sales-agent-api"
    access_token_expire_minutes: int = 15
    dify_api_base_url: str = "https://api.dify.ai/v1"
    dify_api_key: str = ""
    dify_timeout_seconds: float = 30.0
    config_encryption_key: str = ""
    config_encryption_key_version: str = "v1"

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

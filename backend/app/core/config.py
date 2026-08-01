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
    access_token_expire_minutes: int = 24 * 60
    refresh_token_expire_days: int = 30
    dify_api_base_url: str = "https://api.dify.ai/v1"
    dify_api_key: str = ""
    dify_timeout_seconds: float = 30.0
    whatsapp_graph_api_base_url: str = "https://graph.facebook.com"
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_timeout_seconds: float = 15.0
    whatsapp_processing_timeout_seconds: int = 60
    whatsapp_webhook_max_bytes: int = 1_048_576
    whatsapp_gateway_url: str = "http://whatsapp-connector:3001"
    whatsapp_gateway_token: str = ""
    whatsapp_gateway_timeout_seconds: float = 20.0
    whatsapp_ai_retry_worker_enabled: bool = True
    whatsapp_ai_retry_poll_seconds: float = 2.0
    whatsapp_ai_retry_max_delay_seconds: int = 300
    config_encryption_key: str = ""
    config_encryption_key_version: str = "v1"
    rag_embedding_dimensions: int = 384
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_max_upload_bytes: int = 20 * 1024 * 1024
    chroma_url: str = "http://chroma:8000"
    chroma_collection: str = "ai_sales_knowledge"
    chroma_enabled: bool = True

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

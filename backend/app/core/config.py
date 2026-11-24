"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for MedServicePrice.kz backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice",
        alias="DATABASE_URL",
    )
    user_agent: str = Field(
        default="MedServicePriceBot/0.1 (+https://medserviceprice.kz; public-price-aggregator)",
        alias="USER_AGENT",
        min_length=5,
    )
    default_min_delay_sec: float = Field(
        default=1.5,
        alias="DEFAULT_MIN_DELAY_SEC",
        ge=1.5,
    )
    default_max_jitter_sec: float = Field(
        default=0.5,
        alias="DEFAULT_MAX_JITTER_SEC",
        ge=0.0,
    )
    http_timeout_sec: float = Field(
        default=20.0,
        alias="HTTP_TIMEOUT_SEC",
        gt=0.0,
    )
    http_max_retries: int = Field(
        default=3,
        alias="HTTP_MAX_RETRIES",
        ge=0,
        le=10,
    )
    raw_retention_days: int = Field(
        default=90,
        alias="RAW_RETENTION_DAYS",
        ge=90,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()

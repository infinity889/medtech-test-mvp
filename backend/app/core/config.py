"""Application settings loaded from environment variables."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, model_validator
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
    usd_to_kzt_rate: Decimal = Field(
        default=Decimal("495.00"),
        alias="USD_TO_KZT_RATE",
        gt=0,
    )
    fuzzy_match_threshold: float = Field(
        default=86.0,
        alias="FUZZY_MATCH_THRESHOLD",
        ge=0.0,
        le=100.0,
    )
    fuzzy_suggestion_threshold: float = Field(
        default=60.0,
        alias="FUZZY_SUGGESTION_THRESHOLD",
        ge=0.0,
        le=100.0,
    )
    offer_max_age_days: int = Field(
        default=30,
        alias="OFFER_MAX_AGE_DAYS",
        ge=1,
    )
    admin_api_token: str = Field(
        default="dev-admin-token",
        alias="ADMIN_API_TOKEN",
        min_length=4,
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT", ge=1, le=65535)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_fuzzy_thresholds(self) -> "Settings":
        if self.fuzzy_suggestion_threshold > self.fuzzy_match_threshold:
            raise ValueError(
                "fuzzy_suggestion_threshold must be <= fuzzy_match_threshold"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()

"""Pydantic DTOs and fingerprinting helpers for the ingestion module."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.ingestion.models import ScrapeStatus, TriggerSource


class RawServiceInput(BaseModel):
    """Validated raw service item yielded by a source adapter."""

    clinic_name_raw: str = Field(min_length=1)
    city_raw: str = Field(min_length=1)
    address_raw: str | None = None
    phone_raw: str | None = None
    working_hours_raw: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    clinic_rating_raw: float | None = None
    has_online_booking: bool | None = None
    service_name_raw: str = Field(min_length=1)
    category_hint: str | None = None
    price_raw: Decimal = Field(gt=0)
    currency_raw: str = Field(default="KZT", min_length=3, max_length=8)
    duration_days_raw: int | None = Field(default=None, ge=0)
    source_url: HttpUrl
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class SourceInfo(BaseModel):
    """Public descriptor for a registered ingestion source adapter."""

    source_id: str
    display_name: str
    supported_format: str
    cities: list[str]
    enabled: bool = True


class ScrapeRunDTO(BaseModel):
    """Read DTO for a scrape run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: str
    triggered_by: TriggerSource
    status: ScrapeStatus
    started_at: datetime
    finished_at: datetime | None
    records_fetched: int
    records_inserted: int
    records_updated: int
    errors_count: int


class ScrapeErrorDTO(BaseModel):
    """Read DTO for a scrape error entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    source_id: str
    url: str | None
    error_type: str
    message: str
    details: dict[str, Any] | None
    occurred_at: datetime


class RawServiceRecordDTO(BaseModel):
    """Read DTO exposed to downstream modules (normalization)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: str
    source_url: str
    record_fingerprint: str
    clinic_name_raw: str
    city_raw: str
    address_raw: str | None
    phone_raw: str | None
    working_hours_raw: str | None
    latitude: float | None
    longitude: float | None
    clinic_rating_raw: float | None
    has_online_booking: bool | None
    service_name_raw: str
    category_hint: str | None
    price_raw: Decimal
    currency_raw: str
    duration_days_raw: int | None
    raw_payload: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    parsed_at: datetime
    last_run_id: uuid.UUID


def _norm_key(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().lower().split())


def compute_record_fingerprint(source_id: str, item: RawServiceInput) -> str:
    """Compute a deterministic SHA-256 fingerprint for deduplication and price-change detection."""
    price_quantized = item.price_raw.quantize(Decimal("0.01"))
    parts = [
        _norm_key(source_id),
        _norm_key(item.clinic_name_raw),
        _norm_key(item.city_raw),
        _norm_key(item.address_raw),
        _norm_key(item.service_name_raw),
        str(price_quantized),
        _norm_key(item.currency_raw),
        "" if item.duration_days_raw is None else str(item.duration_days_raw),
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

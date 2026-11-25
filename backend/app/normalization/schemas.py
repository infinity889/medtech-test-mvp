"""Pydantic v2 DTOs exposed by the normalization module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.normalization.models import (
    CurrencyCode,
    MatchMethod,
    ServiceCategory,
    UnmatchedStatus,
)


class ServiceCatalogDTO(BaseModel):
    """Canonical service dictionary item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    canonical_name: str
    category: ServiceCategory
    synonyms: list[str]
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClinicDTO(BaseModel):
    """Deduplicated clinic/branch entity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: str
    clinic_key: str
    clinic_name: str
    city: str
    address: str | None
    phone: str | None
    working_hours: str | None
    latitude: float | None
    longitude: float | None
    rating: float | None
    has_online_booking: bool
    website_url: str | None
    updated_at: datetime


class ServiceOfferDTO(BaseModel):
    """Normalized service offer for one (clinic, service) pair."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    service_id: uuid.UUID
    raw_record_id: uuid.UUID
    source_id: str
    source_url: str
    service_name_raw: str
    service_name_norm: str
    category: ServiceCategory
    price_kzt: Decimal
    original_price: Decimal
    currency: CurrencyCode
    duration_days: int | None
    match_method: MatchMethod
    match_score: float
    parsed_at: datetime
    is_active: bool


class PriceHistoryPointDTO(BaseModel):
    """Single historical price observation for charting price trends."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    service_id: uuid.UUID
    offer_id: uuid.UUID | None
    price_kzt: Decimal
    recorded_at: datetime


class UnmatchedServiceDTO(BaseModel):
    """Unmatched raw service entry awaiting admin review."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_record_id: uuid.UUID
    source_id: str
    clinic_name_raw: str
    city_raw: str
    service_name_raw: str
    category_hint: str | None
    price_kzt: Decimal
    suggested_service_id: uuid.UUID | None
    suggested_score: float | None
    status: UnmatchedStatus
    resolved_service_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class SeedSummary(BaseModel):
    """Outcome summary of an idempotent catalog_seed.json load."""

    total_seed_items: int
    inserted: int
    updated: int


class NormalizationSummary(BaseModel):
    """Outcome summary of one NormalizationPipeline run."""

    records_processed: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    clinics_upserted: int = 0
    offers_inserted: int = 0
    offers_updated: int = 0
    price_history_points_added: int = 0
    skipped_errors: int = 0

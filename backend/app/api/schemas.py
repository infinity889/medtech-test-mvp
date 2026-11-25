"""Pydantic v2 request and response schemas for the search-api HTTP contract."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.ingestion.schemas import ScrapeRunDTO
from app.normalization.models import CurrencyCode, ServiceCategory, UnmatchedStatus
from app.normalization.schemas import NormalizationSummary

MoneyKzt = Annotated[
    Decimal,
    PlainSerializer(lambda value: round(float(value), 2), return_type=float, when_used="json"),
]


class OfferSortBy(StrEnum):
    """Supported sort orders for /api/v1/offers."""

    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DISTANCE_ASC = "distance_asc"
    UPDATED_DESC = "updated_desc"
    RATING_DESC = "rating_desc"


class ErrorDetail(BaseModel):
    """Inner error structure."""

    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    """Unified error response envelope."""

    error: ErrorDetail


class PaginationMeta(BaseModel):
    """Unified pagination metadata returned by all list endpoints."""

    page: int
    page_size: int
    total_items: int
    total_pages: int

    @classmethod
    def build(cls, *, page: int, page_size: int, total_items: int) -> PaginationMeta:
        total_pages = math.ceil(total_items / page_size) if total_items > 0 else 0
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )


class HealthResponse(BaseModel):
    """Response for GET /api/v1/health."""

    status: str
    database: str


class CityFilterMeta(BaseModel):
    """City option with active clinic and offer counts."""

    name: str
    clinics_count: int
    offers_count: int


class CategoryFilterMeta(BaseModel):
    """Service category option with localized Russian label and offer count."""

    code: ServiceCategory
    label_ru: str
    offers_count: int


class FiltersMetaResponse(BaseModel):
    """Metadata used to hydrate frontend search filter controls."""

    cities: list[CityFilterMeta]
    categories: list[CategoryFilterMeta]
    price_min_kzt: MoneyKzt | None
    price_max_kzt: MoneyKzt | None
    last_updated_at: datetime | None


class ServiceAutocompleteItem(BaseModel):
    """Single autocomplete suggestion from canonical service catalog."""

    service_id: uuid.UUID
    code: str
    canonical_name: str
    category: ServiceCategory
    matched_synonym: str | None = None
    offers_count: int
    min_price_kzt: MoneyKzt | None


class ServiceAutocompleteResponse(BaseModel):
    """Response for GET /api/v1/services/autocomplete."""

    items: list[ServiceAutocompleteItem]


class ClinicSummary(BaseModel):
    """Compact clinic representation embedded inside offer search results."""

    id: uuid.UUID
    source_id: str
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
    route_2gis_url: str
    route_google_maps_url: str


class OfferSearchItem(BaseModel):
    """Single comparable service offer returned by GET /api/v1/offers."""

    offer_id: uuid.UUID
    service_id: uuid.UUID
    service_code: str
    canonical_name: str
    service_name_raw: str
    category: ServiceCategory
    price_kzt: MoneyKzt
    original_price: MoneyKzt
    currency: CurrencyCode
    duration_days: int | None
    parsed_at: datetime
    source_id: str
    source_url: str
    distance_km: float | None = None
    clinic: ClinicSummary


class OfferSearchSummary(BaseModel):
    """Aggregate price statistics across all offers matching the active filter."""

    min_price_kzt: MoneyKzt | None
    max_price_kzt: MoneyKzt | None
    avg_price_kzt: MoneyKzt | None


class OfferSearchResponse(BaseModel):
    """Paginated response for GET /api/v1/offers."""

    items: list[OfferSearchItem]
    summary: OfferSearchSummary
    pagination: PaginationMeta


class ClinicListItem(BaseModel):
    """Clinic item used for clinic directory and Leaflet map markers."""

    id: uuid.UUID
    source_id: str
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
    offers_count: int
    min_price_kzt: MoneyKzt | None
    route_2gis_url: str
    route_google_maps_url: str


class ClinicListResponse(BaseModel):
    """Paginated response for GET /api/v1/clinics."""

    items: list[ClinicListItem]
    pagination: PaginationMeta


class ClinicOfferItem(BaseModel):
    """Active offer inside GET /api/v1/clinics/{clinic_id}."""

    offer_id: uuid.UUID
    service_id: uuid.UUID
    service_code: str
    canonical_name: str
    service_name_raw: str
    category: ServiceCategory
    price_kzt: MoneyKzt
    duration_days: int | None
    parsed_at: datetime
    source_url: str


class ClinicDetail(BaseModel):
    """Detailed clinic profile with contacts, route links, and active offers."""

    id: uuid.UUID
    source_id: str
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
    route_2gis_url: str
    route_google_maps_url: str
    offers: list[ClinicOfferItem]


class CompareCell(BaseModel):
    """Price cell for one (service, clinic) intersection in /api/v1/compare."""

    offer_id: uuid.UUID
    price_kzt: MoneyKzt
    duration_days: int | None
    parsed_at: datetime
    source_url: str


class CompareRow(BaseModel):
    """One service row across the 2..5 selected clinics."""

    service_id: uuid.UUID
    service_code: str
    canonical_name: str
    category: ServiceCategory
    cheapest_clinic_id: uuid.UUID | None
    cells: dict[str, CompareCell | None]


class CompareMatrixResponse(BaseModel):
    """Side-by-side comparison table across 2..5 clinics."""

    clinics: list[ClinicSummary]
    rows: list[CompareRow]


class PriceHistoryPointItem(BaseModel):
    """Single historical price observation enriched with clinic info."""

    recorded_at: datetime
    price_kzt: MoneyKzt
    clinic_id: uuid.UUID
    clinic_name: str
    city: str


class PriceHistoryResponse(BaseModel):
    """Response for GET /api/v1/services/{service_id}/price-history."""

    service_id: uuid.UUID
    service_code: str
    canonical_name: str
    points: list[PriceHistoryPointItem]


class AdminUnmatchedItem(BaseModel):
    """Admin queue item enriched with suggested canonical service name."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_record_id: uuid.UUID
    source_id: str
    clinic_name_raw: str
    city_raw: str
    service_name_raw: str
    category_hint: str | None
    price_kzt: MoneyKzt
    suggested_service_id: uuid.UUID | None
    suggested_service_name: str | None = None
    suggested_score: float | None
    status: UnmatchedStatus
    resolved_service_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class AdminUnmatchedListResponse(BaseModel):
    """Paginated response for GET /api/v1/admin/unmatched."""

    items: list[AdminUnmatchedItem]
    pagination: PaginationMeta


class AdminResolveUnmatchedRequest(BaseModel):
    """Request body for POST /api/v1/admin/unmatched/{unmatched_id}/resolve."""

    service_id: uuid.UUID
    add_as_synonym: bool = True


class AdminResolveUnmatchedResponse(BaseModel):
    """Response after resolving an unmatched item into a live offer."""

    offer_id: uuid.UUID
    clinic_id: uuid.UUID
    service_id: uuid.UUID
    price_kzt: MoneyKzt
    is_active: bool


class AdminTriggerScrapeRequest(BaseModel):
    """Request body for POST /api/v1/admin/scrape-runs."""

    source_ids: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)
    normalize: bool = True


class AdminTriggerScrapeResponse(BaseModel):
    """Response for POST /api/v1/admin/scrape-runs."""

    runs: list[ScrapeRunDTO]
    normalization_summary: NormalizationSummary | None = None


class AdminStatsResponse(BaseModel):
    """High-level normalized data counters."""

    catalog_services: int
    clinics: int
    offers_total: int
    offers_active: int
    price_history_points: int
    unmatched_pending: int

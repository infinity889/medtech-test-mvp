"""Clinic directory, clinic detail profile, and 2-5 clinic comparison matrix routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_query_service
from app.api.errors import APIError
from app.api.query_service import SearchQueryService
from app.api.schemas import ClinicDetail, ClinicListResponse, CompareMatrixResponse
from app.normalization.models import ServiceCategory

router = APIRouter(prefix="/clinics", tags=["clinics"])
compare_router = APIRouter(tags=["compare"])


def _parse_uuid_list(raw_values: list[str] | None, *, field_name: str) -> list[uuid.UUID]:
    """Parse repeated or comma-separated UUID query params while preserving order."""
    if not raw_values:
        return []
    seen: set[uuid.UUID] = set()
    parsed: list[uuid.UUID] = []
    for entry in raw_values:
        for token in entry.split(","):
            cleaned = token.strip()
            if not cleaned:
                continue
            try:
                val = uuid.UUID(cleaned)
            except ValueError as exc:
                raise APIError(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    code="VALIDATION_ERROR",
                    message=f"Invalid UUID in {field_name}: '{cleaned}'",
                ) from exc
            if val not in seen:
                seen.add(val)
                parsed.append(val)
    return parsed


@router.get("", response_model=ClinicListResponse)
def list_clinics(
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
    city: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    min_rating: Annotated[float | None, Query(ge=0.0, le=5.0)] = None,
    online_booking: bool | None = None,
    has_geo: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ClinicListResponse:
    """List clinics for directory browsing and Leaflet map markers."""
    return query_service.list_clinics(
        city=city,
        q=q,
        min_rating=min_rating,
        online_booking=online_booking,
        has_geo=has_geo,
        page=page,
        page_size=page_size,
    )


@router.get("/{clinic_id}", response_model=ClinicDetail)
def get_clinic_detail(
    clinic_id: uuid.UUID,
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
) -> ClinicDetail:
    """Return full clinic profile with contacts, route links, and active offers (<= 30d)."""
    return query_service.get_clinic_detail(clinic_id)


@compare_router.get("/compare", response_model=CompareMatrixResponse)
def compare_clinics(
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
    clinic_ids: Annotated[list[str], Query(description="2..5 clinic UUIDs (repeated or CSV)")],
    service_ids: Annotated[list[str] | None, Query()] = None,
    category: ServiceCategory | None = None,
) -> CompareMatrixResponse:
    """Compare 2 to 5 clinics side-by-side in a service x clinic price matrix."""
    parsed_clinic_ids = _parse_uuid_list(clinic_ids, field_name="clinic_ids")
    parsed_service_ids = _parse_uuid_list(service_ids, field_name="service_ids") or None
    return query_service.compare_clinics(
        clinic_ids=parsed_clinic_ids,
        service_ids=parsed_service_ids,
        category=category,
    )

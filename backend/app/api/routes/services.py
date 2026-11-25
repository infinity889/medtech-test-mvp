"""Canonical service catalog autocomplete and price history routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_query_service
from app.api.query_service import SearchQueryService
from app.api.schemas import ServiceAutocompleteResponse
from app.normalization.models import ServiceCategory

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/autocomplete", response_model=ServiceAutocompleteResponse)
def autocomplete_services(
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
    q: Annotated[str, Query(min_length=1, max_length=100)],
    category: ServiceCategory | None = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> ServiceAutocompleteResponse:
    """Return ranked canonical medical service suggestions for search autocomplete."""
    return query_service.autocomplete_services(
        q=q,
        category=category,
        city=city,
        limit=limit,
    )

"""Patient search and price-comparison offers route."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_query_service
from app.api.query_service import SearchQueryService
from app.api.schemas import OfferSearchResponse, OfferSortBy
from app.normalization.models import ServiceCategory

router = APIRouter(prefix="/offers", tags=["offers"])


@router.get("", response_model=OfferSearchResponse)
def search_offers(
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
    service_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    category: ServiceCategory | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    min_rating: Annotated[float | None, Query(ge=0.0, le=5.0)] = None,
    online_booking: bool | None = None,
    lat: Annotated[float | None, Query(ge=-90.0, le=90.0)] = None,
    lng: Annotated[float | None, Query(ge=-180.0, le=180.0)] = None,
    sort_by: OfferSortBy = OfferSortBy.PRICE_ASC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OfferSearchResponse:
    """Search comparable medical service offers with filters, geo sorting, and pagination."""
    return query_service.search_offers(
        service_id=service_id,
        q=q,
        city=city,
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        online_booking=online_booking,
        lat=lat,
        lng=lng,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

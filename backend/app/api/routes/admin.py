"""Admin endpoints protected by X-Admin-Token delegating to Ingestion & Normalization services."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_ingestion_service,
    get_normalization_service,
    get_query_service,
    get_scrape_lock,
    require_admin_token,
)
from app.api.errors import APIError
from app.api.query_service import SearchQueryService
from app.api.schemas import (
    AdminResolveUnmatchedRequest,
    AdminResolveUnmatchedResponse,
    AdminStatsResponse,
    AdminTriggerScrapeRequest,
    AdminTriggerScrapeResponse,
    AdminUnmatchedItem,
    AdminUnmatchedListResponse,
    PaginationMeta,
)
from app.ingestion.schemas import ScrapeErrorDTO, ScrapeRunDTO, SourceInfo
from app.ingestion.service import IngestionService
from app.normalization.models import UnmatchedStatus
from app.normalization.schemas import NormalizationSummary, UnmatchedServiceDTO
from app.normalization.service import NormalizationService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)


def _enrich_unmatched(
    item: UnmatchedServiceDTO,
    catalog_names: dict[uuid.UUID, str],
) -> AdminUnmatchedItem:
    suggested_name = (
        catalog_names.get(item.suggested_service_id)
        if item.suggested_service_id is not None
        else None
    )
    return AdminUnmatchedItem(
        id=item.id,
        raw_record_id=item.raw_record_id,
        source_id=item.source_id,
        clinic_name_raw=item.clinic_name_raw,
        city_raw=item.city_raw,
        service_name_raw=item.service_name_raw,
        category_hint=item.category_hint,
        price_kzt=item.price_kzt,
        suggested_service_id=item.suggested_service_id,
        suggested_service_name=suggested_name,
        suggested_score=item.suggested_score,
        status=item.status,
        resolved_service_id=item.resolved_service_id,
        resolved_at=item.resolved_at,
        created_at=item.created_at,
    )


@router.get("/sources", response_model=list[SourceInfo])
def list_sources(
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> list[SourceInfo]:
    """List all registered ingestion source adapters."""
    return ingestion_service.list_sources()


@router.get("/scrape-runs", response_model=list[ScrapeRunDTO])
def list_scrape_runs(
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    source_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ScrapeRunDTO]:
    """List recent scrape runs ordered newest first."""
    return ingestion_service.list_runs(source_id=source_id, limit=limit)


@router.get("/scrape-errors", response_model=list[ScrapeErrorDTO])
def list_scrape_errors(
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    run_id: uuid.UUID | None = None,
    source_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ScrapeErrorDTO]:
    """List structured scrape error entries."""
    return ingestion_service.list_errors(run_id=run_id, source_id=source_id, limit=limit)


@router.post("/scrape-runs", response_model=AdminTriggerScrapeResponse)
async def trigger_scrape_run(
    body: AdminTriggerScrapeRequest,
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
    scrape_lock: Annotated[asyncio.Lock, Depends(get_scrape_lock)],
) -> AdminTriggerScrapeResponse:
    """Trigger manual scraping and optional normalization with concurrent run lock (409)."""
    if scrape_lock.locked():
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="SCRAPE_IN_PROGRESS",
            message="A scrape run is already in progress",
        )

    async with scrape_lock:
        try:
            runs = await ingestion_service.trigger_run(
                source_ids=body.source_ids,
                triggered_by="manual",
                limit=body.limit,
            )
        except KeyError as exc:
            raise APIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="NOT_FOUND",
                message=f"Unknown source_id: {exc.args[0] if exc.args else exc}",
            ) from exc

        norm_summary: NormalizationSummary | None = None
        if body.normalize:
            norm_summary = await asyncio.to_thread(normalization_service.run_normalization)

    return AdminTriggerScrapeResponse(runs=runs, normalization_summary=norm_summary)


@router.get("/unmatched", response_model=AdminUnmatchedListResponse)
def list_unmatched(
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
    query_service: Annotated[SearchQueryService, Depends(get_query_service)],
    status_filter: Annotated[UnmatchedStatus, Query(alias="status")] = UnmatchedStatus.PENDING,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUnmatchedListResponse:
    """List paginated unmatched service items enriched with suggested_service_name."""
    offset = (page - 1) * page_size
    raw_items = normalization_service.list_unmatched(
        status=status_filter,
        limit=page_size,
        offset=offset,
    )
    total_items = query_service.count_unmatched(status_filter=status_filter)
    catalog_names = {svc.id: svc.canonical_name for svc in normalization_service.list_catalog()}

    return AdminUnmatchedListResponse(
        items=[_enrich_unmatched(item, catalog_names) for item in raw_items],
        pagination=PaginationMeta.build(
            page=page,
            page_size=page_size,
            total_items=total_items,
        ),
    )


@router.post(
    "/unmatched/{unmatched_id}/resolve",
    response_model=AdminResolveUnmatchedResponse,
)
def resolve_unmatched(
    unmatched_id: uuid.UUID,
    body: AdminResolveUnmatchedRequest,
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
) -> AdminResolveUnmatchedResponse:
    """Manually map an unmatched entry to a canonical service and create/update live offer."""
    try:
        offer = normalization_service.resolve_unmatched(
            unmatched_id,
            body.service_id,
            add_as_synonym=body.add_as_synonym,
        )
    except LookupError as exc:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=str(exc),
        ) from exc

    return AdminResolveUnmatchedResponse(
        offer_id=offer.id,
        clinic_id=offer.clinic_id,
        service_id=offer.service_id,
        price_kzt=offer.price_kzt,
        is_active=offer.is_active,
    )


@router.post("/unmatched/{unmatched_id}/ignore", response_model=AdminUnmatchedItem)
def ignore_unmatched(
    unmatched_id: uuid.UUID,
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
) -> AdminUnmatchedItem:
    """Mark an unmatched entry as ignored."""
    try:
        ignored = normalization_service.ignore_unmatched(unmatched_id)
    except LookupError as exc:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=str(exc),
        ) from exc

    catalog_names = {svc.id: svc.canonical_name for svc in normalization_service.list_catalog()}
    return _enrich_unmatched(ignored, catalog_names)


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
) -> AdminStatsResponse:
    """Return high-level counts across normalized catalog, clinics, offers, and queue."""
    stats = normalization_service.get_stats()
    return AdminStatsResponse(**stats)

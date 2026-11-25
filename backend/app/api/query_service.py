"""Read-only SQL query service for search, autocomplete, clinics, compare, and history."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import APIError
from app.api.schemas import (
    CategoryFilterMeta,
    CityFilterMeta,
    ClinicSummary,
    FiltersMetaResponse,
    OfferSearchItem,
    OfferSearchResponse,
    OfferSearchSummary,
    OfferSortBy,
    PaginationMeta,
    ServiceAutocompleteItem,
    ServiceAutocompleteResponse,
)
from app.core.config import Settings
from app.normalization.models import (
    Clinic,
    ServiceCatalog,
    ServiceCategory,
    ServiceOffer,
)
from app.normalization.text_utils import normalize_service_text

EARTH_RADIUS_KM = 6371.0088

CATEGORY_ORDER: tuple[ServiceCategory, ...] = (
    ServiceCategory.LAB,
    ServiceCategory.DOCTOR,
    ServiceCategory.DIAGNOSTICS,
    ServiceCategory.PROCEDURE,
)

CATEGORY_LABELS_RU: dict[ServiceCategory, str] = {
    ServiceCategory.LAB: "Анализы",
    ServiceCategory.DOCTOR: "Приём врачей",
    ServiceCategory.DIAGNOSTICS: "Диагностика",
    ServiceCategory.PROCEDURE: "Процедуры",
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in kilometers using the Haversine formula."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return round(EARTH_RADIUS_KM * c, 2)


def build_2gis_url(clinic: Clinic) -> str:
    """Build a deterministic 2GIS route/location URL with address fallback."""
    if clinic.latitude is not None and clinic.longitude is not None:
        return f"https://2gis.kz/geo/{clinic.longitude:.6f},{clinic.latitude:.6f}"
    query_parts = [part for part in (clinic.city, clinic.address or clinic.clinic_name) if part]
    return f"https://2gis.kz/search/{quote(', '.join(query_parts))}"


def build_google_maps_url(clinic: Clinic) -> str:
    """Build a deterministic Google Maps directions URL with address fallback."""
    if clinic.latitude is not None and clinic.longitude is not None:
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={clinic.latitude:.6f},{clinic.longitude:.6f}"
        )
    query_parts = [part for part in (clinic.clinic_name, clinic.address, clinic.city) if part]
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(', '.join(query_parts))}"


def to_clinic_summary(clinic: Clinic) -> ClinicSummary:
    """Convert Clinic ORM instance to ClinicSummary schema."""
    return ClinicSummary(
        id=clinic.id,
        source_id=clinic.source_id,
        clinic_name=clinic.clinic_name,
        city=clinic.city,
        address=clinic.address,
        phone=clinic.phone,
        working_hours=clinic.working_hours,
        latitude=clinic.latitude,
        longitude=clinic.longitude,
        rating=clinic.rating,
        has_online_booking=clinic.has_online_booking,
        website_url=clinic.website_url,
        route_2gis_url=build_2gis_url(clinic),
        route_google_maps_url=build_google_maps_url(clinic),
    )


def _match_service_text_rank(
    *,
    norm_q: str,
    canonical_name: str,
    code: str,
    synonyms: list[str],
) -> tuple[int, str | None] | None:
    """Return (rank, matched_synonym) where lower rank is better: 0=exact, 1=prefix, 2=contains."""
    norm_canonical = normalize_service_text(canonical_name)
    norm_code = normalize_service_text(code)

    if norm_q in (norm_canonical, norm_code):
        return (0, None)

    best_syn_rank: int | None = None
    best_syn_label: str | None = None
    for syn in synonyms:
        norm_syn = normalize_service_text(syn)
        if not norm_syn:
            continue
        if norm_q == norm_syn:
            return (0, syn)
        if norm_syn.startswith(norm_q) and (best_syn_rank is None or best_syn_rank > 1):
            best_syn_rank = 1
            best_syn_label = syn
        elif norm_q in norm_syn and (best_syn_rank is None or best_syn_rank > 2):
            best_syn_rank = 2
            best_syn_label = syn

    if norm_canonical.startswith(norm_q):
        return (1, None)
    if best_syn_rank == 1:
        return (1, best_syn_label)
    if norm_q in norm_canonical or norm_q in norm_code:
        return (2, None)
    if best_syn_rank == 2:
        return (2, best_syn_label)
    return None


class SearchQueryService:
    """Read-only query service enforcing the 30-day freshness rule on all public outputs."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def _freshness_cutoff(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self._settings.offer_max_age_days)

    def get_filters_meta(self) -> FiltersMetaResponse:
        """Aggregate available cities, categories, price range, and latest update timestamp."""
        cutoff = self._freshness_cutoff()
        fresh_filter = (
            ServiceOffer.is_active.is_(True),
            ServiceOffer.parsed_at >= cutoff,
        )

        with self._session_factory() as session:
            city_rows = session.execute(
                select(
                    Clinic.city,
                    func.count(func.distinct(Clinic.id)).label("clinics_count"),
                    func.count(ServiceOffer.id).label("offers_count"),
                )
                .join(ServiceOffer, ServiceOffer.clinic_id == Clinic.id)
                .where(*fresh_filter)
                .group_by(Clinic.city)
                .order_by(func.count(ServiceOffer.id).desc(), Clinic.city.asc())
            ).all()

            category_rows = session.execute(
                select(
                    ServiceOffer.category,
                    func.count(ServiceOffer.id).label("offers_count"),
                )
                .where(*fresh_filter)
                .group_by(ServiceOffer.category)
            ).all()

            agg_row = session.execute(
                select(
                    func.min(ServiceOffer.price_kzt),
                    func.max(ServiceOffer.price_kzt),
                    func.max(ServiceOffer.parsed_at),
                ).where(*fresh_filter)
            ).one()

        counts_by_cat: dict[ServiceCategory, int] = {
            row[0]: int(row[1]) for row in category_rows
        }
        cities = [
            CityFilterMeta(
                name=str(row[0]),
                clinics_count=int(row[1]),
                offers_count=int(row[2]),
            )
            for row in city_rows
        ]
        categories = [
            CategoryFilterMeta(
                code=cat,
                label_ru=CATEGORY_LABELS_RU[cat],
                offers_count=counts_by_cat.get(cat, 0),
            )
            for cat in CATEGORY_ORDER
        ]
        return FiltersMetaResponse(
            cities=cities,
            categories=categories,
            price_min_kzt=agg_row[0],
            price_max_kzt=agg_row[1],
            last_updated_at=agg_row[2],
        )

    def autocomplete_services(
        self,
        *,
        q: str,
        category: ServiceCategory | None = None,
        city: str | None = None,
        limit: int = 10,
    ) -> ServiceAutocompleteResponse:
        """Rank canonical services by exact -> prefix -> substring match with live offer stats."""
        norm_q = normalize_service_text(q)
        if not norm_q:
            return ServiceAutocompleteResponse(items=[])

        cutoff = self._freshness_cutoff()
        with self._session_factory() as session:
            cat_stmt = select(ServiceCatalog).where(ServiceCatalog.is_active.is_(True))
            if category is not None:
                cat_stmt = cat_stmt.where(ServiceCatalog.category == category)
            catalog_rows = list(session.scalars(cat_stmt))

            matched: list[tuple[int, ServiceCatalog, str | None]] = []
            for svc in catalog_rows:
                rank_info = _match_service_text_rank(
                    norm_q=norm_q,
                    canonical_name=svc.canonical_name,
                    code=svc.code,
                    synonyms=list(svc.synonyms or []),
                )
                if rank_info is not None:
                    matched.append((rank_info[0], svc, rank_info[1]))

            if not matched:
                return ServiceAutocompleteResponse(items=[])

            matched_ids = [svc.id for _, svc, _ in matched]
            offer_stats_stmt = (
                select(
                    ServiceOffer.service_id,
                    func.count(ServiceOffer.id),
                    func.min(ServiceOffer.price_kzt),
                )
                .join(Clinic, Clinic.id == ServiceOffer.clinic_id)
                .where(
                    ServiceOffer.service_id.in_(matched_ids),
                    ServiceOffer.is_active.is_(True),
                    ServiceOffer.parsed_at >= cutoff,
                )
                .group_by(ServiceOffer.service_id)
            )
            if city is not None and city.strip():
                offer_stats_stmt = offer_stats_stmt.where(
                    func.lower(Clinic.city) == city.strip().lower()
                )
            stats_map: dict[uuid.UUID, tuple[int, Decimal | None]] = {
                row[0]: (int(row[1]), row[2])
                for row in session.execute(offer_stats_stmt).all()
            }

        ranked_items: list[tuple[int, int, str, ServiceAutocompleteItem]] = []
        for rank, svc, matched_syn in matched:
            offers_count, min_price = stats_map.get(svc.id, (0, None))
            item = ServiceAutocompleteItem(
                service_id=svc.id,
                code=svc.code,
                canonical_name=svc.canonical_name,
                category=svc.category,
                matched_synonym=matched_syn,
                offers_count=offers_count,
                min_price_kzt=min_price,
            )
            ranked_items.append((rank, -offers_count, svc.canonical_name.lower(), item))

        ranked_items.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        return ServiceAutocompleteResponse(
            items=[entry[3] for entry in ranked_items[:limit]]
        )

    def search_offers(
        self,
        *,
        service_id: uuid.UUID | None = None,
        q: str | None = None,
        city: str | None = None,
        category: ServiceCategory | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        min_rating: float | None = None,
        online_booking: bool | None = None,
        lat: float | None = None,
        lng: float | None = None,
        sort_by: OfferSortBy = OfferSortBy.PRICE_ASC,
        page: int = 1,
        page_size: int = 20,
    ) -> OfferSearchResponse:
        """Search active fresh service offers with filters, Haversine distance, and pagination."""
        if min_price is not None and max_price is not None and min_price > max_price:
            raise APIError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="VALIDATION_ERROR",
                message="min_price must be less than or equal to max_price",
            )
        if (lat is None) != (lng is None):
            raise APIError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="VALIDATION_ERROR",
                message="Both lat and lng must be provided together",
            )
        if sort_by == OfferSortBy.DISTANCE_ASC and (lat is None or lng is None):
            raise APIError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="VALIDATION_ERROR",
                message="lat and lng are required when sort_by=distance_asc",
            )

        cutoff = self._freshness_cutoff()
        norm_q = normalize_service_text(q) if q and q.strip() else ""

        with self._session_factory() as session:
            stmt = (
                select(ServiceOffer, Clinic, ServiceCatalog)
                .join(Clinic, Clinic.id == ServiceOffer.clinic_id)
                .join(ServiceCatalog, ServiceCatalog.id == ServiceOffer.service_id)
                .where(
                    ServiceOffer.is_active.is_(True),
                    ServiceOffer.parsed_at >= cutoff,
                    ServiceCatalog.is_active.is_(True),
                )
            )
            if service_id is not None:
                stmt = stmt.where(ServiceOffer.service_id == service_id)
            if city is not None and city.strip():
                stmt = stmt.where(func.lower(Clinic.city) == city.strip().lower())
            if category is not None:
                stmt = stmt.where(ServiceOffer.category == category)
            if min_price is not None:
                stmt = stmt.where(ServiceOffer.price_kzt >= min_price)
            if max_price is not None:
                stmt = stmt.where(ServiceOffer.price_kzt <= max_price)
            if min_rating is not None:
                stmt = stmt.where(Clinic.rating.is_not(None), Clinic.rating >= min_rating)
            if online_booking is not None:
                stmt = stmt.where(Clinic.has_online_booking.is_(online_booking))

            rows = list(session.execute(stmt).all())

        filtered_rows: list[tuple[ServiceOffer, Clinic, ServiceCatalog, float | None]] = []
        for offer, clinic, catalog in rows:
            if norm_q:
                service_match = _match_service_text_rank(
                    norm_q=norm_q,
                    canonical_name=catalog.canonical_name,
                    code=catalog.code,
                    synonyms=list(catalog.synonyms or []),
                )
                raw_match = norm_q in normalize_service_text(offer.service_name_raw)
                clinic_match = norm_q in normalize_service_text(clinic.clinic_name)
                if service_match is None and not raw_match and not clinic_match:
                    continue

            distance: float | None = None
            if (
                lat is not None
                and lng is not None
                and clinic.latitude is not None
                and clinic.longitude is not None
            ):
                distance = haversine_km(lat, lng, clinic.latitude, clinic.longitude)

            filtered_rows.append((offer, clinic, catalog, distance))

        if sort_by == OfferSortBy.PRICE_ASC:
            filtered_rows.sort(
                key=lambda row: (row[0].price_kzt, -row[0].parsed_at.timestamp(), str(row[0].id))
            )
        elif sort_by == OfferSortBy.PRICE_DESC:
            filtered_rows.sort(
                key=lambda row: (-row[0].price_kzt, -row[0].parsed_at.timestamp(), str(row[0].id))
            )
        elif sort_by == OfferSortBy.DISTANCE_ASC:
            filtered_rows.sort(
                key=lambda row: (
                    row[3] is None,
                    row[3] if row[3] is not None else float("inf"),
                    row[0].price_kzt,
                    str(row[0].id),
                )
            )
        elif sort_by == OfferSortBy.UPDATED_DESC:
            filtered_rows.sort(
                key=lambda row: (-row[0].parsed_at.timestamp(), row[0].price_kzt, str(row[0].id))
            )
        elif sort_by == OfferSortBy.RATING_DESC:
            filtered_rows.sort(
                key=lambda row: (
                    row[1].rating is None,
                    -(row[1].rating if row[1].rating is not None else 0.0),
                    row[0].price_kzt,
                    str(row[0].id),
                )
            )

        total_items = len(filtered_rows)
        if total_items > 0:
            prices = [row[0].price_kzt for row in filtered_rows]
            avg_price = (sum(prices, Decimal("0")) / Decimal(total_items)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            summary = OfferSearchSummary(
                min_price_kzt=min(prices),
                max_price_kzt=max(prices),
                avg_price_kzt=avg_price,
            )
        else:
            summary = OfferSearchSummary(
                min_price_kzt=None,
                max_price_kzt=None,
                avg_price_kzt=None,
            )

        start = (page - 1) * page_size
        page_rows = filtered_rows[start : start + page_size]

        items = [
            OfferSearchItem(
                offer_id=offer.id,
                service_id=offer.service_id,
                service_code=catalog.code,
                canonical_name=catalog.canonical_name,
                service_name_raw=offer.service_name_raw,
                category=offer.category,
                price_kzt=offer.price_kzt,
                original_price=offer.original_price,
                currency=offer.currency,
                duration_days=offer.duration_days,
                parsed_at=offer.parsed_at,
                source_id=offer.source_id,
                source_url=offer.source_url,
                distance_km=distance,
                clinic=to_clinic_summary(clinic),
            )
            for offer, clinic, catalog, distance in page_rows
        ]
        return OfferSearchResponse(
            items=items,
            summary=summary,
            pagination=PaginationMeta.build(
                page=page,
                page_size=page_size,
                total_items=total_items,
            ),
        )

"""Normalization pipeline transforming raw_service_records into normalized offers and history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.ingestion.schemas import RawServiceRecordDTO
from app.ingestion.service import IngestionService
from app.normalization.matcher import CatalogEntry, ServiceMatcher
from app.normalization.models import (
    Clinic,
    CurrencyCode,
    MatchMethod,
    PriceHistory,
    ServiceCatalog,
    ServiceCategory,
    ServiceOffer,
    UnmatchedService,
    UnmatchedStatus,
)
from app.normalization.schemas import NormalizationSummary
from app.normalization.text_utils import compute_clinic_key, convert_to_kzt


def _extract_website_origin(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def upsert_clinic(session: Session, raw: RawServiceRecordDTO) -> Clinic:
    """Upsert a deduplicated clinic/branch entity preserving non-null metadata."""
    key = compute_clinic_key(raw.source_id, raw.clinic_name_raw, raw.city_raw, raw.address_raw)
    clinic = session.scalar(select(Clinic).where(Clinic.clinic_key == key))
    now = datetime.now(UTC)
    origin = _extract_website_origin(raw.source_url)

    if clinic is None:
        clinic = Clinic(
            id=uuid.uuid4(),
            source_id=raw.source_id,
            clinic_key=key,
            clinic_name=raw.clinic_name_raw.strip(),
            city=raw.city_raw.strip(),
            address=raw.address_raw.strip() if raw.address_raw else None,
            phone=raw.phone_raw.strip() if raw.phone_raw else None,
            working_hours=raw.working_hours_raw.strip() if raw.working_hours_raw else None,
            latitude=raw.latitude,
            longitude=raw.longitude,
            rating=raw.clinic_rating_raw,
            has_online_booking=bool(raw.has_online_booking),
            website_url=origin,
            updated_at=now,
        )
        session.add(clinic)
        session.flush()
        return clinic

    if raw.phone_raw:
        clinic.phone = raw.phone_raw.strip()
    if raw.working_hours_raw:
        clinic.working_hours = raw.working_hours_raw.strip()
    if raw.latitude is not None:
        clinic.latitude = raw.latitude
    if raw.longitude is not None:
        clinic.longitude = raw.longitude
    if raw.clinic_rating_raw is not None:
        clinic.rating = raw.clinic_rating_raw
    if raw.has_online_booking is True:
        clinic.has_online_booking = True
    if origin and not clinic.website_url:
        clinic.website_url = origin
    clinic.updated_at = now
    return clinic


def upsert_service_offer_and_history(
    session: Session,
    *,
    clinic: Clinic,
    service_id: uuid.UUID,
    canonical_name: str,
    category: ServiceCategory,
    raw: RawServiceRecordDTO,
    price_kzt: Decimal,
    currency: CurrencyCode,
    match_method: MatchMethod,
    match_score: float,
    is_fresh: bool,
) -> tuple[ServiceOffer, bool, bool, bool]:
    """Upsert ServiceOffer for (clinic, service) and append PriceHistory on new/changed price.

    Returns: (offer, was_inserted, was_updated, history_added)
    """
    existing = session.scalar(
        select(ServiceOffer).where(
            ServiceOffer.clinic_id == clinic.id,
            ServiceOffer.service_id == service_id,
        )
    )

    if existing is None:
        offer = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic.id,
            service_id=service_id,
            raw_record_id=raw.id,
            source_id=raw.source_id,
            source_url=raw.source_url,
            service_name_raw=raw.service_name_raw,
            service_name_norm=canonical_name,
            category=category,
            price_kzt=price_kzt,
            original_price=raw.price_raw,
            currency=currency,
            duration_days=raw.duration_days_raw,
            match_method=match_method,
            match_score=match_score,
            parsed_at=raw.parsed_at,
            is_active=is_fresh,
        )
        session.add(offer)
        session.flush()
        session.add(
            PriceHistory(
                id=uuid.uuid4(),
                clinic_id=clinic.id,
                service_id=service_id,
                offer_id=offer.id,
                price_kzt=price_kzt,
                recorded_at=raw.parsed_at,
            )
        )
        return offer, True, False, True

    should_replace = (
        raw.parsed_at > existing.parsed_at
        or (raw.parsed_at == existing.parsed_at and price_kzt < existing.price_kzt)
        or existing.raw_record_id == raw.id
        or match_method == MatchMethod.MANUAL
    )
    if not should_replace:
        return existing, False, False, False

    existing.raw_record_id = raw.id
    existing.source_url = raw.source_url
    existing.service_name_raw = raw.service_name_raw
    existing.service_name_norm = canonical_name
    existing.category = category
    existing.price_kzt = price_kzt
    existing.original_price = raw.price_raw
    existing.currency = currency
    existing.duration_days = raw.duration_days_raw
    existing.match_method = match_method
    existing.match_score = match_score
    existing.parsed_at = raw.parsed_at
    existing.is_active = is_fresh

    last_history = session.scalar(
        select(PriceHistory)
        .where(
            PriceHistory.clinic_id == clinic.id,
            PriceHistory.service_id == service_id,
        )
        .order_by(desc(PriceHistory.recorded_at), desc(PriceHistory.id))
        .limit(1)
    )
    history_added = False
    if last_history is None or last_history.price_kzt != price_kzt:
        session.add(
            PriceHistory(
                id=uuid.uuid4(),
                clinic_id=clinic.id,
                service_id=service_id,
                offer_id=existing.id,
                price_kzt=price_kzt,
                recorded_at=raw.parsed_at,
            )
        )
        history_added = True

    return existing, False, True, history_added


class NormalizationPipeline:
    """Consumes raw records via IngestionService and populates normalized tables."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        ingestion_service: IngestionService,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ingestion_service = ingestion_service
        self._settings = settings or Settings()

    def _build_matcher(self, session: Session) -> ServiceMatcher:
        rows = list(
            session.scalars(select(ServiceCatalog).where(ServiceCatalog.is_active.is_(True)))
        )
        entries = [
            CatalogEntry(
                id=row.id,
                code=row.code,
                canonical_name=row.canonical_name,
                category=row.category,
                synonyms=tuple(row.synonyms or ()),
            )
            for row in rows
        ]
        return ServiceMatcher(
            entries,
            fuzzy_match_threshold=self._settings.fuzzy_match_threshold,
            fuzzy_suggestion_threshold=self._settings.fuzzy_suggestion_threshold,
        )

    def run(
        self,
        *,
        updated_since: datetime | None = None,
        source_id: str | None = None,
        batch_size: int = 500,
    ) -> NormalizationSummary:
        """Stream raw records from IngestionService and normalize them idempotently."""
        summary = NormalizationSummary()
        now = datetime.now(UTC)
        freshness_cutoff = now - timedelta(days=self._settings.offer_max_age_days)
        seen_clinic_ids: set[uuid.UUID] = set()

        with self._session_factory() as session:
            matcher = self._build_matcher(session)

        for batch in self._ingestion_service.iter_raw_records(
            updated_since=updated_since,
            source_id=source_id,
            batch_size=batch_size,
        ):
            with self._session_factory() as session:
                for raw in batch:
                    summary.records_processed += 1
                    try:
                        price_kzt, currency = convert_to_kzt(
                            raw.price_raw,
                            raw.currency_raw,
                            self._settings.usd_to_kzt_rate,
                        )
                    except ValueError:
                        summary.skipped_errors += 1
                        continue

                    match = matcher.match(
                        raw.service_name_raw,
                        category_hint=raw.category_hint,
                    )
                    if (
                        match.is_matched
                        and match.service_id is not None
                        and match.canonical_name is not None
                        and match.category is not None
                        and match.method is not None
                    ):
                        summary.matched_count += 1
                        clinic = upsert_clinic(session, raw)
                        seen_clinic_ids.add(clinic.id)

                        is_fresh = raw.parsed_at >= freshness_cutoff
                        _, inserted, updated, hist_added = upsert_service_offer_and_history(
                            session,
                            clinic=clinic,
                            service_id=match.service_id,
                            canonical_name=match.canonical_name,
                            category=match.category,
                            raw=raw,
                            price_kzt=price_kzt,
                            currency=currency,
                            match_method=match.method,
                            match_score=match.score,
                            is_fresh=is_fresh,
                        )
                        if inserted:
                            summary.offers_inserted += 1
                        elif updated:
                            summary.offers_updated += 1
                        if hist_added:
                            summary.price_history_points_added += 1

                        # If this raw record was previously pending in unmatched queue, resolve it
                        prev_unmatched = session.scalar(
                            select(UnmatchedService).where(
                                UnmatchedService.raw_record_id == raw.id,
                                UnmatchedService.status == UnmatchedStatus.PENDING,
                            )
                        )
                        if prev_unmatched is not None:
                            prev_unmatched.status = UnmatchedStatus.MAPPED
                            prev_unmatched.resolved_service_id = match.service_id
                            prev_unmatched.resolved_at = now
                    else:
                        summary.unmatched_count += 1
                        existing_unmatched = session.scalar(
                            select(UnmatchedService).where(
                                UnmatchedService.raw_record_id == raw.id
                            )
                        )
                        if existing_unmatched is None:
                            session.add(
                                UnmatchedService(
                                    id=uuid.uuid4(),
                                    raw_record_id=raw.id,
                                    source_id=raw.source_id,
                                    clinic_name_raw=raw.clinic_name_raw,
                                    city_raw=raw.city_raw,
                                    service_name_raw=raw.service_name_raw,
                                    category_hint=raw.category_hint,
                                    price_kzt=price_kzt,
                                    suggested_service_id=match.suggested_service_id,
                                    suggested_score=match.suggested_score,
                                    status=UnmatchedStatus.PENDING,
                                    created_at=now,
                                )
                            )
                        elif existing_unmatched.status == UnmatchedStatus.PENDING:
                            existing_unmatched.price_kzt = price_kzt
                            existing_unmatched.suggested_service_id = match.suggested_service_id
                            existing_unmatched.suggested_score = match.suggested_score

                session.commit()

        summary.clinics_upserted = len(seen_clinic_ids)
        return summary

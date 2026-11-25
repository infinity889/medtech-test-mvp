"""Public provider service contract for the normalization module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, asc, desc, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.registry import default_registry
from app.ingestion.models import RawServiceRecord
from app.ingestion.schemas import RawServiceRecordDTO
from app.ingestion.service import IngestionService
from app.normalization.catalog_loader import load_catalog_seed
from app.normalization.models import (
    Clinic,
    MatchMethod,
    PriceHistory,
    ServiceCatalog,
    ServiceCategory,
    ServiceOffer,
    UnmatchedService,
    UnmatchedStatus,
)
from app.normalization.pipeline import (
    NormalizationPipeline,
    upsert_clinic,
    upsert_service_offer_and_history,
)
from app.normalization.schemas import (
    NormalizationSummary,
    PriceHistoryPointDTO,
    SeedSummary,
    ServiceCatalogDTO,
    ServiceOfferDTO,
    UnmatchedServiceDTO,
)
from app.normalization.text_utils import convert_to_kzt, normalize_service_text


def _merge_synonyms(existing: list[str], incoming: list[str]) -> list[str]:
    """Merge synonym lists preserving order and deduplicating by normalized form."""
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*existing, *incoming]:
        cleaned = item.strip()
        norm = normalize_service_text(cleaned)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        merged.append(cleaned)
    return merged


class NormalizationService:
    """Facade consumed by search-api and CLI for catalog, offers, history, and unmatched queue."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        ingestion_service: IngestionService,
        settings: Settings | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ingestion_service = ingestion_service
        self._settings = settings or Settings()
        self._engine = engine
        self._pipeline = NormalizationPipeline(
            session_factory=self._session_factory,
            ingestion_service=self._ingestion_service,
            settings=self._settings,
        )

    def close(self) -> None:
        """Dispose owned SQLAlchemy engine resources if created by factory."""
        if self._engine is not None:
            self._engine.dispose()

    def seed_catalog(self, seed_path: Path | None = None) -> SeedSummary:
        """Idempotently load or update canonical services from catalog_seed.json."""
        seed_items = load_catalog_seed(seed_path)
        now = datetime.now(UTC)
        inserted = 0
        updated = 0

        with self._session_factory() as session:
            existing_by_code = {
                row.code: row for row in session.scalars(select(ServiceCatalog))
            }
            for item in seed_items:
                existing = existing_by_code.get(item.code)
                if existing is None:
                    session.add(
                        ServiceCatalog(
                            id=uuid.uuid4(),
                            code=item.code,
                            canonical_name=item.canonical_name,
                            category=item.category,
                            synonyms=_merge_synonyms([], item.synonyms),
                            description=item.description,
                            is_active=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    inserted += 1
                else:
                    merged_syns = _merge_synonyms(list(existing.synonyms or []), item.synonyms)
                    changed = (
                        existing.canonical_name != item.canonical_name
                        or existing.category != item.category
                        or existing.description != item.description
                        or list(existing.synonyms or []) != merged_syns
                    )
                    if changed:
                        existing.canonical_name = item.canonical_name
                        existing.category = item.category
                        existing.description = item.description
                        existing.synonyms = merged_syns
                        existing.updated_at = now
                        updated += 1
            session.commit()

        return SeedSummary(
            total_seed_items=len(seed_items),
            inserted=inserted,
            updated=updated,
        )

    def run_normalization(
        self,
        *,
        updated_since: datetime | None = None,
        source_id: str | None = None,
        batch_size: int = 500,
    ) -> NormalizationSummary:
        """Run normalization pipeline over raw records from IngestionService."""
        return self._pipeline.run(
            updated_since=updated_since,
            source_id=source_id,
            batch_size=batch_size,
        )

    def list_catalog(
        self,
        *,
        category: ServiceCategory | None = None,
        query: str | None = None,
    ) -> list[ServiceCatalogDTO]:
        """List active canonical services with optional category and substring query filter."""
        stmt = (
            select(ServiceCatalog)
            .where(ServiceCatalog.is_active.is_(True))
            .order_by(asc(ServiceCatalog.canonical_name))
        )
        if category is not None:
            stmt = stmt.where(ServiceCatalog.category == category)

        with self._session_factory() as session:
            rows = list(session.scalars(stmt))

        if query is not None and query.strip():
            norm_q = normalize_service_text(query)
            filtered: list[ServiceCatalog] = []
            for row in rows:
                haystack = [row.canonical_name, *(row.synonyms or [])]
                if any(norm_q in normalize_service_text(term) for term in haystack):
                    filtered.append(row)
            rows = filtered

        return [ServiceCatalogDTO.model_validate(row) for row in rows]

    def list_unmatched(
        self,
        *,
        status: UnmatchedStatus = UnmatchedStatus.PENDING,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UnmatchedServiceDTO]:
        """List unmatched queue items filtered by lifecycle status."""
        stmt = (
            select(UnmatchedService)
            .where(UnmatchedService.status == status)
            .order_by(
                desc(UnmatchedService.suggested_score).nulls_last(),
                desc(UnmatchedService.created_at),
            )
            .offset(offset)
            .limit(limit)
        )
        with self._session_factory() as session:
            rows = list(session.scalars(stmt))
        return [UnmatchedServiceDTO.model_validate(row) for row in rows]

    def resolve_unmatched(
        self,
        unmatched_id: uuid.UUID,
        service_id: uuid.UUID,
        *,
        add_as_synonym: bool = True,
    ) -> ServiceOfferDTO:
        """Map an unmatched item to a canonical service, optionally adding its name as synonym."""
        now = datetime.now(UTC)
        freshness_cutoff = now - timedelta(days=self._settings.offer_max_age_days)

        with self._session_factory() as session:
            unmatched = session.get(UnmatchedService, unmatched_id)
            if unmatched is None:
                raise LookupError(f"UnmatchedService not found: {unmatched_id}")

            catalog = session.get(ServiceCatalog, service_id)
            if catalog is None:
                raise LookupError(f"ServiceCatalog not found: {service_id}")

            raw_row = session.get(RawServiceRecord, unmatched.raw_record_id)
            if raw_row is None:
                raise LookupError(f"RawServiceRecord not found: {unmatched.raw_record_id}")

            primary_offer = self._materialize_manual_mapping(
                session=session,
                unmatched=unmatched,
                raw_row=raw_row,
                catalog=catalog,
                now=now,
                freshness_cutoff=freshness_cutoff,
            )

            if add_as_synonym:
                catalog.synonyms = _merge_synonyms(
                    list(catalog.synonyms or []),
                    [unmatched.service_name_raw],
                )
                catalog.updated_at = now

                # Automatically resolve other pending items sharing the same normalized raw name
                target_norm = normalize_service_text(unmatched.service_name_raw)
                siblings = list(
                    session.scalars(
                        select(UnmatchedService).where(
                            UnmatchedService.status == UnmatchedStatus.PENDING,
                            UnmatchedService.id != unmatched.id,
                        )
                    )
                )
                for sibling in siblings:
                    if normalize_service_text(sibling.service_name_raw) != target_norm:
                        continue
                    sib_raw = session.get(RawServiceRecord, sibling.raw_record_id)
                    if sib_raw is None:
                        continue
                    self._materialize_manual_mapping(
                        session=session,
                        unmatched=sibling,
                        raw_row=sib_raw,
                        catalog=catalog,
                        now=now,
                        freshness_cutoff=freshness_cutoff,
                    )

            session.commit()
            session.refresh(primary_offer)
            return ServiceOfferDTO.model_validate(primary_offer)

    def _materialize_manual_mapping(
        self,
        *,
        session: Session,
        unmatched: UnmatchedService,
        raw_row: RawServiceRecord,
        catalog: ServiceCatalog,
        now: datetime,
        freshness_cutoff: datetime,
    ) -> ServiceOffer:
        raw_dto = RawServiceRecordDTO.model_validate(raw_row)
        price_kzt, currency = convert_to_kzt(
            raw_dto.price_raw,
            raw_dto.currency_raw,
            self._settings.usd_to_kzt_rate,
        )
        clinic = upsert_clinic(session, raw_dto)
        offer, _, _, _ = upsert_service_offer_and_history(
            session,
            clinic=clinic,
            service_id=catalog.id,
            canonical_name=catalog.canonical_name,
            category=catalog.category,
            raw=raw_dto,
            price_kzt=price_kzt,
            currency=currency,
            match_method=MatchMethod.MANUAL,
            match_score=100.0,
            is_fresh=raw_dto.parsed_at >= freshness_cutoff,
        )
        unmatched.status = UnmatchedStatus.MAPPED
        unmatched.resolved_service_id = catalog.id
        unmatched.resolved_at = now
        return offer

    def ignore_unmatched(self, unmatched_id: uuid.UUID) -> UnmatchedServiceDTO:
        """Mark a noisy or out-of-scope unmatched entry as ignored."""
        now = datetime.now(UTC)
        with self._session_factory() as session:
            unmatched = session.get(UnmatchedService, unmatched_id)
            if unmatched is None:
                raise LookupError(f"UnmatchedService not found: {unmatched_id}")
            unmatched.status = UnmatchedStatus.IGNORED
            unmatched.resolved_at = now
            session.commit()
            session.refresh(unmatched)
            return UnmatchedServiceDTO.model_validate(unmatched)

    def get_price_history(
        self,
        *,
        service_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        days: int = 90,
    ) -> list[PriceHistoryPointDTO]:
        """Return chronological price history points for a canonical service."""
        if days < 1:
            raise ValueError("days must be >= 1")
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(PriceHistory)
            .where(
                PriceHistory.service_id == service_id,
                PriceHistory.recorded_at >= cutoff,
            )
            .order_by(asc(PriceHistory.recorded_at), asc(PriceHistory.id))
        )
        if clinic_id is not None:
            stmt = stmt.where(PriceHistory.clinic_id == clinic_id)

        with self._session_factory() as session:
            rows = list(session.scalars(stmt))
        return [PriceHistoryPointDTO.model_validate(row) for row in rows]

    def refresh_stale_offers(self, max_age_days: int = 30) -> int:
        """Deactivate offers older than max_age_days per TZ freshness requirement."""
        if max_age_days < 1:
            raise ValueError("max_age_days must be >= 1")
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        stmt = (
            update(ServiceOffer)
            .where(
                ServiceOffer.is_active.is_(True),
                ServiceOffer.parsed_at < cutoff,
            )
            .values(is_active=False)
            .returning(ServiceOffer.id)
        )
        with self._session_factory() as session:
            updated_ids = list(session.scalars(stmt))
            session.commit()
            return len(updated_ids)

    def get_stats(self) -> dict[str, int]:
        """Return high-level counts across normalized tables for diagnostics and CLI."""
        with self._session_factory() as session:
            return {
                "catalog_services": int(
                    session.scalar(select(func.count()).select_from(ServiceCatalog)) or 0
                ),
                "clinics": int(session.scalar(select(func.count()).select_from(Clinic)) or 0),
                "offers_total": int(
                    session.scalar(select(func.count()).select_from(ServiceOffer)) or 0
                ),
                "offers_active": int(
                    session.scalar(
                        select(func.count())
                        .select_from(ServiceOffer)
                        .where(ServiceOffer.is_active.is_(True))
                    )
                    or 0
                ),
                "price_history_points": int(
                    session.scalar(select(func.count()).select_from(PriceHistory)) or 0
                ),
                "unmatched_pending": int(
                    session.scalar(
                        select(func.count())
                        .select_from(UnmatchedService)
                        .where(UnmatchedService.status == UnmatchedStatus.PENDING)
                    )
                    or 0
                ),
            }


def create_default_normalization_service(settings: Settings | None = None) -> NormalizationService:
    """Build a NormalizationService wired to PostgreSQL and IngestionService."""
    resolved = settings or Settings()
    engine = create_db_engine(resolved.database_url)
    session_factory = create_session_factory(engine)
    ingestion_svc = IngestionService(
        session_factory=session_factory,
        registry=default_registry,
        settings=resolved,
    )
    return NormalizationService(
        session_factory=session_factory,
        ingestion_service=ingestion_svc,
        settings=resolved,
        engine=engine,
    )

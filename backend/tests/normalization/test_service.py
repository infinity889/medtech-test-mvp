"""Integration tests for NormalizationService public contract and CLI."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.registry import AdapterRegistry
from app.ingestion.models import RawServiceRecord, ScrapeRun, ScrapeStatus, TriggerSource
from app.ingestion.service import IngestionService
from app.normalization.cli import run_cli
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
from app.normalization.service import NormalizationService


def test_seed_catalog_is_idempotent_and_list_catalog_filters() -> None:
    settings = Settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        ingestion_svc = IngestionService(
            session_factory=session_factory, registry=AdapterRegistry(), settings=settings
        )
        svc = NormalizationService(
            session_factory=session_factory,
            ingestion_service=ingestion_svc,
            settings=settings,
        )

        first = svc.seed_catalog()
        assert first.total_seed_items >= 65

        second = svc.seed_catalog()
        assert second.inserted == 0
        assert second.total_seed_items == first.total_seed_items

        labs = svc.list_catalog(category=ServiceCategory.LAB)
        assert len(labs) >= 30
        assert all(item.category == ServiceCategory.LAB for item in labs)

        oak_matches = svc.list_catalog(query="CBC")
        assert any(item.code == "lab_oak" for item in oak_matches)
    finally:
        engine.dispose()


def test_resolve_unmatched_feedback_loop_ignore_history_and_stale_refresh(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    tag = uuid.uuid4().hex[:8]
    src = f"svc_norm_{tag}"
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    custom_cat_id = uuid.uuid4()
    raw_u1 = uuid.uuid4()
    raw_u2 = uuid.uuid4()
    raw_ign = uuid.uuid4()
    weird_name = f"Уникальный тест-{tag}"

    try:
        with session_factory() as session:
            session.add_all(
                [
                    ServiceCatalog(
                        id=custom_cat_id,
                        code=f"lab_custom_{tag}",
                        canonical_name=f"Кастомный анализ {tag}",
                        category=ServiceCategory.LAB,
                        synonyms=[],
                    ),
                    ScrapeRun(
                        id=run_id,
                        source_id=src,
                        triggered_by=TriggerSource.MANUAL,
                        status=ScrapeStatus.SUCCESS,
                        started_at=now,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    RawServiceRecord(
                        id=raw_u1,
                        source_id=src,
                        source_url="https://lab1.kz/u1",
                        record_fingerprint=f"u1_{tag}",
                        clinic_name_raw="Клиника 1",
                        city_raw="Алматы",
                        service_name_raw=weird_name,
                        category_hint="лаборатория",
                        price_raw=Decimal("4100.00"),
                        currency_raw="KZT",
                        raw_payload={},
                        first_seen_at=now,
                        last_seen_at=now,
                        parsed_at=now,
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=raw_u2,
                        source_id=src,
                        source_url="https://lab2.kz/u2",
                        record_fingerprint=f"u2_{tag}",
                        clinic_name_raw="Клиника 2",
                        city_raw="Астана",
                        service_name_raw=weird_name,
                        category_hint="лаборатория",
                        price_raw=Decimal("4500.00"),
                        currency_raw="KZT",
                        raw_payload={},
                        first_seen_at=now,
                        last_seen_at=now,
                        parsed_at=now,
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=raw_ign,
                        source_id=src,
                        source_url="https://lab1.kz/ign",
                        record_fingerprint=f"ign_{tag}",
                        clinic_name_raw="Клиника 1",
                        city_raw="Алматы",
                        service_name_raw=f"Шумовая строка-{tag}",
                        category_hint="процедура",
                        price_raw=Decimal("500.00"),
                        currency_raw="KZT",
                        raw_payload={},
                        first_seen_at=now,
                        last_seen_at=now,
                        parsed_at=now,
                        last_run_id=run_id,
                    ),
                ]
            )
            session.commit()

        ingestion_svc = IngestionService(
            session_factory=session_factory, registry=AdapterRegistry(), settings=settings
        )
        svc = NormalizationService(
            session_factory=session_factory,
            ingestion_service=ingestion_svc,
            settings=settings,
        )

        summary = svc.run_normalization(source_id=src)
        assert summary.unmatched_count == 3

        pending = [
            u
            for u in svc.list_unmatched(status=UnmatchedStatus.PENDING, limit=200)
            if u.source_id == src
        ]
        assert len(pending) == 3

        item_u1 = next(u for u in pending if u.raw_record_id == raw_u1)
        item_ign = next(u for u in pending if u.raw_record_id == raw_ign)

        # Resolving u1 with add_as_synonym=True also resolves u2 with identical raw name
        offer_dto = svc.resolve_unmatched(item_u1.id, custom_cat_id, add_as_synonym=True)
        assert offer_dto.service_id == custom_cat_id
        assert offer_dto.match_method == MatchMethod.MANUAL
        assert offer_dto.price_kzt == Decimal("4100.00")

        with session_factory() as session:
            cat_row = session.get(ServiceCatalog, custom_cat_id)
            assert cat_row is not None
            assert weird_name in cat_row.synonyms

            offers = list(
                session.scalars(select(ServiceOffer).where(ServiceOffer.source_id == src))
            )
            assert len(offers) == 2

        # Ignore noisy entry
        ignored_dto = svc.ignore_unmatched(item_ign.id)
        assert ignored_dto.status == UnmatchedStatus.IGNORED

        remaining_pending = [
            u
            for u in svc.list_unmatched(status=UnmatchedStatus.PENDING, limit=200)
            if u.source_id == src
        ]
        assert remaining_pending == []

        # Price history returns both clinics' points
        history = svc.get_price_history(service_id=custom_cat_id, days=90)
        assert len(history) == 2

        # Age one offer > 30 days and verify refresh_stale_offers deactivates it
        with session_factory() as session:
            session.execute(
                update(ServiceOffer)
                .where(ServiceOffer.id == offer_dto.id)
                .values(parsed_at=now - timedelta(days=35))
            )
            session.commit()

        with pytest.raises(ValueError):
            svc.refresh_stale_offers(max_age_days=0)

        deactivated = svc.refresh_stale_offers(max_age_days=30)
        assert deactivated >= 1

        with session_factory() as session:
            refreshed = session.get(ServiceOffer, offer_dto.id)
            assert refreshed is not None
            assert refreshed.is_active is False

        # CLI smoke check
        assert run_cli(["stats"], service=svc) == 0
        out = capsys.readouterr().out
        assert "catalog_services" in out
    finally:
        with session_factory() as session:
            clinic_ids = list(session.scalars(select(Clinic.id).where(Clinic.source_id == src)))
            if clinic_ids:
                session.execute(delete(PriceHistory).where(PriceHistory.clinic_id.in_(clinic_ids)))
            session.execute(delete(UnmatchedService).where(UnmatchedService.source_id == src))
            session.execute(delete(ServiceOffer).where(ServiceOffer.source_id == src))
            session.execute(delete(Clinic).where(Clinic.source_id == src))
            session.execute(delete(ServiceCatalog).where(ServiceCatalog.id == custom_cat_id))
            session.execute(delete(RawServiceRecord).where(RawServiceRecord.source_id == src))
            session.execute(delete(ScrapeRun).where(ScrapeRun.id == run_id))
            session.commit()
        engine.dispose()

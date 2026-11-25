"""Integration tests for NormalizationPipeline against PostgreSQL 16."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.registry import AdapterRegistry
from app.ingestion.models import RawServiceRecord, ScrapeRun, ScrapeStatus, TriggerSource
from app.ingestion.service import IngestionService
from app.normalization.models import (
    Clinic,
    CurrencyCode,
    PriceHistory,
    ServiceCatalog,
    ServiceCategory,
    ServiceOffer,
    UnmatchedService,
    UnmatchedStatus,
)
from app.normalization.pipeline import NormalizationPipeline


def test_pipeline_normalizes_converts_deduplicates_tracks_history_and_queues_unmatched() -> None:
    settings = Settings(usd_to_kzt_rate=Decimal("500.00"), offer_max_age_days=30)
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    tag = uuid.uuid4().hex[:8]
    src = f"pipe_src_{tag}"
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    oak_cat_id = uuid.uuid4()
    terapevt_cat_id = uuid.uuid4()
    raw_oak_id = uuid.uuid4()
    raw_usd_id = uuid.uuid4()
    raw_stale_id = uuid.uuid4()
    raw_unmatched_id = uuid.uuid4()
    raw_oak_new_price_id = uuid.uuid4()

    try:
        with session_factory() as session:
            session.add_all(
                [
                    ServiceCatalog(
                        id=oak_cat_id,
                        code=f"lab_oak_{tag}",
                        canonical_name=f"Общий анализ крови {tag}",
                        category=ServiceCategory.LAB,
                        synonyms=[f"ОАК {tag}", f"CBC {tag}"],
                    ),
                    ServiceCatalog(
                        id=terapevt_cat_id,
                        code=f"doc_terapevt_{tag}",
                        canonical_name=f"Приём терапевта {tag}",
                        category=ServiceCategory.DOCTOR,
                        synonyms=[f"Терапевт {tag}"],
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
                        id=raw_oak_id,
                        source_id=src,
                        source_url="https://lab.kz/oak",
                        record_fingerprint=f"fp1_{tag}",
                        clinic_name_raw="Лаб Тест",
                        city_raw="Алматы",
                        address_raw="ул. Абая 1",
                        phone_raw="+77001112233",
                        working_hours_raw="Пн-Пт 08:00-18:00",
                        latitude=43.23,
                        longitude=76.94,
                        service_name_raw=f"ОАК {tag}",
                        category_hint="лаборатория",
                        price_raw=Decimal("3000.00"),
                        currency_raw="KZT",
                        duration_days_raw=1,
                        raw_payload={},
                        first_seen_at=now - timedelta(hours=2),
                        last_seen_at=now - timedelta(hours=2),
                        parsed_at=now - timedelta(hours=2),
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=raw_usd_id,
                        source_id=src,
                        source_url="https://clinic.kz/terapevt",
                        record_fingerprint=f"fp2_{tag}",
                        clinic_name_raw="МедЦентр USD",
                        city_raw="Астана",
                        address_raw="пр. Мангилик Ел 10",
                        service_name_raw=f"Терапевт {tag}",
                        category_hint="приём врача",
                        price_raw=Decimal("20.00"),
                        currency_raw="USD",
                        raw_payload={},
                        first_seen_at=now,
                        last_seen_at=now,
                        parsed_at=now,
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=raw_stale_id,
                        source_id=src,
                        source_url="https://old.kz/oak",
                        record_fingerprint=f"fp3_{tag}",
                        clinic_name_raw="Старая Лаб",
                        city_raw="Шымкент",
                        service_name_raw=f"CBC {tag}",
                        category_hint="лаборатория",
                        price_raw=Decimal("2500.00"),
                        currency_raw="KZT",
                        raw_payload={},
                        first_seen_at=now - timedelta(days=45),
                        last_seen_at=now - timedelta(days=45),
                        parsed_at=now - timedelta(days=45),
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=raw_unmatched_id,
                        source_id=src,
                        source_url="https://lab.kz/weird",
                        record_fingerprint=f"fp4_{tag}",
                        clinic_name_raw="Лаб Тест",
                        city_raw="Алматы",
                        address_raw="ул. Абая 1",
                        service_name_raw=f"Экзотический тест ZZZ-{tag}",
                        category_hint="лаборатория",
                        price_raw=Decimal("9900.00"),
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
            session_factory=session_factory,
            registry=AdapterRegistry(),
            settings=settings,
        )
        pipeline = NormalizationPipeline(
            session_factory=session_factory,
            ingestion_service=ingestion_svc,
            settings=settings,
        )

        # Pass 1: initial normalization
        summary1 = pipeline.run(source_id=src)
        assert summary1.records_processed == 4
        assert summary1.matched_count == 3
        assert summary1.unmatched_count == 1
        assert summary1.offers_inserted == 3
        assert summary1.price_history_points_added == 3

        with session_factory() as session:
            offers = list(
                session.scalars(select(ServiceOffer).where(ServiceOffer.source_id == src))
            )
            assert len(offers) == 3
            usd_offer = next(o for o in offers if o.currency == CurrencyCode.USD)
            assert usd_offer.original_price == Decimal("20.00")
            assert usd_offer.price_kzt == Decimal("10000.00")
            assert usd_offer.is_active is True

            stale_offer = next(o for o in offers if o.raw_record_id == raw_stale_id)
            assert stale_offer.is_active is False

            unmatched = list(
                session.scalars(select(UnmatchedService).where(UnmatchedService.source_id == src))
            )
            assert len(unmatched) == 1
            assert unmatched[0].status == UnmatchedStatus.PENDING

        # Pass 2: idempotent re-run -> 0 new offers, 0 new price_history points
        summary2 = pipeline.run(source_id=src)
        assert summary2.offers_inserted == 0
        assert summary2.price_history_points_added == 0

        # Pass 3: newer raw record with higher price updates offer and adds history point
        with session_factory() as session:
            session.add(
                RawServiceRecord(
                    id=raw_oak_new_price_id,
                    source_id=src,
                    source_url="https://lab.kz/oak",
                    record_fingerprint=f"fp5_{tag}",
                    clinic_name_raw="Лаб Тест",
                    city_raw="Алматы",
                    address_raw="ул. Абая 1",
                    service_name_raw=f"ОАК {tag}",
                    category_hint="лаборатория",
                    price_raw=Decimal("3400.00"),
                    currency_raw="KZT",
                    duration_days_raw=1,
                    raw_payload={},
                    first_seen_at=now + timedelta(minutes=10),
                    last_seen_at=now + timedelta(minutes=10),
                    parsed_at=now + timedelta(minutes=10),
                    last_run_id=run_id,
                )
            )
            session.commit()

        summary3 = pipeline.run(source_id=src)
        assert summary3.price_history_points_added == 1

        with session_factory() as session:
            oak_offer = session.scalar(
                select(ServiceOffer).where(
                    ServiceOffer.source_id == src,
                    ServiceOffer.service_id == oak_cat_id,
                    ServiceOffer.is_active.is_(True),
                )
            )
            assert oak_offer is not None
            assert oak_offer.price_kzt == Decimal("3400.00")

            hist_count = session.scalar(
                select(func.count())
                .select_from(PriceHistory)
                .where(
                    PriceHistory.clinic_id == oak_offer.clinic_id,
                    PriceHistory.service_id == oak_cat_id,
                )
            )
            assert hist_count == 2
    finally:
        with session_factory() as session:
            clinic_ids = list(
                session.scalars(select(Clinic.id).where(Clinic.source_id == src))
            )
            if clinic_ids:
                session.execute(delete(PriceHistory).where(PriceHistory.clinic_id.in_(clinic_ids)))
            session.execute(delete(UnmatchedService).where(UnmatchedService.source_id == src))
            session.execute(delete(ServiceOffer).where(ServiceOffer.source_id == src))
            session.execute(delete(Clinic).where(Clinic.source_id == src))
            session.execute(
                delete(ServiceCatalog).where(ServiceCatalog.id.in_([oak_cat_id, terapevt_cat_id]))
            )
            session.execute(delete(RawServiceRecord).where(RawServiceRecord.source_id == src))
            session.execute(delete(ScrapeRun).where(ScrapeRun.id == run_id))
            session.commit()
        engine.dispose()


def test_upsert_clinic_coalesces_null_address_with_enriched_address() -> None:
    settings = Settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    tag = uuid.uuid4().hex[:8]
    src = f"coalesce_{tag}"
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    cat_id = uuid.uuid4()

    try:
        with session_factory() as session:
            session.add_all(
                [
                    ServiceCatalog(
                        id=cat_id,
                        code=f"lab_coal_{tag}",
                        canonical_name=f"Тест {tag}",
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
                        id=uuid.uuid4(),
                        source_id=src,
                        source_url="https://lab.kz/1",
                        record_fingerprint=f"c1_{tag}",
                        clinic_name_raw="Сеть Лаб",
                        city_raw="Алматы",
                        address_raw=None,
                        service_name_raw=f"Тест {tag}",
                        category_hint="лаборатория",
                        price_raw=Decimal("2000.00"),
                        currency_raw="KZT",
                        raw_payload={},
                        first_seen_at=now - timedelta(hours=1),
                        last_seen_at=now - timedelta(hours=1),
                        parsed_at=now - timedelta(hours=1),
                        last_run_id=run_id,
                    ),
                    RawServiceRecord(
                        id=uuid.uuid4(),
                        source_id=src,
                        source_url="https://lab.kz/1",
                        record_fingerprint=f"c2_{tag}",
                        clinic_name_raw="Сеть Лаб",
                        city_raw="Алматы",
                        address_raw="ул. Майлина, 38а",
                        working_hours_raw="Пн-Пт 08:00-17:00",
                        latitude=43.34,
                        longitude=77.00,
                        service_name_raw=f"Тест {tag}",
                        category_hint="лаборатория",
                        price_raw=Decimal("2000.00"),
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
        pipeline = NormalizationPipeline(
            session_factory=session_factory, ingestion_service=ingestion_svc, settings=settings
        )
        pipeline.run(source_id=src)

        with session_factory() as session:
            clinics = list(session.scalars(select(Clinic).where(Clinic.source_id == src)))
            assert len(clinics) == 1
            assert clinics[0].address == "ул. Майлина, 38а"
            assert clinics[0].latitude == 43.34
    finally:
        with session_factory() as session:
            clinic_ids = list(session.scalars(select(Clinic.id).where(Clinic.source_id == src)))
            if clinic_ids:
                session.execute(delete(PriceHistory).where(PriceHistory.clinic_id.in_(clinic_ids)))
            session.execute(delete(UnmatchedService).where(UnmatchedService.source_id == src))
            session.execute(delete(ServiceOffer).where(ServiceOffer.source_id == src))
            session.execute(delete(Clinic).where(Clinic.source_id == src))
            session.execute(delete(ServiceCatalog).where(ServiceCatalog.id == cat_id))
            session.execute(delete(RawServiceRecord).where(RawServiceRecord.source_id == src))
            session.execute(delete(ScrapeRun).where(ScrapeRun.id == run_id))
            session.commit()
        engine.dispose()

"""Shared pytest fixtures and seed helpers for search-api integration tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.models import (
    RawServiceRecord,
    ScrapeError,
    ScrapeRun,
    ScrapeStatus,
    TriggerSource,
)
from app.main import create_app
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


@dataclass(frozen=True)
class SeededDataset:
    """IDs of seeded entities for deterministic API assertions."""

    oak_service_id: uuid.UUID
    vitd_service_id: uuid.UUID
    therapist_service_id: uuid.UUID
    uzi_service_id: uuid.UUID
    clinic_almaty_cheap_id: uuid.UUID
    clinic_almaty_near_id: uuid.UUID
    clinic_almaty_no_geo_id: uuid.UUID
    clinic_astana_id: uuid.UUID
    stale_offer_id: uuid.UUID
    unmatched_pending_id: uuid.UUID
    scrape_run_id: uuid.UUID


@pytest.fixture(scope="session")
def api_settings() -> Settings:
    """Return Settings configured for API tests."""
    settings = Settings(ADMIN_API_TOKEN="test-secret-token")
    assert "medprice_test" in settings.database_url, (
        f"Refusing to run API tests against non-test database: {settings.database_url}"
    )
    return settings


@pytest.fixture(scope="session")
def db_engine(api_settings: Settings) -> Iterator[Engine]:
    """Provide a session-scoped SQLAlchemy engine pointing to medprice_test."""
    engine = create_db_engine(api_settings.database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine: Engine) -> sessionmaker[Session]:
    """Clean test tables quickly via DELETE and provide a session factory."""
    factory = create_session_factory(db_engine)
    with factory() as session:
        session.execute(delete(PriceHistory))
        session.execute(delete(ServiceOffer))
        session.execute(delete(UnmatchedService))
        session.execute(delete(Clinic))
        session.execute(delete(ServiceCatalog))
        session.execute(delete(ScrapeError))
        session.execute(delete(RawServiceRecord))
        session.execute(delete(ScrapeRun))
        session.commit()
    return factory


@pytest.fixture
def app(
    api_settings: Settings,
    db_engine: Engine,
    db_session_factory: sessionmaker[Session],
) -> FastAPI:
    """Create a fresh FastAPI app wired to the clean test database."""
    _ = db_session_factory
    return create_app(settings=api_settings, engine=db_engine)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an AsyncClient speaking ASGI directly to the FastAPI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


def _make_raw(
    *,
    run_id: uuid.UUID,
    source_id: str,
    clinic_name: str,
    city: str,
    service_name: str,
    price: Decimal,
    parsed_at: datetime,
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    url: str = "https://example.kz/price",
) -> RawServiceRecord:
    rec_id = uuid.uuid4()
    return RawServiceRecord(
        id=rec_id,
        source_id=source_id,
        source_url=url,
        record_fingerprint=rec_id.hex,
        clinic_name_raw=clinic_name,
        city_raw=city,
        address_raw=address,
        latitude=lat,
        longitude=lng,
        service_name_raw=service_name,
        price_raw=price,
        currency_raw="KZT",
        raw_payload={},
        first_seen_at=parsed_at,
        last_seen_at=parsed_at,
        parsed_at=parsed_at,
        last_run_id=run_id,
    )


@pytest.fixture
def seeded_data(db_session_factory: sessionmaker[Session]) -> SeededDataset:
    """Populate realistic KZ medical clinics, services, offers, history, and unmatched items."""
    now = datetime.now(UTC)
    run_id = uuid.uuid4()

    oak_id = uuid.uuid4()
    vitd_id = uuid.uuid4()
    therapist_id = uuid.uuid4()
    uzi_id = uuid.uuid4()

    clinic_almaty_cheap_id = uuid.uuid4()
    clinic_almaty_near_id = uuid.uuid4()
    clinic_almaty_no_geo_id = uuid.uuid4()
    clinic_astana_id = uuid.uuid4()

    stale_offer_id = uuid.uuid4()
    unmatched_pending_id = uuid.uuid4()

    with db_session_factory() as session:
        session.add(
            ScrapeRun(
                id=run_id,
                source_id="kdlolymp",
                triggered_by=TriggerSource.MANUAL,
                status=ScrapeStatus.SUCCESS,
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
                records_fetched=10,
                records_inserted=10,
                records_updated=0,
                errors_count=1,
            )
        )
        session.add(
            ScrapeError(
                id=uuid.uuid4(),
                run_id=run_id,
                source_id="kdlolymp",
                url="https://www.kdlolymp.kz/pricelist/almaty",
                error_type="TimeoutError",
                message="Sample scrape warning",
                details={"retry": 1},
                occurred_at=now - timedelta(minutes=4),
            )
        )

        session.add_all(
            [
                ServiceCatalog(
                    id=oak_id,
                    code="lab_oak",
                    canonical_name="Общий анализ крови (ОАК)",
                    category=ServiceCategory.LAB,
                    synonyms=["ОАК", "CBC", "Клинический анализ крови"],
                    description="Базовый анализ крови",
                ),
                ServiceCatalog(
                    id=vitd_id,
                    code="lab_vit_d",
                    canonical_name="Витамин D (25-OH)",
                    category=ServiceCategory.LAB,
                    synonyms=["25-OH витамин D", "Vitamin D"],
                ),
                ServiceCatalog(
                    id=therapist_id,
                    code="doc_therapist",
                    canonical_name="Приём терапевта",
                    category=ServiceCategory.DOCTOR,
                    synonyms=["Консультация терапевта", "Терапевт"],
                ),
                ServiceCatalog(
                    id=uzi_id,
                    code="diag_uzi_abdomen",
                    canonical_name="УЗИ органов брюшной полости",
                    category=ServiceCategory.DIAGNOSTICS,
                    synonyms=["УЗИ ОБП"],
                ),
            ]
        )

        # Almaty coordinates reference: Republic Square ~ (43.238949, 76.945465)
        clinic_almaty_cheap = Clinic(
            id=clinic_almaty_cheap_id,
            source_id="kdlolymp",
            clinic_key="kdlolymp_almaty_far",
            clinic_name="КДЛ Олимп Алматы",
            city="Алматы",
            address="ул. Толе би, 120",
            phone="+7 (727) 259-79-69",
            working_hours="Пн-Сб 07:30-15:00",
            latitude=43.2567,
            longitude=76.9050,  # ~3.8 km from Republic Square
            rating=4.5,
            has_online_booking=True,
            website_url="https://www.kdlolymp.kz",
            updated_at=now,
        )
        clinic_almaty_near = Clinic(
            id=clinic_almaty_near_id,
            source_id="invivo",
            clinic_key="invivo_almaty_center",
            clinic_name="INVIVO Алматы Центр",
            city="Алматы",
            address="пр. Назарбаева, 187",
            phone="+7 (727) 339-04-80",
            working_hours="Пн-Вс 08:00-17:00",
            latitude=43.2380,
            longitude=76.9460,  # ~0.11 km from Republic Square
            rating=4.9,
            has_online_booking=False,
            website_url="https://invivo.kz",
            updated_at=now,
        )
        clinic_almaty_no_geo = Clinic(
            id=clinic_almaty_no_geo_id,
            source_id="doq",
            clinic_key="doq_almaty_nogeo",
            clinic_name="МедЦентр Здоровье",
            city="Алматы",
            address="ул. Абая, 55",
            phone="+7 (727) 200-00-01",
            working_hours="Пн-Пт 09:00-18:00",
            latitude=None,
            longitude=None,
            rating=4.2,
            has_online_booking=True,
            website_url="https://doq.kz/almaty/clinic/zdorovie",
            updated_at=now,
        )
        clinic_astana = Clinic(
            id=clinic_astana_id,
            source_id="kdlolymp",
            clinic_key="kdlolymp_astana",
            clinic_name="КДЛ Олимп Астана",
            city="Астана",
            address="пр. Кабанбай батыра, 11",
            phone="+7 (7172) 59-79-69",
            working_hours="Пн-Сб 07:30-15:00",
            latitude=51.1282,
            longitude=71.4304,
            rating=4.7,
            has_online_booking=True,
            website_url="https://www.kdlolymp.kz",
            updated_at=now,
        )
        session.add_all(
            [clinic_almaty_cheap, clinic_almaty_near, clinic_almaty_no_geo, clinic_astana]
        )
        session.flush()

        raw_entries = [
            _make_raw(
                run_id=run_id,
                source_id="kdlolymp",
                clinic_name="КДЛ Олимп Алматы",
                city="Алматы",
                service_name="ОАК расширенный",
                price=Decimal("2200.00"),
                parsed_at=now - timedelta(hours=4),
                url="https://www.kdlolymp.kz/pricelist/almaty",
            ),
            _make_raw(
                run_id=run_id,
                source_id="invivo",
                clinic_name="INVIVO Алматы Центр",
                city="Алматы",
                service_name="Общий анализ крови с СОЭ",
                price=Decimal("2850.50"),
                parsed_at=now - timedelta(hours=1),
                url="https://invivo.kz/ru/almaty/analyzes/oak",
            ),
            _make_raw(
                run_id=run_id,
                source_id="doq",
                clinic_name="МедЦентр Здоровье",
                city="Алматы",
                service_name="Приём врача-терапевта первичный",
                price=Decimal("9000.00"),
                parsed_at=now - timedelta(hours=2),
                url="https://doq.kz/almaty/doctor/therapist",
            ),
            _make_raw(
                run_id=run_id,
                source_id="kdlolymp",
                clinic_name="КДЛ Олимп Астана",
                city="Астана",
                service_name="ОАК стандарт",
                price=Decimal("2400.00"),
                parsed_at=now - timedelta(hours=3),
                url="https://www.kdlolymp.kz/pricelist/astana",
            ),
            _make_raw(
                run_id=run_id,
                source_id="kdlolymp",
                clinic_name="КДЛ Олимп Алматы",
                city="Алматы",
                service_name="Витамин D 25-OH",
                price=Decimal("8500.00"),
                parsed_at=now - timedelta(days=2),
                url="https://www.kdlolymp.kz/pricelist/almaty",
            ),
            _make_raw(
                run_id=run_id,
                source_id="invivo",
                clinic_name="INVIVO Алматы Центр",
                city="Алматы",
                service_name="25-OH Vitamin D",
                price=Decimal("7900.00"),
                parsed_at=now - timedelta(days=1),
                url="https://invivo.kz/ru/almaty/analyzes/vitd",
            ),
            # Stale raw record (31 days old) still marked is_active=True in DB to test guard!
            _make_raw(
                run_id=run_id,
                source_id="doq",
                clinic_name="МедЦентр Здоровье",
                city="Алматы",
                service_name="УЗИ брюшной полости старое",
                price=Decimal("5000.00"),
                parsed_at=now - timedelta(days=31),
                url="https://doq.kz/almaty/uzi-old",
            ),
            # Unmatched pending raw record
            _make_raw(
                run_id=run_id,
                source_id="kdlolymp",
                clinic_name="КДЛ Олимп Алматы",
                city="Алматы",
                service_name="Экспресс-скрининг крови VIP",
                price=Decimal("4100.00"),
                parsed_at=now - timedelta(hours=1),
                address="ул. Толе би, 120",
                lat=43.2567,
                lng=76.9050,
                url="https://www.kdlolymp.kz/pricelist/almaty#vip",
            ),
        ]
        session.add_all(raw_entries)
        session.flush()

        offer_oak_cheap = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_almaty_cheap_id,
            service_id=oak_id,
            raw_record_id=raw_entries[0].id,
            source_id="kdlolymp",
            source_url=raw_entries[0].source_url,
            service_name_raw=raw_entries[0].service_name_raw,
            service_name_norm="Общий анализ крови (ОАК)",
            category=ServiceCategory.LAB,
            price_kzt=Decimal("2200.00"),
            original_price=Decimal("2200.00"),
            currency=CurrencyCode.KZT,
            duration_days=1,
            match_method=MatchMethod.EXACT,
            match_score=100.0,
            parsed_at=raw_entries[0].parsed_at,
            is_active=True,
        )
        offer_oak_near = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_almaty_near_id,
            service_id=oak_id,
            raw_record_id=raw_entries[1].id,
            source_id="invivo",
            source_url=raw_entries[1].source_url,
            service_name_raw=raw_entries[1].service_name_raw,
            service_name_norm="Общий анализ крови (ОАК)",
            category=ServiceCategory.LAB,
            price_kzt=Decimal("2850.50"),
            original_price=Decimal("2850.50"),
            currency=CurrencyCode.KZT,
            duration_days=1,
            match_method=MatchMethod.SYNONYM,
            match_score=100.0,
            parsed_at=raw_entries[1].parsed_at,
            is_active=True,
        )
        offer_therapist = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_almaty_no_geo_id,
            service_id=therapist_id,
            raw_record_id=raw_entries[2].id,
            source_id="doq",
            source_url=raw_entries[2].source_url,
            service_name_raw=raw_entries[2].service_name_raw,
            service_name_norm="Приём терапевта",
            category=ServiceCategory.DOCTOR,
            price_kzt=Decimal("9000.00"),
            original_price=Decimal("9000.00"),
            currency=CurrencyCode.KZT,
            duration_days=0,
            match_method=MatchMethod.SYNONYM,
            match_score=100.0,
            parsed_at=raw_entries[2].parsed_at,
            is_active=True,
        )
        offer_oak_astana = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_astana_id,
            service_id=oak_id,
            raw_record_id=raw_entries[3].id,
            source_id="kdlolymp",
            source_url=raw_entries[3].source_url,
            service_name_raw=raw_entries[3].service_name_raw,
            service_name_norm="Общий анализ крови (ОАК)",
            category=ServiceCategory.LAB,
            price_kzt=Decimal("2400.00"),
            original_price=Decimal("2400.00"),
            currency=CurrencyCode.KZT,
            duration_days=1,
            match_method=MatchMethod.EXACT,
            match_score=100.0,
            parsed_at=raw_entries[3].parsed_at,
            is_active=True,
        )
        offer_vitd_olymp = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_almaty_cheap_id,
            service_id=vitd_id,
            raw_record_id=raw_entries[4].id,
            source_id="kdlolymp",
            source_url=raw_entries[4].source_url,
            service_name_raw=raw_entries[4].service_name_raw,
            service_name_norm="Витамин D (25-OH)",
            category=ServiceCategory.LAB,
            price_kzt=Decimal("8500.00"),
            original_price=Decimal("8500.00"),
            currency=CurrencyCode.KZT,
            duration_days=2,
            match_method=MatchMethod.EXACT,
            match_score=100.0,
            parsed_at=raw_entries[4].parsed_at,
            is_active=True,
        )
        offer_vitd_invivo = ServiceOffer(
            id=uuid.uuid4(),
            clinic_id=clinic_almaty_near_id,
            service_id=vitd_id,
            raw_record_id=raw_entries[5].id,
            source_id="invivo",
            source_url=raw_entries[5].source_url,
            service_name_raw=raw_entries[5].service_name_raw,
            service_name_norm="Витамин D (25-OH)",
            category=ServiceCategory.LAB,
            price_kzt=Decimal("7900.00"),
            original_price=Decimal("7900.00"),
            currency=CurrencyCode.KZT,
            duration_days=1,
            match_method=MatchMethod.SYNONYM,
            match_score=100.0,
            parsed_at=raw_entries[5].parsed_at,
            is_active=True,
        )
        offer_stale = ServiceOffer(
            id=stale_offer_id,
            clinic_id=clinic_almaty_no_geo_id,
            service_id=uzi_id,
            raw_record_id=raw_entries[6].id,
            source_id="doq",
            source_url=raw_entries[6].source_url,
            service_name_raw=raw_entries[6].service_name_raw,
            service_name_norm="УЗИ органов брюшной полости",
            category=ServiceCategory.DIAGNOSTICS,
            price_kzt=Decimal("5000.00"),
            original_price=Decimal("5000.00"),
            currency=CurrencyCode.KZT,
            duration_days=0,
            match_method=MatchMethod.EXACT,
            match_score=100.0,
            parsed_at=raw_entries[6].parsed_at,  # 31 days old!
            is_active=True,  # Intentionally True to verify hard API freshness guard
        )
        session.add_all(
            [
                offer_oak_cheap,
                offer_oak_near,
                offer_therapist,
                offer_oak_astana,
                offer_vitd_olymp,
                offer_vitd_invivo,
                offer_stale,
            ]
        )
        session.flush()

        session.add_all(
            [
                PriceHistory(
                    id=uuid.uuid4(),
                    clinic_id=clinic_almaty_cheap_id,
                    service_id=oak_id,
                    offer_id=offer_oak_cheap.id,
                    price_kzt=Decimal("2000.00"),
                    recorded_at=now - timedelta(days=20),
                ),
                PriceHistory(
                    id=uuid.uuid4(),
                    clinic_id=clinic_almaty_cheap_id,
                    service_id=oak_id,
                    offer_id=offer_oak_cheap.id,
                    price_kzt=Decimal("2200.00"),
                    recorded_at=now - timedelta(hours=4),
                ),
                PriceHistory(
                    id=uuid.uuid4(),
                    clinic_id=clinic_astana_id,
                    service_id=oak_id,
                    offer_id=offer_oak_astana.id,
                    price_kzt=Decimal("2400.00"),
                    recorded_at=now - timedelta(days=5),
                ),
            ]
        )

        session.add(
            UnmatchedService(
                id=unmatched_pending_id,
                raw_record_id=raw_entries[7].id,
                source_id="kdlolymp",
                clinic_name_raw="КДЛ Олимп Алматы",
                city_raw="Алматы",
                service_name_raw=raw_entries[7].service_name_raw,
                category_hint="Анализы",
                price_kzt=Decimal("4100.00"),
                suggested_service_id=oak_id,
                suggested_score=74.5,
                status=UnmatchedStatus.PENDING,
            )
        )
        session.commit()

    return SeededDataset(
        oak_service_id=oak_id,
        vitd_service_id=vitd_id,
        therapist_service_id=therapist_id,
        uzi_service_id=uzi_id,
        clinic_almaty_cheap_id=clinic_almaty_cheap_id,
        clinic_almaty_near_id=clinic_almaty_near_id,
        clinic_almaty_no_geo_id=clinic_almaty_no_geo_id,
        clinic_astana_id=clinic_astana_id,
        stale_offer_id=stale_offer_id,
        unmatched_pending_id=unmatched_pending_id,
        scrape_run_id=run_id,
    )

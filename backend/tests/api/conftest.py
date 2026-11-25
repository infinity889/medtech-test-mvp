"""Shared pytest fixtures for search-api integration tests against PostgreSQL."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.models import RawServiceRecord, ScrapeError, ScrapeRun
from app.main import create_app
from app.normalization.models import (
    Clinic,
    PriceHistory,
    ServiceCatalog,
    ServiceOffer,
    UnmatchedService,
)


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

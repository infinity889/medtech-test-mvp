"""FastAPI application entry point for MedServicePrice.kz Search & Comparison API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from app.api.errors import register_error_handlers
from app.api.query_service import SearchQueryService
from app.api.routes import health as health_routes
from app.api.routes import offers as offers_routes
from app.api.routes import services as services_routes
from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.registry import default_registry
from app.ingestion.service import IngestionService
from app.normalization.service import NormalizationService

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    resolved_settings = settings or Settings()
    owns_engine = engine is None
    resolved_engine = (
        engine if engine is not None else create_db_engine(resolved_settings.database_url)
    )
    session_factory = create_session_factory(resolved_engine)

    ingestion_service = IngestionService(
        session_factory=session_factory,
        registry=default_registry,
        settings=resolved_settings,
    )
    normalization_service = NormalizationService(
        session_factory=session_factory,
        ingestion_service=ingestion_service,
        settings=resolved_settings,
    )
    query_service = SearchQueryService(
        session_factory=session_factory,
        settings=resolved_settings,
    )

    if resolved_settings.admin_api_token == "dev-admin-token":
        logger.warning(
            "ADMIN_API_TOKEN is using the default dev value ('dev-admin-token'). "
            "Set a strong token in .env before public deployment."
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_engine:
                resolved_engine.dispose()

    application = FastAPI(
        title="MedServicePrice.kz API",
        version="0.1.0",
        description=(
            "Search and price comparison REST API for medical services in Kazakhstan "
            "(lab tests, doctor visits, diagnostics, procedures)."
        ),
        lifespan=lifespan,
    )

    application.state.settings = resolved_settings
    application.state.engine = resolved_engine
    application.state.session_factory = session_factory
    application.state.ingestion_service = ingestion_service
    application.state.normalization_service = normalization_service
    application.state.query_service = query_service
    application.state.scrape_lock = asyncio.Lock()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(application)

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(health_routes.router)
    api_v1.include_router(services_routes.router)
    api_v1.include_router(offers_routes.router)
    application.include_router(api_v1)

    return application


app = create_app()

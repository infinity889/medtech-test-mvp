"""FastAPI dependency injection providers and X-Admin-Token authentication."""

from __future__ import annotations

import asyncio
import hmac
from typing import Annotated, cast

from fastapi import Depends, Header, Request, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import APIError
from app.core.config import Settings
from app.ingestion.service import IngestionService
from app.normalization.service import NormalizationService


def get_app_settings(request: Request) -> Settings:
    """Return runtime Settings attached to FastAPI app state."""
    return cast(Settings, request.app.state.settings)


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return SQLAlchemy session factory attached to FastAPI app state."""
    return cast(sessionmaker[Session], request.app.state.session_factory)


def get_ingestion_service(request: Request) -> IngestionService:
    """Return IngestionService facade attached to FastAPI app state."""
    return cast(IngestionService, request.app.state.ingestion_service)


def get_normalization_service(request: Request) -> NormalizationService:
    """Return NormalizationService facade attached to FastAPI app state."""
    return cast(NormalizationService, request.app.state.normalization_service)


def get_scrape_lock(request: Request) -> asyncio.Lock:
    """Return process-level lock preventing concurrent manual scrape runs."""
    return cast(asyncio.Lock, request.app.state.scrape_lock)


def require_admin_token(
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Validate X-Admin-Token using constant-time comparison."""
    if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.admin_api_token):
        raise APIError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or missing X-Admin-Token header",
        )

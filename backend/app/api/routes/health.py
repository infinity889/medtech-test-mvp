"""Health check and filter metadata routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session_factory
from app.api.errors import APIError
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> HealthResponse:
    """Verify API liveness and PostgreSQL connectivity."""
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Database connection unavailable",
        ) from exc
    return HealthResponse(status="ok", database="ok")

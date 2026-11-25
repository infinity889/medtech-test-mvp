"""Unified API error type and FastAPI exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_HTTP_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


class APIError(Exception):
    """Domain/API exception serialized into the unified APIError JSON envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Build standard JSON error body matching SPEC-search-api.md."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }


def _sanitize_validation_errors(raw_errors: Any) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for err in raw_errors:
        item: dict[str, Any] = {
            "loc": list(err.get("loc", ())),
            "msg": str(err.get("msg", "Invalid value")),
            "type": str(err.get("type", "value_error")),
        }
        sanitized.append(item)
    return sanitized


def register_error_handlers(app: FastAPI) -> None:
    """Attach unified JSON error handlers to a FastAPI application."""

    @app.exception_handler(APIError)
    async def _handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_payload(
                "VALIDATION_ERROR",
                "Invalid request parameters",
                _sanitize_validation_errors(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = str(exc.detail) if exc.detail else code
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, message, None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception in API request: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("INTERNAL_ERROR", "Internal server error", None),
        )

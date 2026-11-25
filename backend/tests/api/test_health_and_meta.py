"""Tests for /api/v1/health, CORS preflight, OpenAPI schema, and unified APIError envelope."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Query


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_unknown_route_returns_unified_api_error(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_validation_and_internal_errors_use_unified_envelope(
    app: FastAPI,
) -> None:
    @app.get("/api/v1/_test-validation")
    def _test_validation(limit: int = Query(ge=1, le=10)) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/api/v1/_test-boom")
    def _test_boom() -> dict[str, str]:
        raise RuntimeError("sensitive internal secret database_url=postgres://pw")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad_param = await client.get("/api/v1/_test-validation?limit=999")
        assert bad_param.status_code == 422
        val_body = bad_param.json()
        assert val_body["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(val_body["error"]["details"], list)

        boom = await client.get("/api/v1/_test-boom")
        assert boom.status_code == 500
        boom_body = boom.json()
        assert boom_body["error"]["code"] == "INTERNAL_ERROR"
        assert "postgres://" not in boom_body["error"]["message"]
        assert boom_body["error"]["details"] is None


@pytest.mark.asyncio
async def test_cors_preflight_allows_vite_dev_origin(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Admin-Token",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_openapi_schema_is_exposed(client: httpx.AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "MedServicePrice.kz API"
    assert "/api/v1/health" in schema["paths"]

"""Tests for X-Admin-Token protected /api/v1/admin/* endpoints and 409 scrape lock."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.ingestion.models import ScrapeStatus, TriggerSource
from app.ingestion.schemas import ScrapeRunDTO
from tests.api.conftest import SeededDataset

ADMIN_HEADERS = {"X-Admin-Token": "test-secret-token"}


@pytest.mark.asyncio
async def test_admin_endpoints_require_valid_token(client: httpx.AsyncClient) -> None:
    no_header = await client.get("/api/v1/admin/stats")
    assert no_header.status_code == 401
    assert no_header.json()["error"]["code"] == "UNAUTHORIZED"

    wrong_header = await client.get(
        "/api/v1/admin/sources", headers={"X-Admin-Token": "wrong-token"}
    )
    assert wrong_header.status_code == 401
    assert wrong_header.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_admin_read_endpoints_delegate_to_services(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    sources_res = await client.get("/api/v1/admin/sources", headers=ADMIN_HEADERS)
    assert sources_res.status_code == 200
    source_ids = {item["source_id"] for item in sources_res.json()}
    assert {"kdlolymp", "invivo", "doq"}.issubset(source_ids)

    runs_res = await client.get("/api/v1/admin/scrape-runs", headers=ADMIN_HEADERS)
    assert runs_res.status_code == 200
    assert len(runs_res.json()) == 1
    assert runs_res.json()[0]["id"] == str(seeded_data.scrape_run_id)

    errors_res = await client.get(
        "/api/v1/admin/scrape-errors",
        params={"run_id": str(seeded_data.scrape_run_id)},
        headers=ADMIN_HEADERS,
    )
    assert errors_res.status_code == 200
    assert len(errors_res.json()) == 1
    assert errors_res.json()[0]["error_type"] == "TimeoutError"

    stats_res = await client.get("/api/v1/admin/stats", headers=ADMIN_HEADERS)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["catalog_services"] == 4
    assert stats["clinics"] == 4
    assert stats["unmatched_pending"] == 1


@pytest.mark.asyncio
async def test_admin_unmatched_list_resolve_creates_live_offer_and_ignore(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    list_res = await client.get("/api/v1/admin/unmatched", headers=ADMIN_HEADERS)
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["pagination"]["total_items"] == 1
    item = body["items"][0]
    assert item["id"] == str(seeded_data.unmatched_pending_id)
    assert item["suggested_service_name"] == "Общий анализ крови (ОАК)"

    # Resolve to UZI service (which had 0 fresh offers before!)
    resolve_res = await client.post(
        f"/api/v1/admin/unmatched/{seeded_data.unmatched_pending_id}/resolve",
        json={"service_id": str(seeded_data.uzi_service_id), "add_as_synonym": True},
        headers=ADMIN_HEADERS,
    )
    assert resolve_res.status_code == 200
    resolved = resolve_res.json()
    assert resolved["service_id"] == str(seeded_data.uzi_service_id)
    assert resolved["price_kzt"] == 4100.0
    assert resolved["is_active"] is True

    # Newly resolved offer must immediately appear in public /api/v1/offers!
    public_offers = await client.get(
        "/api/v1/offers", params={"service_id": str(seeded_data.uzi_service_id)}
    )
    assert public_offers.status_code == 200
    assert public_offers.json()["pagination"]["total_items"] == 1
    assert public_offers.json()["items"][0]["price_kzt"] == 4100.0

    # Pending queue is now empty
    after_pending = await client.get(
        "/api/v1/admin/unmatched", params={"status": "pending"}, headers=ADMIN_HEADERS
    )
    assert after_pending.json()["pagination"]["total_items"] == 0

    # Ignoring a non-existent ID returns 404
    missing_ignore = await client.post(
        f"/api/v1/admin/unmatched/{uuid.uuid4()}/ignore", headers=ADMIN_HEADERS
    )
    assert missing_ignore.status_code == 404
    assert missing_ignore.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_admin_ignore_unmatched_moves_item_to_ignored(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    res = await client.post(
        f"/api/v1/admin/unmatched/{seeded_data.unmatched_pending_id}/ignore",
        headers=ADMIN_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"

    pending = await client.get(
        "/api/v1/admin/unmatched", params={"status": "pending"}, headers=ADMIN_HEADERS
    )
    assert pending.json()["pagination"]["total_items"] == 0

    ignored = await client.get(
        "/api/v1/admin/unmatched", params={"status": "ignored"}, headers=ADMIN_HEADERS
    )
    assert ignored.json()["pagination"]["total_items"] == 1


@pytest.mark.asyncio
async def test_admin_trigger_scrape_runs_and_returns_409_when_locked(
    app: FastAPI,
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    _ = seeded_data
    started = asyncio.Event()
    release = asyncio.Event()

    async def _fake_trigger_run(
        source_ids: list[str] | None = None,
        *,
        triggered_by: str = "manual",
        limit: int | None = None,
    ) -> list[ScrapeRunDTO]:
        _ = (source_ids, triggered_by, limit)
        started.set()
        await release.wait()
        now = datetime.now(UTC)
        return [
            ScrapeRunDTO(
                id=uuid.uuid4(),
                source_id="kdlolymp",
                triggered_by=TriggerSource.MANUAL,
                status=ScrapeStatus.SUCCESS,
                started_at=now,
                finished_at=now,
                records_fetched=5,
                records_inserted=5,
                records_updated=0,
                errors_count=0,
            )
        ]

    app.state.ingestion_service.trigger_run = _fake_trigger_run

    first_task = asyncio.create_task(
        client.post(
            "/api/v1/admin/scrape-runs",
            json={"source_ids": ["kdlolymp"], "limit": 5, "normalize": False},
            headers=ADMIN_HEADERS,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2.0)

    # Concurrent second call must receive 409 SCRAPE_IN_PROGRESS immediately
    second_res = await client.post(
        "/api/v1/admin/scrape-runs",
        json={"source_ids": ["kdlolymp"], "limit": 5, "normalize": False},
        headers=ADMIN_HEADERS,
    )
    assert second_res.status_code == 409
    assert second_res.json()["error"]["code"] == "SCRAPE_IN_PROGRESS"

    release.set()
    first_res = await first_task
    assert first_res.status_code == 200
    body = first_res.json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["source_id"] == "kdlolymp"
    assert body["normalization_summary"] is None

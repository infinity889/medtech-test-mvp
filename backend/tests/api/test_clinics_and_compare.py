"""Tests for /api/v1/clinics, /api/v1/clinics/{id}, /api/v1/compare, and /price-history."""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.api.conftest import SeededDataset


@pytest.mark.asyncio
async def test_list_clinics_supports_has_geo_city_and_search(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    geo_res = await client.get("/api/v1/clinics", params={"has_geo": True})
    assert geo_res.status_code == 200
    geo_body = geo_res.json()
    assert geo_body["pagination"]["total_items"] == 3
    for clinic in geo_body["items"]:
        assert clinic["latitude"] is not None
        assert clinic["longitude"] is not None
        assert clinic["route_2gis_url"].startswith("https://2gis.kz/geo/")

    # Search clinic without GPS -> address fallback route URLs
    nogeo_res = await client.get("/api/v1/clinics", params={"has_geo": False, "city": "Алматы"})
    assert nogeo_res.status_code == 200
    nogeo_items = nogeo_res.json()["items"]
    assert len(nogeo_items) == 1
    assert nogeo_items[0]["id"] == str(seeded_data.clinic_almaty_no_geo_id)
    assert nogeo_items[0]["offers_count"] == 1  # stale UZI offer excluded
    assert nogeo_items[0]["route_2gis_url"].startswith("https://2gis.kz/search/")
    assert "destination=" in nogeo_items[0]["route_google_maps_url"]


@pytest.mark.asyncio
async def test_clinic_detail_returns_fresh_offers_and_404_for_unknown(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    res = await client.get(f"/api/v1/clinics/{seeded_data.clinic_almaty_no_geo_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["clinic_name"] == "МедЦентр Здоровье"
    assert detail["working_hours"] == "Пн-Пт 09:00-18:00"
    # Stale 31-day offer must NOT be returned on clinic card either!
    offer_ids = {item["offer_id"] for item in detail["offers"]}
    assert str(seeded_data.stale_offer_id) not in offer_ids
    assert len(detail["offers"]) == 1
    assert detail["offers"][0]["service_code"] == "doc_therapist"

    missing = await client.get(f"/api/v1/clinics/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_compare_matrix_highlights_cheapest_and_validates_bounds(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    # CSV format with 2 clinics
    c1 = str(seeded_data.clinic_almaty_cheap_id)
    c2 = str(seeded_data.clinic_almaty_near_id)
    res = await client.get("/api/v1/compare", params={"clinic_ids": f"{c1},{c2}"})
    assert res.status_code == 200
    body = res.json()
    assert [c["id"] for c in body["clinics"]] == [c1, c2]
    assert len(body["rows"]) == 2

    rows_by_code = {row["service_code"]: row for row in body["rows"]}
    # OAK: KDL Olymp (2200) < INVIVO (2850.5)
    oak_row = rows_by_code["lab_oak"]
    assert oak_row["cheapest_clinic_id"] == c1
    assert oak_row["cells"][c1]["price_kzt"] == 2200.0
    assert oak_row["cells"][c2]["price_kzt"] == 2850.5

    # Vitamin D: INVIVO (7900) < KDL Olymp (8500)
    vitd_row = rows_by_code["lab_vit_d"]
    assert vitd_row["cheapest_clinic_id"] == c2
    assert vitd_row["cells"][c1]["price_kzt"] == 8500.0
    assert vitd_row["cells"][c2]["price_kzt"] == 7900.0

    # Validation: < 2 clinics -> 422
    too_few = await client.get("/api/v1/compare", params={"clinic_ids": c1})
    assert too_few.status_code == 422
    assert too_few.json()["error"]["code"] == "VALIDATION_ERROR"

    # Validation: > 5 clinics -> 422
    six_ids = ",".join(str(uuid.uuid4()) for _ in range(6))
    too_many = await client.get("/api/v1/compare", params={"clinic_ids": six_ids})
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "VALIDATION_ERROR"

    # Non-existent clinic -> 404
    missing_clinic = await client.get(
        "/api/v1/compare", params={"clinic_ids": f"{c1},{uuid.uuid4()}"}
    )
    assert missing_clinic.status_code == 404
    assert missing_clinic.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_service_price_history_returns_chronological_series(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    res = await client.get(
        f"/api/v1/services/{seeded_data.oak_service_id}/price-history",
        params={"days": 30},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["service_code"] == "lab_oak"
    assert [p["price_kzt"] for p in body["points"]] == [2000.0, 2400.0, 2200.0]
    assert body["points"][0]["clinic_name"] == "КДЛ Олимп Алматы"
    assert body["points"][1]["city"] == "Астана"

    # Filter by city
    almaty_only = await client.get(
        f"/api/v1/services/{seeded_data.oak_service_id}/price-history",
        params={"city": "Алматы", "days": 30},
    )
    assert almaty_only.status_code == 200
    assert [p["price_kzt"] for p in almaty_only.json()["points"]] == [2000.0, 2200.0]

    # Unknown service -> 404
    missing = await client.get(f"/api/v1/services/{uuid.uuid4()}/price-history")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

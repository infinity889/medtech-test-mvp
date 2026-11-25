"""Tests for /api/v1/meta/filters, /api/v1/services/autocomplete, and /api/v1/offers."""

from __future__ import annotations

import httpx
import pytest

from tests.api.conftest import SeededDataset


@pytest.mark.asyncio
async def test_meta_filters_aggregates_fresh_active_offers_only(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    _ = seeded_data
    response = await client.get("/api/v1/meta/filters")
    assert response.status_code == 200
    body = response.json()

    cities_by_name = {item["name"]: item for item in body["cities"]}
    assert cities_by_name["Алматы"]["offers_count"] == 5  # stale 31d offer excluded
    assert cities_by_name["Алматы"]["clinics_count"] == 3
    assert cities_by_name["Астана"]["offers_count"] == 1
    assert cities_by_name["Астана"]["clinics_count"] == 1

    categories = {item["code"]: item for item in body["categories"]}
    assert categories["lab"]["label_ru"] == "Анализы"
    assert categories["lab"]["offers_count"] == 5
    assert categories["doctor"]["offers_count"] == 1
    assert categories["diagnostics"]["offers_count"] == 0  # stale UZI excluded!
    assert body["price_min_kzt"] == 2200.0
    assert body["price_max_kzt"] == 9000.0
    assert body["last_updated_at"] is not None


@pytest.mark.asyncio
async def test_autocomplete_matches_russian_and_english_synonyms(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    for query in ("ОАК", "CBC", "общий анализ"):
        response = await client.get("/api/v1/services/autocomplete", params={"q": query})
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        top = items[0]
        assert top["service_id"] == str(seeded_data.oak_service_id)
        assert top["code"] == "lab_oak"
        assert top["offers_count"] == 3
        assert top["min_price_kzt"] == 2200.0

    # City filter narrows offers_count and min_price_kzt
    astana_res = await client.get(
        "/api/v1/services/autocomplete", params={"q": "ОАК", "city": "Астана"}
    )
    assert astana_res.status_code == 200
    astana_top = astana_res.json()["items"][0]
    assert astana_top["offers_count"] == 1
    assert astana_top["min_price_kzt"] == 2400.0


@pytest.mark.asyncio
async def test_offers_search_filters_sorting_freshness_and_pagination(
    client: httpx.AsyncClient,
    seeded_data: SeededDataset,
) -> None:
    # 1. Default search excludes 31-day-old stale offer even though is_active=True in DB
    all_res = await client.get("/api/v1/offers", params={"page_size": 50})
    assert all_res.status_code == 200
    all_body = all_res.json()
    offer_ids = {item["offer_id"] for item in all_body["items"]}
    assert str(seeded_data.stale_offer_id) not in offer_ids
    assert all_body["pagination"]["total_items"] == 6
    assert all_body["summary"]["min_price_kzt"] == 2200.0
    assert all_body["summary"]["max_price_kzt"] == 9000.0

    # 2. Search by synonym 'CBC' + city + price_asc
    oak_almaty = await client.get(
        "/api/v1/offers",
        params={"q": "CBC", "city": "Алматы", "sort_by": "price_asc"},
    )
    assert oak_almaty.status_code == 200
    oak_body = oak_almaty.json()
    assert [item["price_kzt"] for item in oak_body["items"]] == [2200.0, 2850.5]
    assert oak_body["items"][0]["clinic"]["route_2gis_url"].startswith("https://2gis.kz/geo/")
    assert oak_body["items"][0]["clinic"]["route_google_maps_url"].startswith(
        "https://www.google.com/maps/dir/"
    )

    # 3. Sort by distance_asc from Almaty Republic Square (43.238949, 76.945465)
    # INVIVO (~0.11 km) must come before KDL Olymp (~3.8 km), and no-geo clinic must be last
    dist_res = await client.get(
        "/api/v1/offers",
        params={
            "city": "Алматы",
            "lat": 43.238949,
            "lng": 76.945465,
            "sort_by": "distance_asc",
        },
    )
    assert dist_res.status_code == 200
    dist_items = dist_res.json()["items"]
    assert dist_items[0]["clinic"]["id"] == str(seeded_data.clinic_almaty_near_id)
    assert dist_items[0]["distance_km"] is not None
    assert dist_items[0]["distance_km"] < 0.5
    assert dist_items[-1]["clinic"]["id"] == str(seeded_data.clinic_almaty_no_geo_id)
    assert dist_items[-1]["distance_km"] is None

    # 4. Sort by updated_desc & rating_desc & price_desc
    updated_res = await client.get(
        "/api/v1/offers",
        params={"service_id": str(seeded_data.oak_service_id), "sort_by": "updated_desc"},
    )
    assert updated_res.json()["items"][0]["clinic"]["id"] == str(seeded_data.clinic_almaty_near_id)

    rating_res = await client.get(
        "/api/v1/offers",
        params={"service_id": str(seeded_data.oak_service_id), "sort_by": "rating_desc"},
    )
    assert rating_res.json()["items"][0]["clinic"]["rating"] == 4.9

    price_desc = await client.get(
        "/api/v1/offers",
        params={"service_id": str(seeded_data.oak_service_id), "sort_by": "price_desc"},
    )
    assert [item["price_kzt"] for item in price_desc.json()["items"]] == [2850.5, 2400.0, 2200.0]

    # 5. Filters: min_price, max_price, min_rating, online_booking, category
    filtered = await client.get(
        "/api/v1/offers",
        params={
            "city": "Алматы",
            "category": "lab",
            "min_price": "2000",
            "max_price": "3000",
            "min_rating": 4.4,
            "online_booking": True,
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total_items"] == 1
    assert filtered.json()["items"][0]["clinic"]["id"] == str(seeded_data.clinic_almaty_cheap_id)

    # 6. Pagination
    page2 = await client.get("/api/v1/offers", params={"page": 2, "page_size": 2})
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 2
    assert page2.json()["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total_items": 6,
        "total_pages": 3,
    }


@pytest.mark.asyncio
async def test_offers_rejects_invalid_price_and_geo_combinations(
    client: httpx.AsyncClient,
) -> None:
    bad_price = await client.get("/api/v1/offers", params={"min_price": 5000, "max_price": 2000})
    assert bad_price.status_code == 422
    assert bad_price.json()["error"]["code"] == "VALIDATION_ERROR"

    half_geo = await client.get("/api/v1/offers", params={"lat": 43.23})
    assert half_geo.status_code == 422
    assert half_geo.json()["error"]["code"] == "VALIDATION_ERROR"

    dist_no_geo = await client.get("/api/v1/offers", params={"sort_by": "distance_asc"})
    assert dist_no_geo.status_code == 422
    assert dist_no_geo.json()["error"]["code"] == "VALIDATION_ERROR"

"""Offline contract tests for DoqAdapter using a saved Next.js RSC fixture."""

from decimal import Decimal
from pathlib import Path

import httpx
import respx

from app.ingestion.adapters.doq import DoqAdapter
from app.ingestion.adapters.registry import default_registry
from app.ingestion.http_client import PoliteHttpClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "doq_almaty_terapevt.html"


@respx.mock
async def test_doq_adapter_parses_rsc_fixture_with_geo_rating_and_prices() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://doq.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /appointments/*\n")
    )
    respx.get("https://doq.kz/doctors/almaty/terapevt").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = DoqAdapter(
        cities=[("almaty", "Алматы")],
        listing_slugs=[("terapevt", "приём врача")],
    )
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client):
            records.append(rec)

    assert len(records) == 2

    first = records[0]
    assert first.clinic_name_raw == "AQmed в Аксай 2"
    assert first.city_raw == "Алматы"
    assert first.address_raw == "мкр. Аксай-2, 44А"
    assert first.phone_raw == "+77070000022"
    assert first.latitude == 43.233918
    assert first.longitude == 76.835224
    assert first.clinic_rating_raw == 4.56
    assert first.has_online_booking is True
    assert first.service_name_raw == "Приём терапевта"
    assert first.category_hint == "приём врача"
    assert first.price_raw == Decimal("3500")
    assert first.currency_raw == "KZT"
    assert str(first.source_url) == "https://doq.kz/clinics/almaty/aqmed"

    second = records[1]
    assert second.service_name_raw == "УЗИ органов брюшной полости"
    assert second.category_hint == "диагностика"
    assert second.price_raw == Decimal("9000")


@respx.mock
async def test_doq_adapter_respects_limit() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://doq.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://doq.kz/doctors/almaty/terapevt").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = DoqAdapter(
        cities=[("almaty", "Алматы")],
        listing_slugs=[("terapevt", "приём врача")],
    )
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client, limit=1):
            records.append(rec)

    assert len(records) == 1


def test_doq_adapter_registered_in_default_registry() -> None:
    adapter = default_registry.get("doq")
    assert adapter.source_id == "doq"
    assert "Алматы" in adapter.cities

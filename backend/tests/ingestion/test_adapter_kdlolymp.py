"""Offline contract tests for KdlOlympAdapter using a saved Nuxt SSR fixture."""

from decimal import Decimal
from pathlib import Path

import httpx
import respx

from app.ingestion.adapters.kdlolymp import KdlOlympAdapter
from app.ingestion.adapters.registry import default_registry
from app.ingestion.http_client import PoliteHttpClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kdlolymp_pricelist_almaty.html"


@respx.mock
async def test_kdlolymp_adapter_parses_nuxt_fixture_and_skips_zero_price() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://kdlolymp.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /cabinet/\n")
    )
    respx.get("https://kdlolymp.kz/contacts").mock(return_value=httpx.Response(404))
    respx.get("https://kdlolymp.kz/pricelist/almaty").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = KdlOlympAdapter(cities=[("almaty", "Алматы")])
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client):
            records.append(rec)

    assert len(records) == 2

    first = records[0]
    assert first.clinic_name_raw == "КДЛ Олимп"
    assert first.city_raw == "Алматы"
    assert first.service_name_raw == (
        "Клинический анализ крови с лейкоцитарной формулой (ОАК + СОЭ)"
    )
    assert first.price_raw == Decimal("3980")
    assert first.currency_raw == "KZT"
    assert first.duration_days_raw == 1
    assert first.category_hint == "лаборатория"
    assert first.phone_raw == "+77020528585"
    assert (
        str(first.source_url)
        == "https://kdlolymp.kz/services/klinicheskiy-analiz-krovi-s-leykocitarnoy-formuloy-oak"
    )

    second = records[1]
    assert second.price_raw == Decimal("1880")
    # 24 hours with duration_unit=1 -> 1 day
    assert second.duration_days_raw == 1


@respx.mock
async def test_kdlolymp_adapter_respects_limit() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://kdlolymp.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://kdlolymp.kz/contacts").mock(return_value=httpx.Response(404))
    respx.get("https://kdlolymp.kz/pricelist/almaty").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = KdlOlympAdapter(cities=[("almaty", "Алматы")])
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client, limit=1):
            records.append(rec)

    assert len(records) == 1


@respx.mock
async def test_kdlolymp_adapter_extracts_schedule_and_fair_multicity_limit() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    contacts_html = """
    <html><body><script id="__NUXT_DATA__" type="application/json">
    [
      {"GET /api/call-center-shedule?lang=ru-RU": 1},
      {"body": 2},
      {"data": 3},
      [4],
      {"is_active": 5, "translation": 6},
      1,
      {"begin_date": 7, "end_date": 8, "begin_time": 9, "end_time": 10},
      "Понедельник",
      "Суббота",
      "07:00",
      "21:00"
    ]
    </script></body></html>
    """
    respx.get("https://kdlolymp.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://kdlolymp.kz/contacts").mock(
        return_value=httpx.Response(200, text=contacts_html)
    )
    respx.get("https://kdlolymp.kz/pricelist/almaty").mock(
        return_value=httpx.Response(200, text=html)
    )
    respx.get("https://kdlolymp.kz/pricelist/astana").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = KdlOlympAdapter(cities=[("almaty", "Алматы"), ("astana", "Астана")])
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client, limit=2):
            records.append(rec)

    assert len(records) == 2
    assert {r.city_raw for r in records} == {"Алматы", "Астана"}
    assert records[0].working_hours_raw == "Понедельник–Суббота 07:00–21:00"


def test_kdlolymp_adapter_registered_in_default_registry() -> None:
    adapter = default_registry.get("kdlolymp")
    assert adapter.source_id == "kdlolymp"
    assert "Алматы" in adapter.cities

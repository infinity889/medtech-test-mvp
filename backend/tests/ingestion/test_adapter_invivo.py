"""Offline contract tests for InvivoAdapter using a saved HTML fixture."""

from decimal import Decimal
from pathlib import Path

import httpx
import respx

from app.ingestion.adapters.invivo import InvivoAdapter
from app.ingestion.adapters.registry import default_registry
from app.ingestion.http_client import PoliteHttpClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "invivo_category_almaty.html"


@respx.mock
async def test_invivo_adapter_parses_html_fixture_and_skips_invalid_price() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://invivo.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://invivo.kz/ru/sitemap-points.xml").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<urlset><url><loc>"
                "https://invivo.kz/ru/almaty/rec-points-map/detail/68/"
                "</loc></url></urlset>"
            ),
        )
    )
    respx.get("https://invivo.kz/ru/almaty/rec-points-map/detail/68/").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<html><head><title>"
                "Пункт INVIVO: г. Алматы, ул. Майлина, 38а — сдать анализы"
                "</title></head><body>"
                '<div data-lat="43,345069" data-long="77,00647" '
                'data-schedule=\'[{"ScheduleRecord":{"Days":"ПН-ПТ",'
                '"TimeSampling":"07:30 - 15:30"}}]\'></div>'
                "</body></html>"
            ),
        )
    )
    respx.get("https://invivo.kz/ru/almaty/analyzes/obshcheklinicheskie-issledovaniia/").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = InvivoAdapter(
        cities=[("almaty", "Алматы")],
        category_slugs=["obshcheklinicheskie-issledovaniia"],
    )
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client):
            records.append(rec)

    assert len(records) == 2

    first = records[0]
    assert first.clinic_name_raw == "Лаборатория INVIVO"
    assert first.city_raw == "Алматы"
    assert first.address_raw == "г. Алматы, ул. Майлина, 38а"
    assert first.working_hours_raw == "ПН-ПТ 07:30 - 15:30"
    assert first.latitude == 43.345069
    assert first.longitude == 77.00647
    assert first.service_name_raw == "Моча. Микроальбумин в суточной моче"
    assert first.price_raw == Decimal("3350")
    assert first.currency_raw == "KZT"
    assert first.duration_days_raw == 2
    assert first.category_hint == "лаборатория"
    assert first.phone_raw == "+7 (778) 769-38-81"
    expected_url = (
        "https://invivo.kz/ru/almaty/analyzes/obshcheklinicheskie-issledovaniia/"
        "mocha-mikroalbumin-v-sutochnoi-moche-02-006/"
    )
    assert str(first.source_url) == expected_url

    second = records[1]
    assert second.service_name_raw == "Общий анализ крови (ОАК)"
    assert second.price_raw == Decimal("2800")
    assert second.duration_days_raw == 1


@respx.mock
async def test_invivo_adapter_respects_limit() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    respx.get("https://invivo.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://invivo.kz/ru/sitemap-points.xml").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<urlset><url><loc>"
                "https://invivo.kz/ru/almaty/rec-points-map/detail/68/"
                "</loc></url></urlset>"
            ),
        )
    )
    respx.get("https://invivo.kz/ru/almaty/rec-points-map/detail/68/").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<html><head><title>"
                "Пункт INVIVO: г. Алматы, ул. Майлина, 38а — сдать анализы"
                "</title></head><body>"
                '<div data-lat="43,345069" data-long="77,00647" '
                'data-schedule=\'[{"ScheduleRecord":{"Days":"ПН-ПТ",'
                '"TimeSampling":"07:30 - 15:30"}}]\'></div>'
                "</body></html>"
            ),
        )
    )
    respx.get("https://invivo.kz/ru/almaty/analyzes/obshcheklinicheskie-issledovaniia/").mock(
        return_value=httpx.Response(200, text=html)
    )

    async def no_sleep(_: float) -> None:
        return None

    adapter = InvivoAdapter(
        cities=[("almaty", "Алматы")],
        category_slugs=["obshcheklinicheskie-issledovaniia"],
    )
    records = []
    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        async for rec in adapter.fetch_records(client, limit=1):
            records.append(rec)

    assert len(records) == 1


def test_invivo_adapter_registered_in_default_registry() -> None:
    adapter = default_registry.get("invivo")
    assert adapter.source_id == "invivo"
    assert "Алматы" in adapter.cities

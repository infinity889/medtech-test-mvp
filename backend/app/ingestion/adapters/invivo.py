"""Source adapter for INVIVO laboratory network (https://invivo.kz)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl, TypeAdapter

from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.extractors import parse_duration_days, parse_price_and_currency
from app.ingestion.http_client import PoliteHttpClient
from app.ingestion.schemas import RawServiceInput

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)

DEFAULT_INVIVO_CITIES: tuple[tuple[str, str], ...] = (
    ("almaty", "Алматы"),
    ("astana", "Астана"),
    ("shymkent", "Шымкент"),
)

DEFAULT_INVIVO_CATEGORIES: tuple[str, ...] = (
    "obshcheklinicheskie-issledovaniia",
    "biokhimicheskie-issledovaniia-krovi",
    "gormony",
    "gemostaz",
)


def _extract_phone(soup: BeautifulSoup) -> str | None:
    for link in soup.select("a[href^='tel:']"):
        href = link.get("href")
        if not isinstance(href, str):
            continue
        phone = href.removeprefix("tel:").strip()
        if len(phone) >= 7:
            return phone
    return None


class InvivoAdapter(BaseSourceAdapter):
    """Extracts public laboratory test prices from invivo.kz category pages."""

    source_id = "invivo"
    display_name = "Лаборатория INVIVO"
    supported_format = "html"
    base_url = "https://invivo.kz"

    def __init__(
        self,
        cities: Sequence[tuple[str, str]] | None = None,
        category_slugs: Sequence[str] | None = None,
    ) -> None:
        self._city_pairs = tuple(cities) if cities is not None else DEFAULT_INVIVO_CITIES
        self._category_slugs = (
            tuple(category_slugs) if category_slugs is not None else DEFAULT_INVIVO_CATEGORIES
        )
        self.cities = tuple(city_name for _, city_name in self._city_pairs)

    async def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        yielded = 0

        for city_slug, city_name in self._city_pairs:
            for category_slug in self._category_slugs:
                if limit is not None and yielded >= limit:
                    return

                page_url = f"{self.base_url}/ru/{city_slug}/analyzes/{category_slug}/"
                html = await client.get_text(page_url)
                soup = BeautifulSoup(html, "lxml")
                phone = _extract_phone(soup)

                for item in soup.select("div.results-analyzes-item"):
                    if limit is not None and yielded >= limit:
                        return

                    name_el = item.select_one("a.results-analyzes-name")
                    price_el = item.select_one("div.results-analyzes-price p")
                    if name_el is None or price_el is None:
                        continue

                    service_name = " ".join(name_el.get_text(" ", strip=True).split())
                    if not service_name:
                        continue

                    raw_price_text = price_el.get_text(" ", strip=True)
                    try:
                        price, currency = parse_price_and_currency(raw_price_text)
                    except ValueError:
                        continue

                    days_el = item.select_one("span.ra-days")
                    code_el = item.select_one("span.ra-code")
                    bio_el = item.select_one("span.ra-bio")

                    duration_days = (
                        parse_duration_days(days_el.get_text(" ", strip=True))
                        if days_el is not None
                        else None
                    )
                    href = name_el.get("href")
                    service_url = (
                        urljoin(self.base_url, href)
                        if isinstance(href, str) and href.strip()
                        else page_url
                    )

                    yield RawServiceInput(
                        clinic_name_raw="Лаборатория INVIVO",
                        city_raw=city_name,
                        phone_raw=phone,
                        has_online_booking=True,
                        service_name_raw=service_name,
                        category_hint="лаборатория",
                        price_raw=price,
                        currency_raw=currency,
                        duration_days_raw=duration_days,
                        source_url=_HTTP_URL_ADAPTER.validate_python(service_url),
                        raw_payload={
                            "code": code_el.get_text(" ", strip=True) if code_el else None,
                            "biomaterial": bio_el.get_text(" ", strip=True) if bio_el else None,
                            "category_slug": category_slug,
                            "city_slug": city_slug,
                            "price_text": raw_price_text,
                        },
                    )
                    yielded += 1

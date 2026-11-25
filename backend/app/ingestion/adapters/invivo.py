"""Source adapter for INVIVO laboratory network (https://invivo.kz)."""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl, TypeAdapter

from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.extractors import parse_duration_days, parse_price_and_currency
from app.ingestion.http_client import HttpFetchError, PoliteHttpClient, RobotsDisallowedError
from app.ingestion.schemas import RawServiceInput

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_LOC_RE = re.compile(r"<loc>(.*?)</loc>")

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


@dataclass(frozen=True, slots=True)
class _CityBranchMeta:
    address: str | None = None
    working_hours: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def _extract_phone(soup: BeautifulSoup) -> str | None:
    for link in soup.select("a[href^='tel:']"):
        href = link.get("href")
        if not isinstance(href, str):
            continue
        phone = href.removeprefix("tel:").strip()
        if len(phone) >= 7:
            return phone
    return None


def _parse_invivo_schedule(raw_schedule: str) -> str | None:
    try:
        items = json.loads(raw_schedule)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None

    parts: list[str] = []
    for entry in items:
        rec = entry.get("ScheduleRecord") if isinstance(entry, dict) else None
        if not isinstance(rec, dict):
            continue
        days = str(rec.get("Days") or "").strip()
        sampling = str(rec.get("TimeSampling") or "").strip()
        if days and sampling and sampling not in {"-", "—"}:
            parts.append(f"{days} {sampling}")
    return "; ".join(parts) if parts else None


def _parse_invivo_branch_detail(html: str) -> _CityBranchMeta:
    soup = BeautifulSoup(html, "lxml")

    address: str | None = None
    if soup.title and soup.title.string:
        # Format: "Пункт INVIVO: г. Алматы, ул. Майлина, 38а — сдать анализы..."
        title = soup.title.string.strip()
        match = re.search(r"Пункт\s+INVIVO:\s*(.+?)\s*[—–|]", title)
        if match is not None:
            address = match.group(1).strip()

    lat: float | None = None
    lng: float | None = None
    working_hours: str | None = None

    geo_el = soup.select_one("[data-lat][data-lng], [data-lat][data-long]")
    if geo_el is not None:
        raw_lat = geo_el.get("data-lat")
        raw_lng = geo_el.get("data-lng") or geo_el.get("data-long")
        try:
            if isinstance(raw_lat, str) and isinstance(raw_lng, str):
                lat = float(raw_lat.replace(",", "."))
                lng = float(raw_lng.replace(",", "."))
        except ValueError:
            lat, lng = None, None

        raw_sched = geo_el.get("data-schedule")
        if isinstance(raw_sched, str):
            working_hours = _parse_invivo_schedule(raw_sched)

    if working_hours is None:
        sched_el = soup.select_one("[data-schedule]")
        if sched_el is not None and isinstance(sched_el.get("data-schedule"), str):
            working_hours = _parse_invivo_schedule(str(sched_el.get("data-schedule")))

    return _CityBranchMeta(
        address=address,
        working_hours=working_hours,
        latitude=lat,
        longitude=lng,
    )


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

    async def _fetch_city_branch_meta(
        self, client: PoliteHttpClient
    ) -> dict[str, _CityBranchMeta]:
        """Politely fetch 1 representative branch detail per city from sitemap-points.xml."""
        try:
            sitemap_xml = await client.get_text(f"{self.base_url}/ru/sitemap-points.xml")
        except (HttpFetchError, RobotsDisallowedError):
            return {}

        urls = _LOC_RE.findall(sitemap_xml)
        meta_by_city: dict[str, _CityBranchMeta] = {}
        for city_slug, _ in self._city_pairs:
            prefix = f"{self.base_url}/ru/{city_slug}/rec-points-map/detail/"
            detail_url = next((u for u in urls if u.startswith(prefix)), None)
            if detail_url is None:
                continue
            try:
                detail_html = await client.get_text(detail_url)
            except (HttpFetchError, RobotsDisallowedError):
                continue
            meta_by_city[city_slug] = _parse_invivo_branch_detail(detail_html)
        return meta_by_city

    async def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        yielded = 0
        per_city_limit = (
            max(1, math.ceil(limit / len(self._city_pairs)))
            if limit is not None and len(self._city_pairs) > 1
            else limit
        )
        branch_meta_map = await self._fetch_city_branch_meta(client)

        for city_slug, city_name in self._city_pairs:
            city_yielded = 0
            branch_meta = branch_meta_map.get(city_slug, _CityBranchMeta())

            for category_slug in self._category_slugs:
                if limit is not None and yielded >= limit:
                    return
                if per_city_limit is not None and city_yielded >= per_city_limit:
                    break

                page_url = f"{self.base_url}/ru/{city_slug}/analyzes/{category_slug}/"
                html = await client.get_text(page_url)
                soup = BeautifulSoup(html, "lxml")
                phone = _extract_phone(soup)

                for item in soup.select("div.results-analyzes-item"):
                    if limit is not None and yielded >= limit:
                        return
                    if per_city_limit is not None and city_yielded >= per_city_limit:
                        break

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
                        address_raw=branch_meta.address,
                        phone_raw=phone,
                        working_hours_raw=branch_meta.working_hours,
                        latitude=branch_meta.latitude,
                        longitude=branch_meta.longitude,
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
                    city_yielded += 1

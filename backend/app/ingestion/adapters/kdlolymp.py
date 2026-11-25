"""Source adapter for KDL Olymp (https://kdlolymp.kz) public pricelists."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl, TypeAdapter

from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.http_client import HttpFetchError, PoliteHttpClient, RobotsDisallowedError
from app.ingestion.schemas import RawServiceInput

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)

_NUXT_WRAPPER_TAGS = frozenset(
    {"ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "Set"}
)

DEFAULT_KDLOLYMP_CITIES: tuple[tuple[str, str], ...] = (
    ("almaty", "Алматы"),
    ("astana", "Астана"),
    ("shymkent", "Шымкент"),
    ("karaganda", "Караганда"),
    ("aktobe", "Актобе"),
    ("pavlodar", "Павлодар"),
)


def _resolve_nuxt_index(data: list[Any], idx: int, *, depth: int = 0) -> Any:
    """Resolve one Nuxt 3 devalue-encoded index without double-dereferencing primitive ints."""
    if depth > 6 or idx < 0 or idx >= len(data):
        return idx
    val = data[idx]
    if isinstance(val, list):
        if len(val) == 2 and isinstance(val[0], str) and val[0] in _NUXT_WRAPPER_TAGS:
            ref = val[1]
            return _resolve_nuxt_index(data, ref, depth=depth + 1) if isinstance(ref, int) else ref
        return [
            _resolve_nuxt_index(data, item, depth=depth + 1) if isinstance(item, int) else item
            for item in val
        ]
    if isinstance(val, dict):
        return {
            key: (
                _resolve_nuxt_index(data, item, depth=depth + 1) if isinstance(item, int) else item
            )
            for key, item in val.items()
        }
    return val


def _extract_duration_days(price_obj: dict[str, Any]) -> int | None:
    raw_duration = price_obj.get("max_duration") or price_obj.get("min_duration")
    if not isinstance(raw_duration, (int, float)) or raw_duration <= 0:
        return None
    duration_unit = price_obj.get("duration_unit")
    # KDL Olymp uses duration_unit=1 for hours, duration_unit=2 for days
    if duration_unit == 1:
        return max(1, math.ceil(float(raw_duration) / 24.0))
    return int(raw_duration)


def _extract_phone(soup: BeautifulSoup) -> str | None:
    tel_link = soup.select_one("a[href^='tel:']")
    if tel_link is None:
        return None
    href = tel_link.get("href")
    if not isinstance(href, str):
        return None
    phone = href.removeprefix("tel:").strip()
    return phone or None


def _extract_city_geo_and_phone(
    payload: list[Any], city_slug: str
) -> tuple[float | None, float | None, str | None]:
    """Extract city latitude, longitude, and phone embedded in __NUXT_DATA__."""
    for idx, entry in enumerate(payload):
        if not (
            isinstance(entry, dict)
            and "latitude" in entry
            and "longitude" in entry
            and "slug" in entry
        ):
            continue
        resolved = _resolve_nuxt_index(payload, idx)
        if not isinstance(resolved, dict) or resolved.get("slug") != city_slug:
            continue
        lat_raw = resolved.get("latitude")
        lng_raw = resolved.get("longitude")
        lat: float | None = None
        lng: float | None = None
        try:
            if lat_raw is not None and lng_raw is not None:
                lat = float(str(lat_raw).replace(",", "."))
                lng = float(str(lng_raw).replace(",", "."))
        except ValueError:
            lat, lng = None, None

        city_phone: str | None = None
        phones = resolved.get("phones")
        if isinstance(phones, list):
            for item in phones:
                if isinstance(item, dict) and item.get("phone_number"):
                    city_phone = str(item["phone_number"]).strip()
                    break
        return lat, lng, city_phone
    return None, None, None


def _extract_working_hours_from_contacts_html(html: str) -> str | None:
    """Extract call-center/lab working schedule from kdlolymp.kz/contacts __NUXT_DATA__."""
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NUXT_DATA__")
    if not isinstance(script, Tag) or not script.string:
        return None
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None

    parts: list[str] = []
    for entry in payload:
        if not (isinstance(entry, dict) and any("shedule" in str(k) for k in entry)):
            continue
        for key, ref in entry.items():
            if "shedule" not in str(key) or not isinstance(ref, int):
                continue
            resolved = _resolve_nuxt_index(payload, ref)
            if not isinstance(resolved, dict):
                continue
            body = resolved.get("body")
            items = body.get("data") if isinstance(body, dict) else None
            if not isinstance(items, list):
                continue
            for sched in items:
                if not isinstance(sched, dict) or not sched.get("is_active", 1):
                    continue
                tr = sched.get("translation")
                if not isinstance(tr, dict):
                    continue
                begin_d = str(tr.get("begin_date") or "").strip()
                end_d = str(tr.get("end_date") or "").strip()
                begin_t = str(tr.get("begin_time") or "").strip()
                end_t = str(tr.get("end_time") or "").strip()
                if begin_d and begin_t and end_t:
                    days = f"{begin_d}–{end_d}" if end_d and end_d != begin_d else begin_d
                    parts.append(f"{days} {begin_t}–{end_t}")
    return "; ".join(parts) if parts else None


class KdlOlympAdapter(BaseSourceAdapter):
    """Extracts public laboratory test prices from kdlolymp.kz city pricelist pages."""

    source_id = "kdlolymp"
    display_name = "КДЛ Олимп"
    supported_format = "html"
    base_url = "https://kdlolymp.kz"

    def __init__(self, cities: Sequence[tuple[str, str]] | None = None) -> None:
        self._city_pairs = tuple(cities) if cities is not None else DEFAULT_KDLOLYMP_CITIES
        self.cities = tuple(city_name for _, city_name in self._city_pairs)

    async def _fetch_working_hours(self, client: PoliteHttpClient) -> str | None:
        try:
            contacts_html = await client.get_text(f"{self.base_url}/contacts")
        except (HttpFetchError, RobotsDisallowedError):
            return None
        return _extract_working_hours_from_contacts_html(contacts_html)

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
        working_hours = await self._fetch_working_hours(client)

        for city_slug, city_name in self._city_pairs:
            if limit is not None and yielded >= limit:
                return

            page_url = f"{self.base_url}/pricelist/{city_slug}"
            html = await client.get_text(page_url)
            soup = BeautifulSoup(html, "lxml")
            page_phone = _extract_phone(soup)

            script = soup.find("script", id="__NUXT_DATA__")
            if not isinstance(script, Tag) or not script.string:
                continue

            payload = json.loads(script.string)
            if not isinstance(payload, list):
                continue

            lat, lng, city_phone = _extract_city_geo_and_phone(payload, city_slug)
            phone = city_phone or page_phone

            seen_codes: set[str] = set()
            city_yielded = 0
            for idx, entry in enumerate(payload):
                if limit is not None and yielded >= limit:
                    return
                if per_city_limit is not None and city_yielded >= per_city_limit:
                    break
                if not (
                    isinstance(entry, dict)
                    and "translation" in entry
                    and "price" in entry
                    and "code" in entry
                ):
                    continue

                resolved = _resolve_nuxt_index(payload, idx)
                if not isinstance(resolved, dict):
                    continue

                code = str(resolved.get("code") or "").strip()
                if code and code in seen_codes:
                    continue

                translation = resolved.get("translation")
                price_obj = resolved.get("price")
                if not isinstance(translation, dict) or not isinstance(price_obj, dict):
                    continue

                title = str(translation.get("title") or "").strip()
                raw_price_val = price_obj.get("price")
                if not title or raw_price_val is None:
                    continue

                try:
                    price = Decimal(str(raw_price_val))
                except InvalidOperation:
                    continue
                if price <= 0:
                    continue

                if code:
                    seen_codes.add(code)

                slug = str(resolved.get("slug") or "").strip()
                service_url = f"{self.base_url}/services/{slug}" if slug else page_url

                yield RawServiceInput(
                    clinic_name_raw="КДЛ Олимп",
                    city_raw=city_name,
                    address_raw=f"г. {city_name}, сеть пунктов КДЛ Олимп",
                    phone_raw=phone,
                    working_hours_raw=working_hours,
                    latitude=lat,
                    longitude=lng,
                    has_online_booking=True,
                    service_name_raw=title,
                    category_hint="лаборатория",
                    price_raw=price,
                    currency_raw="KZT",
                    duration_days_raw=_extract_duration_days(price_obj),
                    source_url=_HTTP_URL_ADAPTER.validate_python(service_url),
                    raw_payload={
                        "code": code,
                        "slug": slug,
                        "city_slug": city_slug,
                        "category_id": resolved.get("category_id"),
                        "price": str(price),
                        "min_duration": price_obj.get("min_duration"),
                        "max_duration": price_obj.get("max_duration"),
                        "duration_unit": price_obj.get("duration_unit"),
                    },
                )
                yielded += 1
                city_yielded += 1

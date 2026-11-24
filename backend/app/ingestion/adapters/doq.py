"""Source adapter for DOQ.kz clinic & doctor aggregator (https://doq.kz)."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import HttpUrl, TypeAdapter

from app.ingestion.adapters.base import BaseSourceAdapter
from app.ingestion.http_client import PoliteHttpClient
from app.ingestion.schemas import RawServiceInput

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)

DEFAULT_DOQ_CITIES: tuple[tuple[str, str], ...] = (
    ("almaty", "Алматы"),
    ("astana", "Астана"),
    ("shymkent", "Шымкент"),
)

DEFAULT_DOQ_LISTINGS: tuple[tuple[str, str], ...] = (
    ("terapevt", "приём врача"),
    ("kardiolog", "приём врача"),
    ("pediatr", "приём врача"),
    ("nevrolog", "приём врача"),
    ("ginekolog", "приём врача"),
    ("dopler-uzi", "диагностика"),
)

_DIAGNOSTIC_KEYWORDS = ("узи", "экг", "мрт", "кт ", "рентген", "доплер", "фгдс", "ээг", "эхокг")
_PROCEDURE_KEYWORDS = (
    "справка",
    "удаление",
    "вскрытие",
    "инъекц",
    "массаж",
    "капельниц",
    "перевяз",
)


def _infer_category_hint(service_name: str, default_category: str) -> str:
    lowered = service_name.lower()
    if any(kw in lowered for kw in _DIAGNOSTIC_KEYWORDS):
        return "диагностика"
    if any(kw in lowered for kw in _PROCEDURE_KEYWORDS):
        return "процедура"
    return default_category


def _extract_rsc_offer_blocks(html: str) -> list[dict[str, Any]]:
    """Decode Next.js App Router RSC chunks and return doctor/offer dicts with branches+services."""
    decoded_parts: list[str] = []
    for raw_chunk in _RSC_CHUNK_RE.findall(html):
        try:
            decoded_parts.append(json.loads(f'"{raw_chunk}"'))
        except json.JSONDecodeError:
            continue

    decoded = "".join(decoded_parts)
    found: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if (
                "clinic_branches" in node
                and "services" in node
                and isinstance(node["clinic_branches"], list)
                and isinstance(node["services"], list)
            ):
                found.append(node)
                return
            for val in node.values():
                _walk(val)
        elif isinstance(node, list):
            for val in node:
                _walk(val)

    for line in decoded.splitlines():
        if "clinic_branches" not in line:
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        try:
            parsed = json.loads(line[colon + 1 :])
        except json.JSONDecodeError:
            continue
        _walk(parsed)

    return found


def _normalize_rating(raw_score: Any) -> float | None:
    if not isinstance(raw_score, (int, float)) or raw_score <= 0:
        return None
    # DOQ.kz uses a 0..10 feedback_score; normalize to 0..5 scale
    score = float(raw_score)
    normalized = score / 2.0 if score > 5.0 else score
    return round(normalized, 2)


class DoqAdapter(BaseSourceAdapter):
    """Extracts clinic services, doctor appointments, addresses, geo, and ratings from doq.kz."""

    source_id = "doq"
    display_name = "DOQ.kz (Клиники и врачи РК)"
    supported_format = "html"
    base_url = "https://doq.kz"

    def __init__(
        self,
        cities: Sequence[tuple[str, str]] | None = None,
        listing_slugs: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        self._city_pairs = tuple(cities) if cities is not None else DEFAULT_DOQ_CITIES
        self._listings = (
            tuple(listing_slugs) if listing_slugs is not None else DEFAULT_DOQ_LISTINGS
        )
        self.cities = tuple(city_name for _, city_name in self._city_pairs)

    async def fetch_records(
        self,
        client: PoliteHttpClient,
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        yielded = 0

        for city_slug, city_name in self._city_pairs:
            for listing_slug, default_category in self._listings:
                if limit is not None and yielded >= limit:
                    return

                page_url = f"{self.base_url}/doctors/{city_slug}/{listing_slug}"
                html = await client.get_text(page_url)
                offer_blocks = _extract_rsc_offer_blocks(html)

                for block in offer_blocks:
                    if limit is not None and yielded >= limit:
                        return

                    branches_by_id: dict[int, dict[str, Any]] = {}
                    for branch in block.get("clinic_branches", []):
                        if isinstance(branch, dict) and isinstance(branch.get("id"), int):
                            branches_by_id[branch["id"]] = branch

                    offline_only = bool(block.get("offline_booking_enabled"))

                    for svc_entry in block.get("services", []):
                        if limit is not None and yielded >= limit:
                            return
                        if not isinstance(svc_entry, dict) or not svc_entry.get("is_active", True):
                            continue

                        branch_id = svc_entry.get("clinic_branch")
                        if not isinstance(branch_id, int) or branch_id not in branches_by_id:
                            continue
                        branch = branches_by_id[branch_id]

                        svc_obj = svc_entry.get("service")
                        if not isinstance(svc_obj, dict):
                            continue
                        service_name = str(svc_obj.get("name") or "").strip()
                        clinic_name = str(branch.get("name") or "").strip()
                        if not service_name or not clinic_name:
                            continue

                        discount_price = svc_entry.get("discount_price")
                        base_price = svc_entry.get("base_price")
                        chosen_price = (
                            discount_price
                            if isinstance(discount_price, (int, float)) and discount_price > 0
                            else base_price
                        )
                        if chosen_price is None:
                            continue
                        try:
                            price = Decimal(str(chosen_price))
                        except InvalidOperation:
                            continue
                        if price <= 0:
                            continue

                        location = branch.get("location")
                        lat: float | None = None
                        lng: float | None = None
                        if isinstance(location, dict):
                            raw_lat = location.get("lat")
                            raw_lng = location.get("lng")
                            if isinstance(raw_lat, (int, float)) and isinstance(
                                raw_lng, (int, float)
                            ):
                                lat = float(raw_lat)
                                lng = float(raw_lng)

                        phones = branch.get("phones")
                        phone: str | None = None
                        if isinstance(phones, list) and phones and isinstance(phones[0], str):
                            phone = phones[0].strip() or None

                        address_raw = branch.get("address")
                        address = str(address_raw).strip() if address_raw else None

                        clinic_slug = str(branch.get("clinic_slug") or "").strip()
                        source_url = (
                            f"{self.base_url}/clinics/{city_slug}/{clinic_slug}"
                            if clinic_slug
                            else page_url
                        )

                        has_online_booking = (
                            bool(svc_entry.get("nearest_slot_datetime")) or not offline_only
                        )

                        yield RawServiceInput(
                            clinic_name_raw=clinic_name,
                            city_raw=city_name,
                            address_raw=address,
                            phone_raw=phone,
                            latitude=lat,
                            longitude=lng,
                            clinic_rating_raw=_normalize_rating(branch.get("feedback_score")),
                            has_online_booking=has_online_booking,
                            service_name_raw=service_name,
                            category_hint=_infer_category_hint(service_name, default_category),
                            price_raw=price,
                            currency_raw="KZT",
                            duration_days_raw=None,
                            source_url=_HTTP_URL_ADAPTER.validate_python(source_url),
                            raw_payload={
                                "doq_service_entry_id": svc_entry.get("id"),
                                "clinic_branch_id": branch_id,
                                "clinic_slug": clinic_slug,
                                "listing_slug": listing_slug,
                                "base_price": base_price,
                                "discount_price": discount_price,
                                "feedback_score_10": branch.get("feedback_score"),
                            },
                        )
                        yielded += 1

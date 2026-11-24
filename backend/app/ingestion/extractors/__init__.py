"""Shared price-list extraction types and value parsers (HTML, PDF, DOCX, Excel)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

_PRICE_NUMBER_RE = re.compile(r"-?\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?")
_DURATION_RANGE_RE = re.compile(r"(\d+)\s*[-–—]\s*(\d+)")
_DURATION_SINGLE_RE = re.compile(r"(\d+)")

_NAME_HEADER_KEYWORDS = (
    "наименование",
    "услуг",
    "анализ",
    "исследован",
    "назван",
    "service",
    "name",
)
_PRICE_HEADER_KEYWORDS = ("цена", "стоимост", "прайс", "тариф", "price", "cost", "kzt", "тенге")
_DURATION_HEADER_KEYWORDS = ("срок", "готовност", "дней", "дня", "duration", "days", "turnaround")


@dataclass(frozen=True, slots=True)
class ExtractedPriceRow:
    """One extracted raw price row from a document or HTML table."""

    service_name_raw: str
    price_raw: Decimal
    currency_raw: str = "KZT"
    duration_days_raw: int | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractionError:
    """Structured row-level extraction error."""

    row_index: int
    reason: str
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result returned by any document extractor."""

    rows: list[ExtractedPriceRow] = field(default_factory=list)
    errors: list[ExtractionError] = field(default_factory=list)


def parse_price_and_currency(raw_text: str) -> tuple[Decimal, str]:
    """Parse a raw price string into (Decimal price > 0, currency code KZT|USD)."""
    cleaned = raw_text.strip()
    if not cleaned:
        raise ValueError("Empty price string")

    lowered = cleaned.lower()
    currency = "USD" if ("$" in lowered or "usd" in lowered) else "KZT"

    match = _PRICE_NUMBER_RE.search(cleaned)
    if match is None:
        raise ValueError(f"Unable to parse price from '{raw_text}'")

    numeric_str = (
        match.group(0)
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        value = Decimal(numeric_str)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal price '{raw_text}'") from exc

    if value <= 0:
        raise ValueError(f"Price must be positive, got {value}")

    return value, currency


def parse_duration_days(raw_text: str | None) -> int | None:
    """Parse turnaround time text (e.g. '2-3 дня', '24 часа', '1 day') into integer days."""
    if raw_text is None:
        return None
    cleaned = raw_text.strip().lower()
    if not cleaned or cleaned in {"-", "—", "n/a", "нет"}:
        return None

    is_hours = any(token in cleaned for token in ("час", "hour", "ч.", "hr"))

    range_match = _DURATION_RANGE_RE.search(cleaned)
    if range_match is not None:
        upper = int(range_match.group(2))
        return max(1, math.ceil(upper / 24)) if is_hours else upper

    single_match = _DURATION_SINGLE_RE.search(cleaned)
    if single_match is not None:
        value = int(single_match.group(1))
        return max(1, math.ceil(value / 24)) if is_hours else value

    return None


def _detect_columns(header_cells: list[str]) -> tuple[int, int, int | None] | None:
    """Detect (name_idx, price_idx, duration_idx) from a header row, or None if not a header."""
    name_idx: int | None = None
    price_idx: int | None = None
    duration_idx: int | None = None

    for idx, cell in enumerate(header_cells):
        text = cell.strip().lower()
        if not text:
            continue
        if name_idx is None and any(k in text for k in _NAME_HEADER_KEYWORDS):
            name_idx = idx
        elif price_idx is None and any(k in text for k in _PRICE_HEADER_KEYWORDS):
            price_idx = idx
        elif duration_idx is None and any(k in text for k in _DURATION_HEADER_KEYWORDS):
            duration_idx = idx

    if name_idx is not None and price_idx is not None:
        return name_idx, price_idx, duration_idx
    return None


def extract_price_rows_from_matrix(
    matrix: list[list[str]],
    *,
    row_offset: int = 0,
) -> ExtractionResult:
    """Extract price rows from a 2D table of strings using header auto-detection."""
    rows: list[ExtractedPriceRow] = []
    errors: list[ExtractionError] = []

    if not matrix:
        return ExtractionResult(rows=rows, errors=errors)

    name_idx = 0
    price_idx = 1
    duration_idx: int | None = None
    start_row = 0

    detected = _detect_columns(matrix[0])
    if detected is not None:
        name_idx, price_idx, duration_idx = detected
        start_row = 1
    elif len(matrix[0]) >= 3:
        # Fallback heuristic when header is absent: [name, duration?, price]
        price_idx = len(matrix[0]) - 1
        duration_idx = 1 if len(matrix[0]) == 3 else None

    for rel_idx, cells in enumerate(matrix[start_row:], start=start_row):
        cleaned = [cell.strip() for cell in cells]
        if not any(cleaned):
            continue

        # Skip repeated header rows inside multi-page tables
        if _detect_columns(cleaned) is not None:
            continue

        if len(cleaned) <= max(name_idx, price_idx):
            errors.append(
                ExtractionError(
                    row_index=row_offset + rel_idx,
                    reason="Row has fewer columns than expected",
                    raw_data={"cells": cleaned},
                )
            )
            continue

        service_name = cleaned[name_idx]
        price_cell = cleaned[price_idx]
        duration_cell = (
            cleaned[duration_idx]
            if duration_idx is not None and duration_idx < len(cleaned)
            else None
        )

        if not service_name:
            errors.append(
                ExtractionError(
                    row_index=row_offset + rel_idx,
                    reason="Missing service name",
                    raw_data={"cells": cleaned},
                )
            )
            continue

        try:
            price, currency = parse_price_and_currency(price_cell)
        except ValueError as exc:
            errors.append(
                ExtractionError(
                    row_index=row_offset + rel_idx,
                    reason=f"Invalid price: {exc}",
                    raw_data={"service_name": service_name, "price_cell": price_cell},
                )
            )
            continue

        rows.append(
            ExtractedPriceRow(
                service_name_raw=service_name,
                price_raw=price,
                currency_raw=currency,
                duration_days_raw=parse_duration_days(duration_cell),
                raw_row={"cells": cleaned},
            )
        )

    return ExtractionResult(rows=rows, errors=errors)

"""Deterministic text normalization, category mapping, clinic keys, and currency conversion."""

from __future__ import annotations

import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal

from app.normalization.models import CurrencyCode, ServiceCategory

_NON_WORD_RE = re.compile(r"[^\w\s/+\\-]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_PREFIXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:кровь|моча|кал)\s*\.\s*"),
    re.compile(r"^(?:прием|консультация)\s+врача\s+"),
)

_CATEGORY_MAP: dict[str, ServiceCategory] = {
    "лаборатория": ServiceCategory.LAB,
    "анализ": ServiceCategory.LAB,
    "анализы": ServiceCategory.LAB,
    "lab": ServiceCategory.LAB,
    "laboratory": ServiceCategory.LAB,
    "прием врача": ServiceCategory.DOCTOR,
    "врач": ServiceCategory.DOCTOR,
    "консультация": ServiceCategory.DOCTOR,
    "doctor": ServiceCategory.DOCTOR,
    "диагностика": ServiceCategory.DIAGNOSTICS,
    "diagnostics": ServiceCategory.DIAGNOSTICS,
    "процедура": ServiceCategory.PROCEDURE,
    "процедуры": ServiceCategory.PROCEDURE,
    "procedure": ServiceCategory.PROCEDURE,
}


def normalize_service_text(text: str) -> str:
    """Normalize a raw service name for deterministic exact/synonym/fuzzy matching."""
    cleaned = text.strip().lower().replace("ё", "е")
    for prefix_re in _LEADING_PREFIXES:
        stripped = prefix_re.sub("", cleaned, count=1).strip()
        if stripped != cleaned and stripped:
            cleaned = stripped
            break
    cleaned = _NON_WORD_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("_", " ")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def map_category_hint(hint: str | None) -> ServiceCategory | None:
    """Map raw category hint string from an adapter into a canonical ServiceCategory."""
    if hint is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", hint.strip().lower().replace("ё", "е"))
    if not normalized:
        return None
    return _CATEGORY_MAP.get(normalized)


def compute_clinic_key(
    source_id: str,
    clinic_name: str,
    city: str,
    address: str | None,
) -> str:
    """Compute a deterministic SHA-256 clinic deduplication key."""
    parts = [
        _WHITESPACE_RE.sub(" ", source_id.strip().lower()),
        _WHITESPACE_RE.sub(" ", clinic_name.strip().lower().replace("ё", "е")),
        _WHITESPACE_RE.sub(" ", city.strip().lower().replace("ё", "е")),
        _WHITESPACE_RE.sub(" ", (address or "").strip().lower().replace("ё", "е")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def convert_to_kzt(
    price: Decimal,
    currency: str,
    usd_to_kzt_rate: Decimal,
) -> tuple[Decimal, CurrencyCode]:
    """Convert raw price in KZT or USD into KZT Decimal quantized to 0.01."""
    if price <= 0:
        raise ValueError(f"Price must be positive, got {price}")
    if usd_to_kzt_rate <= 0:
        raise ValueError(f"usd_to_kzt_rate must be positive, got {usd_to_kzt_rate}")

    code_str = currency.strip().upper()
    try:
        code = CurrencyCode(code_str)
    except ValueError as exc:
        raise ValueError(f"Unsupported currency: '{currency}'") from exc

    kzt_amount = price if code == CurrencyCode.KZT else price * usd_to_kzt_rate
    quantized = kzt_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return quantized, code

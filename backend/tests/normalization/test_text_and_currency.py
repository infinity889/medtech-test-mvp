"""Unit tests for text normalization, category mapping, clinic keys, and KZT/USD conversion."""

from decimal import Decimal

import pytest

from app.normalization.models import CurrencyCode, ServiceCategory
from app.normalization.text_utils import (
    compute_clinic_key,
    convert_to_kzt,
    map_category_hint,
    normalize_service_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Общий анализ крови (ОАК)*", "общий анализ крови оак"),
        ("Кровь. Общий анализ (ОАК)", "общий анализ оак"),
        ("Моча. Общий анализ (ОАМ)", "общий анализ оам"),
        ("Приём врача терапевта первичный", "терапевта первичный"),
        ('Профиль "Обследование печени"', "профиль обследование печени"),
        ("  CBC  ", "cbc"),
    ],
)
def test_normalize_service_text(raw: str, expected: str) -> None:
    assert normalize_service_text(raw) == expected


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("лаборатория", ServiceCategory.LAB),
        ("приём врача", ServiceCategory.DOCTOR),
        ("прием врача", ServiceCategory.DOCTOR),
        ("диагностика", ServiceCategory.DIAGNOSTICS),
        ("процедура", ServiceCategory.PROCEDURE),
        ("lab", ServiceCategory.LAB),
        ("", None),
        (None, None),
        ("неизвестная категория", None),
    ],
)
def test_map_category_hint(hint: str | None, expected: ServiceCategory | None) -> None:
    assert map_category_hint(hint) == expected


def test_convert_to_kzt_supports_kzt_and_usd_with_decimal() -> None:
    kzt_price, kzt_cur = convert_to_kzt(Decimal("3980"), "kzt", Decimal("495.00"))
    assert kzt_price == Decimal("3980.00")
    assert kzt_cur == CurrencyCode.KZT

    usd_price, usd_cur = convert_to_kzt(Decimal("12.50"), "USD", Decimal("495.25"))
    assert usd_price == Decimal("6190.63")
    assert usd_cur == CurrencyCode.USD


def test_convert_to_kzt_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        convert_to_kzt(Decimal("0"), "KZT", Decimal("495.00"))
    with pytest.raises(ValueError):
        convert_to_kzt(Decimal("10"), "EUR", Decimal("495.00"))
    with pytest.raises(ValueError):
        convert_to_kzt(Decimal("10"), "USD", Decimal("-1"))


def test_compute_clinic_key_is_deterministic_and_case_insensitive() -> None:
    k1 = compute_clinic_key("doq", "AQmed в Аксай 2", "Алматы", "мкр. Аксай-2, 44А")
    k2 = compute_clinic_key("DOQ", "  aqmed в аксай 2 ", "алматы", "мкр. аксай-2, 44а")
    k3 = compute_clinic_key("doq", "AQmed в Аксай 2", "Астана", "мкр. Аксай-2, 44А")
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 64

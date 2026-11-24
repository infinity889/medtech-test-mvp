"""Unit tests for HTML and PDF price-list extractors and price/duration parsers."""

from decimal import Decimal

import pytest

from app.ingestion.extractors import parse_duration_days, parse_price_and_currency
from app.ingestion.extractors.html import extract_price_rows_from_html_tables
from app.ingestion.extractors.pdf import extract_price_rows_from_pdf


def _build_minimal_pdf(pages_lines: list[list[str]]) -> bytes:
    """Build a valid multi-page ASCII/Latin PDF with selectable text lines for pdfplumber tests."""
    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    # Reserve catalog (1) and pages (2)
    add_obj(b"")
    add_obj(b"")
    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    for lines in pages_lines:
        commands = ["BT", "/F1 10 Tf"]
        y = 750
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"1 0 0 1 50 {y} Tm ({escaped}) Tj")
            y -= 18
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        content_id = add_obj(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        page_id = add_obj(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


@pytest.mark.parametrize(
    ("raw", "expected_price", "expected_currency"),
    [
        ("3 200 ₸", Decimal("3200"), "KZT"),
        ("12\u00a0500 тг", Decimal("12500"), "KZT"),
        ("от 4 500,50 KZT", Decimal("4500.50"), "KZT"),
        ("$25", Decimal("25"), "USD"),
        ("30.5 USD", Decimal("30.5"), "USD"),
    ],
)
def test_parse_price_and_currency_valid(
    raw: str, expected_price: Decimal, expected_currency: str
) -> None:
    price, currency = parse_price_and_currency(raw)
    assert isinstance(price, Decimal)
    assert price == expected_price
    assert currency == expected_currency


@pytest.mark.parametrize("raw", ["", "по запросу", "0 ₸", "-500 тг"])
def test_parse_price_and_currency_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_price_and_currency(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 день", 1),
        ("2-3 раб. дня", 3),
        ("до 5 дней", 5),
        ("24 часа", 1),
        ("-", None),
        (None, None),
    ],
)
def test_parse_duration_days(raw: str | None, expected: int | None) -> None:
    assert parse_duration_days(raw) == expected


def test_extract_price_rows_from_html_tables() -> None:
    html = """
    <html><body>
      <table>
        <thead>
          <tr><th>Наименование услуги</th><th>Срок выполнения</th><th>Цена</th></tr>
        </thead>
        <tbody>
          <tr><td>Общий анализ крови (ОАК)</td><td>1 день</td><td>2 800 ₸</td></tr>
          <tr><td>Биохимия крови расширенная</td><td>2-3 дня</td><td>14 500 тг</td></tr>
          <tr><td>Консультация (USD тариф)</td><td></td><td>$45</td></tr>
          <tr><td>Недоступная услуга</td><td>1 день</td><td>по запросу</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_price_rows_from_html_tables(html)

    assert len(result.rows) == 3
    assert result.rows[0].service_name_raw == "Общий анализ крови (ОАК)"
    assert result.rows[0].price_raw == Decimal("2800")
    assert result.rows[0].currency_raw == "KZT"
    assert result.rows[0].duration_days_raw == 1

    assert result.rows[1].price_raw == Decimal("14500")
    assert result.rows[1].duration_days_raw == 3

    assert result.rows[2].price_raw == Decimal("45")
    assert result.rows[2].currency_raw == "USD"

    assert len(result.errors) == 1
    assert "price" in result.errors[0].reason.lower()


def test_extract_price_rows_from_multipage_pdf() -> None:
    pdf_bytes = _build_minimal_pdf(
        [
            [
                "Price List - Page 1",
                "Complete Blood Count (CBC)   2 900 KZT   1 day",
                "Vitamin D 25-OH   8 500 KZT   2 days",
                "Broken Line Without Price   N/A",
            ],
            [
                "Price List - Page 2",
                "Thyroid Panel TSH   3 400 KZT   1 day",
                "MRI Brain Consultation   $60",
            ],
        ]
    )

    result = extract_price_rows_from_pdf(pdf_bytes)

    assert len(result.rows) == 4
    assert result.rows[0].service_name_raw == "Complete Blood Count (CBC)"
    assert result.rows[0].price_raw == Decimal("2900")
    assert result.rows[0].currency_raw == "KZT"
    assert result.rows[0].duration_days_raw == 1

    assert result.rows[3].service_name_raw == "MRI Brain Consultation"
    assert result.rows[3].price_raw == Decimal("60")
    assert result.rows[3].currency_raw == "USD"

"""Unit tests for DOCX and Excel (.xlsx) price-list extractors."""

import io
from decimal import Decimal

from docx import Document
from openpyxl import Workbook

from app.ingestion.extractors.docx import extract_price_rows_from_docx
from app.ingestion.extractors.excel import extract_price_rows_from_excel


def test_extract_price_rows_from_docx_tables() -> None:
    doc = Document()
    doc.add_heading("Прайс-лист клиники", level=1)
    table = doc.add_table(rows=4, cols=3)

    rows_data = [
        ["Наименование услуги", "Срок готовности", "Цена (тг)"],
        ["УЗИ органов брюшной полости", "1 день", "9 500 ₸"],
        ["Приём терапевта первичный", "-", "8 000"],
        ["Архивная услуга", "1 день", "нет цены"],
    ]
    for r_idx, values in enumerate(rows_data):
        for c_idx, val in enumerate(values):
            table.cell(r_idx, c_idx).text = val

    buf = io.BytesIO()
    doc.save(buf)

    result = extract_price_rows_from_docx(buf.getvalue())

    assert len(result.rows) == 2
    assert result.rows[0].service_name_raw == "УЗИ органов брюшной полости"
    assert result.rows[0].price_raw == Decimal("9500")
    assert result.rows[0].currency_raw == "KZT"
    assert result.rows[0].duration_days_raw == 1

    assert result.rows[1].service_name_raw == "Приём терапевта первичный"
    assert result.rows[1].price_raw == Decimal("8000")
    assert result.rows[1].duration_days_raw is None

    assert len(result.errors) == 1


def test_extract_price_rows_from_excel_multisheet() -> None:
    wb = Workbook()
    ws_lab = wb.active
    assert ws_lab is not None
    ws_lab.title = "Лаборатория"
    ws_lab.append(["Название анализа", "Стоимость", "Срок"])
    ws_lab.append(["Глюкоза крови", 1800, "1 день"])
    ws_lab.append(["Ферритин", "5 200 тг", "1-2 дня"])
    ws_lab.append(["Ошибочная строка", 0, "1 день"])

    ws_diag = wb.create_sheet("Диагностика")
    ws_diag.append(["Наименование услуги", "Цена"])
    ws_diag.append(["ЭКГ с расшифровкой", 4500.50])
    ws_diag.append(["Телемедицина VIP", "$35"])

    buf = io.BytesIO()
    wb.save(buf)

    result = extract_price_rows_from_excel(buf.getvalue())

    assert len(result.rows) == 4
    assert result.rows[0].service_name_raw == "Глюкоза крови"
    assert result.rows[0].price_raw == Decimal("1800")
    assert result.rows[0].duration_days_raw == 1

    assert result.rows[1].service_name_raw == "Ферритин"
    assert result.rows[1].price_raw == Decimal("5200")
    assert result.rows[1].duration_days_raw == 2

    assert result.rows[2].service_name_raw == "ЭКГ с расшифровкой"
    assert result.rows[2].price_raw == Decimal("4500.5")

    assert result.rows[3].service_name_raw == "Телемедицина VIP"
    assert result.rows[3].price_raw == Decimal("35")
    assert result.rows[3].currency_raw == "USD"

    assert len(result.errors) == 1

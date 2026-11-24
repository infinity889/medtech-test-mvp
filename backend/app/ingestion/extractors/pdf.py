"""PDF price-list extractor using pdfplumber."""

from __future__ import annotations

import io
import re

import pdfplumber

from app.ingestion.extractors import (
    ExtractedPriceRow,
    ExtractionError,
    ExtractionResult,
    extract_price_rows_from_matrix,
    parse_duration_days,
    parse_price_and_currency,
)

_PRICE_TOKEN_RE = re.compile(
    r"(?P<price>(?:\$\s*\d[\d\s\u00a0]*(?:[.,]\d{1,2})?|"
    r"\d[\d\s\u00a0]*(?:[.,]\d{1,2})?\s*(?:₸|тг\.?|тенге|kzt|usd|\$)))",
    re.IGNORECASE,
)


def _extract_from_text_lines(text: str, page_num: int) -> ExtractionResult:
    rows: list[ExtractedPriceRow] = []
    errors: list[ExtractionError] = []

    for line_idx, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue

        match = _PRICE_TOKEN_RE.search(line)
        if match is None:
            continue

        service_name = line[: match.start()].strip(" .-\t")
        price_token = match.group("price").strip()
        trailing = line[match.end() :].strip(" .-\t")

        if not service_name:
            errors.append(
                ExtractionError(
                    row_index=line_idx,
                    reason=f"Page {page_num}: missing service name before price",
                    raw_data={"line": line, "page": page_num},
                )
            )
            continue

        try:
            price, currency = parse_price_and_currency(price_token)
        except ValueError as exc:
            errors.append(
                ExtractionError(
                    row_index=line_idx,
                    reason=f"Page {page_num}: invalid price: {exc}",
                    raw_data={"line": line, "page": page_num},
                )
            )
            continue

        rows.append(
            ExtractedPriceRow(
                service_name_raw=service_name,
                price_raw=price,
                currency_raw=currency,
                duration_days_raw=parse_duration_days(trailing) if trailing else None,
                raw_row={"page": page_num, "line": line},
            )
        )

    return ExtractionResult(rows=rows, errors=errors)


def extract_price_rows_from_pdf(data: bytes) -> ExtractionResult:
    """Extract raw price rows from ruled tables or text lines across all PDF pages."""
    all_rows: list[ExtractedPriceRow] = []
    all_errors: list[ExtractionError] = []
    row_offset = 0

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            extracted_on_page = False

            for table in tables:
                matrix = [[cell or "" for cell in row] for row in table if row]
                if not matrix:
                    continue
                partial = extract_price_rows_from_matrix(matrix, row_offset=row_offset)
                all_rows.extend(partial.rows)
                all_errors.extend(partial.errors)
                row_offset += len(matrix)
                if partial.rows:
                    extracted_on_page = True

            if not extracted_on_page:
                text = page.extract_text() or ""
                text_result = _extract_from_text_lines(text, page_num=page_num)
                all_rows.extend(text_result.rows)
                all_errors.extend(text_result.errors)

    return ExtractionResult(rows=all_rows, errors=all_errors)

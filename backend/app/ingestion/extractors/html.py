"""HTML table price-list extractor using BeautifulSoup + lxml."""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.ingestion.extractors import (
    ExtractedPriceRow,
    ExtractionError,
    ExtractionResult,
    extract_price_rows_from_matrix,
)


def extract_price_rows_from_html_tables(html: str) -> ExtractionResult:
    """Extract raw service price rows from all HTML <table> elements."""
    soup = BeautifulSoup(html, "lxml")
    all_rows: list[ExtractedPriceRow] = []
    all_errors: list[ExtractionError] = []
    row_offset = 0

    for table in soup.find_all("table"):
        matrix: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if cells:
                matrix.append(cells)

        partial = extract_price_rows_from_matrix(matrix, row_offset=row_offset)
        all_rows.extend(partial.rows)
        all_errors.extend(partial.errors)
        row_offset += len(matrix)

    return ExtractionResult(rows=all_rows, errors=all_errors)

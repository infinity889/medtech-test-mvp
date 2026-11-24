"""DOCX price-list extractor using python-docx."""

from __future__ import annotations

import io

from docx import Document

from app.ingestion.extractors import (
    ExtractedPriceRow,
    ExtractionError,
    ExtractionResult,
    extract_price_rows_from_matrix,
)


def extract_price_rows_from_docx(data: bytes) -> ExtractionResult:
    """Extract raw service price rows from all tables in a DOCX document."""
    doc = Document(io.BytesIO(data))
    all_rows: list[ExtractedPriceRow] = []
    all_errors: list[ExtractionError] = []
    row_offset = 0

    for table in doc.tables:
        matrix: list[list[str]] = []
        for row in table.rows:
            cells = [" ".join(cell.text.split()) for cell in row.cells]
            if any(cells):
                matrix.append(cells)

        partial = extract_price_rows_from_matrix(matrix, row_offset=row_offset)
        all_rows.extend(partial.rows)
        all_errors.extend(partial.errors)
        row_offset += len(matrix)

    return ExtractionResult(rows=all_rows, errors=all_errors)

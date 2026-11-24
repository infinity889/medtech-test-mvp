"""Excel (.xlsx) price-list extractor using openpyxl."""

from __future__ import annotations

import io
from collections.abc import Sequence

from openpyxl import load_workbook

from app.ingestion.extractors import (
    ExtractedPriceRow,
    ExtractionError,
    ExtractionResult,
    extract_price_rows_from_matrix,
)


def _cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return " ".join(str(value).split())


def extract_price_rows_from_excel(
    data: bytes,
    *,
    sheet_names: Sequence[str] | None = None,
) -> ExtractionResult:
    """Extract raw service price rows from one or all sheets of an .xlsx workbook."""
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    all_rows: list[ExtractedPriceRow] = []
    all_errors: list[ExtractionError] = []
    row_offset = 0

    try:
        target_sheets = list(sheet_names) if sheet_names is not None else list(workbook.sheetnames)
        for sheet_name in target_sheets:
            if sheet_name not in workbook.sheetnames:
                continue
            sheet = workbook[sheet_name]
            matrix: list[list[str]] = []
            for raw_row in sheet.iter_rows(values_only=True):
                cells = [_cell_to_str(cell) for cell in raw_row]
                if any(cells):
                    matrix.append(cells)

            partial = extract_price_rows_from_matrix(matrix, row_offset=row_offset)
            all_rows.extend(partial.rows)
            all_errors.extend(partial.errors)
            row_offset += len(matrix)
    finally:
        workbook.close()

    return ExtractionResult(rows=all_rows, errors=all_errors)

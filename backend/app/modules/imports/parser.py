"""File parser utility for CSV and Excel (.xlsx) imports.

Handles headers detection, row streaming, encoding normalization,
and preview extraction.
"""

import csv
import os
from typing import Any, Dict, List, Tuple
import openpyxl
from app.core.exceptions import BadRequestException


def get_headers_and_sample(
    file_path: str, sample_limit: int = 10
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """Extract headers, sample preview rows, and estimated total rows."""
    if not os.path.exists(file_path):
        raise BadRequestException(f"Import file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        return _read_csv(file_path, max_rows=sample_limit)
    elif ext in [".xlsx", ".xls"]:
        return _read_xlsx(file_path, max_rows=sample_limit)
    else:
        raise BadRequestException(f"Unsupported file format '{ext}'. Must be .csv or .xlsx")


def read_all_rows(file_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Read all rows from CSV or Excel file."""
    headers, rows, _ = get_headers_and_sample(file_path, sample_limit=None)
    return headers, rows


def _read_csv(
    file_path: str, max_rows: int = None
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    rows: List[Dict[str, Any]] = []
    total_count = 0
    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return [], [], 0

        headers = [str(h).strip() for h in raw_headers if h is not None]

        for row_idx, row in enumerate(reader, start=1):
            total_count += 1
            if max_rows is None or len(rows) < max_rows:
                row_dict = {}
                for col_idx, h in enumerate(headers):
                    val = row[col_idx].strip() if col_idx < len(row) and row[col_idx] is not None else ""
                    row_dict[h] = val
                rows.append(row_dict)

    return headers, rows, total_count


def _read_xlsx(
    file_path: str, max_rows: int = None
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = wb.active
    row_iter = sheet.iter_rows(values_only=True)

    try:
        raw_headers = next(row_iter)
    except StopIteration:
        wb.close()
        return [], [], 0

    headers = [str(h).strip() for h in raw_headers if h is not None and str(h).strip()]

    rows: List[Dict[str, Any]] = []
    total_count = 0

    for row_values in row_iter:
        if not any(v is not None and str(v).strip() for v in row_values):
            continue  # skip completely blank rows
        total_count += 1
        if max_rows is None or len(rows) < max_rows:
            row_dict = {}
            for col_idx, h in enumerate(headers):
                val = (
                    str(row_values[col_idx]).strip()
                    if col_idx < len(row_values) and row_values[col_idx] is not None
                    else ""
                )
                row_dict[h] = val
            rows.append(row_dict)

    wb.close()
    return headers, rows, total_count

# LOGIC HEADER
# Input:          A list of ExtractedReceipt rows, an output directory, and a format
#                 ("xlsx" or "csv").
# Transformation: Flatten each receipt into one spreadsheet row (line items joined
#                 into a single readable cell) and write the file. Rows that failed to
#                 read/parse still appear, carrying their warnings, so nothing is
#                 silently dropped. Writes to xlsx via openpyxl or csv via the stdlib.
# Output:         The Path of the written spreadsheet.

from __future__ import annotations

import csv
from pathlib import Path

from extractor.engines.base import ExtractedReceipt

COLUMNS = [
    "Source File", "Vendor", "Date", "Currency", "Total", "Tax",
    "Line Items", "Duplicate Of", "Engine", "Warnings",
]


def write(rows: list[ExtractedReceipt], output_dir: Path, output_format: str = "xlsx") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        return _write_csv(rows, output_dir / "receipts.csv")
    if output_format == "xlsx":
        return _write_xlsx(rows, output_dir / "receipts.xlsx")
    raise ValueError(f"unknown output_format: {output_format}")


def _row_values(r: ExtractedReceipt) -> list:
    line_items = "; ".join(
        f"{li.description} ({li.amount})" if li.amount is not None else li.description
        for li in r.line_items
    )
    return [
        r.source_file, r.vendor or "", r.date or "", r.currency or "",
        r.total if r.total is not None else "",
        r.tax if r.tax is not None else "",
        line_items, r.duplicate_of or "", r.engine, "; ".join(r.warnings),
    ]


def _write_csv(rows: list[ExtractedReceipt], path: Path) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(_row_values(r))
    return path


def _write_xlsx(rows: list[ExtractedReceipt], path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Receipts"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(_row_values(r))
    # Reasonable column widths for readability.
    widths = [28, 24, 12, 9, 10, 10, 40, 22, 11, 34]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
    wb.save(path)
    return path

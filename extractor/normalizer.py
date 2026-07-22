# LOGIC HEADER
# Input:          An ExtractedReceipt straight from an engine (fields may be rough).
# Transformation: Tidy values into consistent shapes for a spreadsheet — round money
#                 to 2 decimals, collapse whitespace in text, and add a data-quality
#                 warning when the tax looks larger than the total (a common OCR/parse
#                 slip). Never invents data; only cleans what is already there.
# Output:         The same ExtractedReceipt, normalized in place and returned.

from __future__ import annotations

import re

from extractor.engines.base import ExtractedReceipt

_WHITESPACE = re.compile(r"\s+")


def normalize(receipt: ExtractedReceipt) -> ExtractedReceipt:
    receipt.vendor = _clean_text(receipt.vendor)
    receipt.total = _round_money(receipt.total)
    receipt.tax = _round_money(receipt.tax)

    for item in receipt.line_items:
        item.description = _clean_text(item.description) or ""
        item.amount = _round_money(item.amount)

    if receipt.total is not None and receipt.tax is not None and receipt.tax > receipt.total:
        receipt.warnings.append("tax is greater than total — check this row")

    return receipt


def _clean_text(value):
    if value is None:
        return None
    cleaned = _WHITESPACE.sub(" ", str(value)).strip()
    return cleaned or None


def _round_money(value):
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None

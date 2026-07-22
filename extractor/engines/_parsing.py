# LOGIC HEADER
# Input:          A raw JSON string returned by an AI model, the source filename, and
#                 the engine name to stamp on the row.
# Transformation: Parse the JSON (tolerating markdown code-fences the model may wrap it
#                 in) into a structured ExtractedReceipt. Bad/again-nonsense JSON becomes
#                 a warning, never a crash. Shared by every AI engine so the text and
#                 vision engines can never drift apart in how they read a model reply.
# Output:         An ExtractedReceipt.

from __future__ import annotations

import json
import re
from typing import Optional

from extractor.engines.base import ExtractedReceipt, LineItem

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_receipt_json(raw_json: str, source_file: str, engine_name: str) -> ExtractedReceipt:
    result = ExtractedReceipt(source_file=source_file, engine=engine_name)
    cleaned = _FENCE.sub("", raw_json or "").strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        result.warnings.append(f"AI reply was not valid JSON: {exc}")
        return result
    if not isinstance(data, dict):
        result.warnings.append("AI reply was not a JSON object")
        return result

    result.vendor = _clean_str(data.get("vendor"))
    result.date = _clean_str(data.get("date"))
    result.currency = _clean_str(data.get("currency"))
    result.total = _clean_num(data.get("total"))
    result.tax = _clean_num(data.get("tax"))
    for item in data.get("line_items") or []:
        if isinstance(item, dict):
            result.line_items.append(
                LineItem(description=_clean_str(item.get("description")) or "",
                         amount=_clean_num(item.get("amount")))
            )
    return result


def _clean_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _clean_num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").lstrip("$£€₱¥ "))
    except ValueError:
        return None

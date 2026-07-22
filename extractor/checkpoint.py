# LOGIC HEADER
# Input:          The Config (for the output dir) and, when saving, the in-progress
#                 map of content_hash -> extracted-row dict.
# Transformation: Persist AI-vision results to a small JSON file keyed by each file's
#                 content hash, so a re-run or a crash mid-batch skips receipts already
#                 processed and never re-spends the user's AI quota. Converts between
#                 ExtractedReceipt objects and plain dicts for storage.
# Output:         A loaded cache dict (load), a persisted file (save), and conversions.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extractor.config import Config
from extractor.engines.base import ExtractedReceipt, LineItem

_FILENAME = ".vision_cache.json"


def _cache_path(config: Config) -> Path:
    return config.output_dir / _FILENAME


def load(config: Config) -> dict[str, dict]:
    path = _cache_path(config)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}  # a corrupt cache is ignored, not fatal — we just reprocess


def save(config: Config, cache: dict[str, dict]) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(config)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    tmp.replace(path)   # atomic swap so a crash never leaves a half-written cache


def to_dict(r: ExtractedReceipt) -> dict[str, Any]:
    return {
        "source_file": r.source_file, "vendor": r.vendor, "date": r.date,
        "currency": r.currency, "total": r.total, "tax": r.tax,
        "engine": r.engine,
        "line_items": [{"description": li.description, "amount": li.amount}
                       for li in r.line_items],
        "warnings": list(r.warnings),
    }


def to_receipt(d: dict[str, Any]) -> ExtractedReceipt:
    r = ExtractedReceipt(source_file=d.get("source_file", ""), engine=d.get("engine", "ai_vision"))
    r.vendor = d.get("vendor"); r.date = d.get("date"); r.currency = d.get("currency")
    r.total = d.get("total"); r.tax = d.get("tax")
    r.warnings = list(d.get("warnings", []))
    r.line_items = [LineItem(description=li.get("description", ""), amount=li.get("amount"))
                    for li in d.get("line_items", [])]
    return r

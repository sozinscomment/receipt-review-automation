# LOGIC HEADER
# Input:          A Config (engine choice, folders, OCR settings).
# Transformation: The assembly line — discover files, read text from each (with OCR
#                 fallback), run the selected engine, normalize, and collect one row
#                 per file. A single file's failure is captured as a warning row and
#                 never stops the batch. This module is GUI-free and fully testable.
# Output:         A list of normalized ExtractedReceipt rows.

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

from extractor import checkpoint, dedup, io_loader, normalizer, text_reader
from extractor.config import Config
from extractor.engines.base import ExtractedReceipt
from extractor.engines.factory import build_engine

# Progress callback: progress(done_index, total, filename, receipt_or_None).
# receipt is None to signal "starting this file", or the ExtractedReceipt when done.
ProgressFn = Callable[[int, int, str, Optional[ExtractedReceipt]], None]


def run(config: Config, progress: Optional[ProgressFn] = None,
        limit: Optional[int] = None) -> list[ExtractedReceipt]:
    files = io_loader.discover_files(config.input_dir)
    if limit is not None:
        files = files[:limit]
    engine = build_engine(config)

    # Checkpoint is used only for the paid/metered AI vision engine, so a re-run or a
    # crash mid-batch never re-spends quota on receipts already processed.
    use_cache = engine.consumes_image
    cache = checkpoint.load(config) if use_cache else {}

    total = len(files)
    rows: list[ExtractedReceipt] = []
    for i, path in enumerate(files, start=1):
        _notify(progress, i, total, path.name, None)   # "starting"
        content_hash = _hash_file(path)

        if use_cache and content_hash in cache:
            receipt = checkpoint.to_receipt(cache[content_hash])
            receipt.content_hash = content_hash
            receipt.warnings.insert(0, "loaded from checkpoint (not re-sent to AI)")
        else:
            receipt = _extract_one(engine, path, config, content_hash)
            # Only cache SUCCESSES — never persist a failure, so a re-run retries it.
            if use_cache and not receipt.extraction_failed:
                cache[content_hash] = checkpoint.to_dict(receipt)
                checkpoint.save(config, cache)   # save after each file: crash-safe

        rows.append(receipt)
        _notify(progress, i, total, path.name, receipt)   # "done"

    if config.deduplicate:
        rows = dedup.mark_duplicates(rows).rows
    return rows


def _notify(progress: Optional[ProgressFn], i: int, total: int, name: str,
            receipt: Optional[ExtractedReceipt]) -> None:
    if progress is not None:
        progress(i, total, name, receipt)


def _extract_one(engine, path: Path, config: Config, content_hash: str) -> ExtractedReceipt:
    """Run one file through the selected engine (image-based or text-based)."""
    if engine.consumes_image:
        receipt = engine.extract_image(path, source_file=path.name)
        receipt.content_hash = content_hash
        return normalizer.normalize(receipt)

    read = text_reader.read_text(path, config)
    if not read.ok:
        row = ExtractedReceipt(source_file=path.name, engine=config.engine,
                               content_hash=content_hash)
        row.warnings.append(read.error or "could not read any text")
        return row

    receipt = engine.extract(read.text, source_file=path.name)
    receipt.content_hash = content_hash
    receipt.warnings.insert(0, f"read via {read.method}")
    return normalizer.normalize(receipt)


def _hash_file(path: Path) -> str:
    """MD5 of the file's raw bytes — a stable fingerprint for exact-duplicate files.

    MD5 is used only for duplicate detection (not security), where its speed is the
    priority and collisions on real receipt files are not a practical concern.
    """
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

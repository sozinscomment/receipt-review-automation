# LOGIC HEADER
# Input:          A batch of uploaded receipt files (saved to a temp input folder) plus
#                 the vendored extractor package's Config/pipeline.
# Transformation: Point the extractor pipeline at the temp folder, run it (rule_based by
#                 default; ai_vision if AI_API_KEY is set in the environment), classify
#                 each resulting row as "flagged" (extraction failed OR marked as a
#                 duplicate) or "clean", and persist both a run summary and one row per
#                 flagged item to storage.
# Output:         process_batch() returns a dict summary (run_id, files_processed,
#                 flagged_count, duplicate_count) suitable for the API response and for
#                 n8n's flagged-count branch condition.

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from extractor.config import Config
from extractor import pipeline

from api.storage import FlaggedItem, Run, Storage

VENDOR_OUTPUT_DIR = Path("data/vendor_output")  # checkpoint file lives here if ai_vision is used


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_flagged(receipt) -> tuple[bool, str]:
    """Decide whether a receipt needs human review, and why.

    Three cases route to review: the engine explicitly errored
    (extraction_failed), the file was matched as a duplicate, or nothing
    usable came out of it at all (no total found) — which in practice means
    the file couldn't be read/OCR'd, even though no exception was raised.
    """
    if receipt.extraction_failed:
        detail = "; ".join(receipt.warnings) if receipt.warnings else "extraction_failed"
        return True, f"extraction_failed: {detail}"
    if receipt.duplicate_of:
        return True, f"duplicate_of: {receipt.duplicate_of}"
    if receipt.total is None:
        detail = "; ".join(receipt.warnings) if receipt.warnings else "no total extracted"
        return True, f"no_data_extracted: {detail}"
    return False, ""


def process_batch(files: list[tuple[str, BinaryIO]], storage: Storage,
                   engine: str = "rule_based") -> dict:
    """Save uploaded files to a scratch folder, run the extractor pipeline once, and
    record the outcome. `files` is a list of (filename, file-like-object) pairs, matching
    what FastAPI's UploadFile gives us — kept as plain tuples here so this function has
    no FastAPI import and stays independently testable."""
    with tempfile.TemporaryDirectory(prefix="review_batch_") as tmp:
        input_dir = Path(tmp)
        for name, fileobj in files:
            dest = input_dir / name
            with open(dest, "wb") as out:
                shutil.copyfileobj(fileobj, out)

        VENDOR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        config = Config.load().with_overrides(
            engine=engine,
            input_dir=input_dir,
            output_dir=VENDOR_OUTPUT_DIR,
        )
        receipts = pipeline.run(config)

    run = storage.create_run(Run(
        started_at=_now_iso(),
        files_processed=len(receipts),
        engine=engine,
    ))

    flagged_count = 0
    duplicate_count = 0
    for receipt in receipts:
        flagged, reason = _is_flagged(receipt)
        if receipt.duplicate_of:
            duplicate_count += 1
        if flagged:
            flagged_count += 1
            storage.create_flagged_item(FlaggedItem(
                run_id=run.id,
                source_file=receipt.source_file,
                vendor=receipt.vendor,
                date=receipt.date,
                total=receipt.total,
                reason=reason,
                created_at=_now_iso(),
            ))

    run.flagged_count = flagged_count
    run.duplicate_count = duplicate_count
    # SQLite has no easy "update dataclass in place" helper here — cheap direct update.
    with storage._conn() as conn:  # noqa: SLF001 (internal use within the same package)
        conn.execute(
            "UPDATE runs SET flagged_count = ?, duplicate_count = ? WHERE id = ?",
            (flagged_count, duplicate_count, run.id),
        )

    return {
        "run_id": run.id,
        "files_processed": run.files_processed,
        "flagged_count": flagged_count,
        "duplicate_count": duplicate_count,
    }

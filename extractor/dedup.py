# LOGIC HEADER
# Input:          The list of ExtractedReceipt rows produced by the pipeline (each
#                 already carrying a content_hash of its source file's bytes).
# Transformation: Detect duplicates automatically so no human has to pre-sort a pile.
#                 Two independent signals, checked in order against everything seen so
#                 far: (1) identical file bytes (same content_hash) — a certain
#                 duplicate, e.g. the same file saved twice; (2) an identical
#                 (vendor, date, total) fingerprint when ALL THREE were confidently
#                 extracted — the same purchase captured twice. The FIRST occurrence is
#                 kept as the original; later matches get duplicate_of set to point at
#                 it. Data is never deleted — duplicates are marked, not dropped, so an
#                 automated run can never silently lose a financial record.
# Output:         The same rows, with duplicate_of populated on detected duplicates,
#                 and a count of how many were flagged.

from __future__ import annotations

from dataclasses import dataclass

from extractor.engines.base import ExtractedReceipt


@dataclass
class DedupResult:
    rows: list[ExtractedReceipt]
    duplicate_count: int


def mark_duplicates(rows: list[ExtractedReceipt]) -> DedupResult:
    """Flag duplicate rows in place (by file bytes, then by extracted fingerprint)."""
    seen_hashes: dict[str, str] = {}          # content_hash -> original source_file
    seen_fingerprints: dict[tuple, str] = {}  # (vendor,date,total) -> original source_file
    duplicate_count = 0

    for row in rows:
        original = _match(row, seen_hashes, seen_fingerprints)
        if original is not None and original != row.source_file:
            row.duplicate_of = original
            row.warnings.append(f"duplicate of {original}")
            duplicate_count += 1
            continue

        # First time we've seen this file/fingerprint: record it as an original.
        if row.content_hash:
            seen_hashes.setdefault(row.content_hash, row.source_file)
        fp = _fingerprint(row)
        if fp is not None:
            seen_fingerprints.setdefault(fp, row.source_file)

    return DedupResult(rows=rows, duplicate_count=duplicate_count)


def _match(row: ExtractedReceipt, seen_hashes: dict, seen_fingerprints: dict):
    """Return the original file this row duplicates, or None."""
    if row.content_hash and row.content_hash in seen_hashes:
        return seen_hashes[row.content_hash]
    fp = _fingerprint(row)
    if fp is not None and fp in seen_fingerprints:
        return seen_fingerprints[fp]
    return None


def _fingerprint(row: ExtractedReceipt):
    """A comparable key for a receipt, ONLY when vendor+date+total are all present.

    Requiring all three avoids false merges: two blank/garbled receipts must never be
    treated as 'the same' just because they share missing fields.
    """
    if not row.vendor or not row.date or row.total is None:
        return None
    return (row.vendor.strip().lower(), row.date, round(float(row.total), 2))

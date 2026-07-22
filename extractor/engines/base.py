# LOGIC HEADER
# Input:          Raw receipt text (from text_reader) and the source filename.
# Transformation: Define the shared shape every extraction engine must produce, so
#                 the rest of the pipeline never cares which engine ran. This is the
#                 seam that lets a future AI engine drop in beside the rule-based one
#                 without any caller changing — the whole point of the design.
# Output:         An ExtractedReceipt dataclass + an abstract Extractor interface.

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineItem:
    description: str
    amount: Optional[float] = None


@dataclass
class ExtractedReceipt:
    source_file: str
    vendor: Optional[str] = None
    date: Optional[str] = None          # ISO 8601 (YYYY-MM-DD) once normalized
    total: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None
    line_items: list[LineItem] = field(default_factory=list)
    engine: str = "unknown"             # which engine produced this row
    warnings: list[str] = field(default_factory=list)
    content_hash: Optional[str] = None  # hash of the source file's bytes (set by pipeline)
    duplicate_of: Optional[str] = None  # source_file of the original, if this is a dup
    extraction_failed: bool = False     # True if the engine errored (don't cache these)

    def missing_fields(self) -> list[str]:
        """Key fields that came back empty — used to flag low-confidence rows."""
        missing = []
        for name in ("vendor", "date", "total"):
            if getattr(self, name) in (None, ""):
                missing.append(name)
        return missing


class Extractor(abc.ABC):
    """Every extraction engine implements this one method.

    consumes_image = False means the engine works on OCR'd text (the pipeline reads
    the file first). An image-consuming engine (consumes_image = True) receives the
    file path directly and implements extract_image() instead — used by AI vision,
    which reads the picture itself rather than OCR text.
    """

    name: str = "base"
    consumes_image: bool = False

    @abc.abstractmethod
    def extract(self, text: str, source_file: str) -> ExtractedReceipt:
        """Turn raw receipt text into a structured ExtractedReceipt."""
        raise NotImplementedError

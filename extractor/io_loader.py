# LOGIC HEADER
# Input:          A directory path to scan for receipt/invoice files.
# Transformation: Walk the directory (non-recursively) and collect every file whose
#                 extension is a supported PDF or image type, sorted for stable order.
# Output:         A list of pathlib.Path objects, one per supported file.

from __future__ import annotations

from pathlib import Path

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
                    ".heic", ".heif", ".webp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS


class InputError(Exception):
    """Raised when the input directory is missing or unusable."""


def discover_files(input_dir: Path) -> list[Path]:
    """Return supported receipt files directly inside input_dir, sorted by name."""
    if not input_dir.exists():
        raise InputError(f"input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise InputError(f"input path is not a directory: {input_dir}")

    files = [
        p for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return files


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTENSIONS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS

# LOGIC HEADER
# Input:          A single receipt/invoice file path (PDF or image) and the Config
#                 (for OCR language and DPI).
# Transformation: Turn the file into raw text. For a PDF, first try direct text
#                 extraction (fast, free, exact); if the page carries no real text
#                 (a scanned/photographed PDF), render it to an image and OCR it.
#                 For an image file, OCR it directly. OCR needs the system Tesseract
#                 (and Poppler for PDFs); if those are absent the failure is reported
#                 clearly rather than crashing the whole run.
# Output:         A ReadResult: the extracted text plus how it was obtained, or an
#                 error string explaining why nothing could be read.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from extractor import io_loader
from extractor.config import Config

# Teach Pillow to open Apple HEIC/HEIF photos (the iPhone default format). This is a
# one-time registration; if pillow-heif isn't installed, HEIC files simply fail to
# open with a clear message rather than crashing the run.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - depends on optional dependency being present
    pass

# Below this many characters of directly-extracted PDF text, we assume the PDF is
# effectively image-only (scanned) and fall back to OCR.
_MIN_PDF_TEXT_CHARS = 20


@dataclass
class ReadResult:
    text: str
    method: str                    # "pdf_text" | "pdf_ocr" | "image_ocr"
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


def read_text(path: Path, config: Config) -> ReadResult:
    """Extract raw text from a supported receipt file."""
    try:
        if io_loader.is_pdf(path):
            return _read_pdf(path, config)
        if io_loader.is_image(path):
            return ReadResult(text=_ocr_image_file(path, config), method="image_ocr")
        return ReadResult(text="", method="unknown",
                          error=f"unsupported file type: {path.suffix}")
    except _OcrUnavailable as exc:
        return ReadResult(text="", method="ocr_unavailable", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - report the file's failure, keep the run alive
        return ReadResult(text="", method="error", error=f"{type(exc).__name__}: {exc}")


def _read_pdf(path: Path, config: Config) -> ReadResult:
    import pdfplumber

    direct_text_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            direct_text_parts.append(page.extract_text() or "")
    direct_text = "\n".join(direct_text_parts).strip()

    if len(direct_text) >= _MIN_PDF_TEXT_CHARS:
        return ReadResult(text=direct_text, method="pdf_text")

    # Scanned/image-only PDF: render each page to an image and OCR it.
    ocr_text = _ocr_pdf_pages(path, config)
    return ReadResult(text=ocr_text, method="pdf_ocr")


class _OcrUnavailable(Exception):
    """Raised when a system OCR dependency (Tesseract/Poppler) is missing."""


def _ocr_image_file(path: Path, config: Config) -> str:
    pytesseract, Image = _import_ocr_stack()
    try:
        with Image.open(path) as img:
            prepared = _prepare(img, config)
            return pytesseract.image_to_string(prepared, lang=config.ocr_language)
    except pytesseract.TesseractNotFoundError as exc:  # type: ignore[attr-defined]
        raise _OcrUnavailable(
            "Tesseract OCR is not installed. See the README's Installation section."
        ) from exc


def _prepare(img, config: Config):
    """Preprocess an image for OCR, or just normalize it if preprocessing is off.

    Even when preprocessing is disabled we convert to RGB, because formats like HEIC
    open as a HEIF-backed image that Tesseract won't accept directly.
    """
    if config.preprocess_images:
        from extractor import preprocess
        return preprocess.prepare_for_ocr(img, config)
    return img.convert("RGB")


def _ocr_pdf_pages(path: Path, config: Config) -> str:
    pytesseract, _ = _import_ocr_stack()
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise _OcrUnavailable("pdf2image is not installed (pip install -r requirements.txt).") from exc

    try:
        images = convert_from_path(str(path), dpi=config.ocr_dpi)
    except Exception as exc:  # pdf2image raises if Poppler is missing
        raise _OcrUnavailable(
            "Could not render the PDF for OCR. This usually means Poppler is not "
            "installed. See the README's Installation section."
        ) from exc

    parts = []
    for img in images:
        try:
            parts.append(pytesseract.image_to_string(_prepare(img, config),
                                                      lang=config.ocr_language))
        except pytesseract.TesseractNotFoundError as exc:  # type: ignore[attr-defined]
            raise _OcrUnavailable(
                "Tesseract OCR is not installed. See the README's Installation section."
            ) from exc
    return "\n".join(parts)


def _import_ocr_stack():
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise _OcrUnavailable(
            "OCR libraries missing. Run: pip install -r requirements.txt"
        ) from exc
    return pytesseract, Image

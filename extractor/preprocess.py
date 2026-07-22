# LOGIC HEADER
# Input:          A freshly-opened PIL image (any mode/format, incl. HEIC) and the Config.
# Transformation: Clean the image so OCR reads it better — the biggest wins for phone
#                 photos of receipts: (1) honor EXIF orientation, (2) normalize to
#                 grayscale, (3) auto-rotate sideways/upside-down photos in 90-degree
#                 steps using Tesseract's orientation detector, (4) stretch contrast so
#                 faded receipts get crisper. Each step is defensive: if a step can't
#                 run (e.g. OSD finds too little text), it is skipped rather than failing
#                 the whole file. Nothing here fabricates content — it only makes the
#                 existing marks easier to recognize.
# Output:         A grayscale PIL image ready to hand to Tesseract.

from __future__ import annotations

from extractor.config import Config


def prepare_for_ocr(img, config: Config):
    """Return an OCR-optimized grayscale copy of a PIL image."""
    from PIL import ImageOps

    # 1. Honor EXIF orientation. Phone cameras often store the photo un-rotated and
    #    tag the intended rotation in metadata; this bakes that rotation into pixels.
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001 - orientation is best-effort, never fatal
        pass

    # 2. Normalize any exotic mode (HEIF-backed, CMYK, palette) to plain grayscale.
    work = img.convert("RGB").convert("L")

    # 3. Coarse auto-rotate (0/90/180/270) using Tesseract's orientation detection.
    if config.ocr_auto_rotate:
        degrees = _detect_rotation(work, config)
        if degrees:
            # OSD "Rotate: N" = clockwise degrees needed to make the page upright.
            # PIL rotates counter-clockwise, so negate; expand to avoid cropping.
            work = work.rotate(-degrees, expand=True, fillcolor=255)

    # 4. Stretch contrast so faded ink / low-light photos become crisper for OCR.
    work = ImageOps.autocontrast(work)
    return work


def _detect_rotation(img, config: Config) -> int:
    """Ask Tesseract which way the page is turned; return degrees (0/90/180/270)."""
    import pytesseract

    try:
        osd = pytesseract.image_to_osd(img)
    except Exception:  # noqa: BLE001 - OSD fails on sparse/blurry pages; treat as 0
        return 0
    return _parse_osd_rotation(osd)


def _parse_osd_rotation(osd_text: str) -> int:
    """Extract the 'Rotate: N' value from Tesseract OSD output, defaulting to 0."""
    for line in osd_text.splitlines():
        if line.strip().startswith("Rotate:"):
            try:
                deg = int(line.split(":", 1)[1].strip())
            except ValueError:
                return 0
            return deg % 360
    return 0

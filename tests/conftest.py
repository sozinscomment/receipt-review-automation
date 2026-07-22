# LOGIC HEADER
# Input:          Nothing.
# Transformation: Shared pytest fixtures — a temp working directory each test runs
#                 in (so storage.py's default relative "data/" path and the vendored
#                 extractor's checkpoint file never touch the real project folder),
#                 and a helper to draw simple synthetic receipt PNGs for OCR tests.
# Output:         `isolated_cwd` and `make_receipt_image` fixtures.

import os
from pathlib import Path

import pytest


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def make_receipt_image():
    def _make(path: Path, vendor: str, date: str, total: str):
        from PIL import Image, ImageDraw, ImageFont

        lines = [vendor, f"Date: {date}", "Item A          5.00", "Item B          3.00",
                 f"TOTAL          {total}"]
        img = Image.new("RGB", (420, 40 + 26 * len(lines)), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        y = 20
        for line in lines:
            draw.text((20, y), line, fill="black", font=font)
            y += 26
        img.save(path)
        return path
    return _make

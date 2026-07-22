# LOGIC HEADER
# Input:          An optional path to config.yaml, plus environment variables
#                 (AI_PROVIDER, AI_API_KEY, AI_MODEL) loaded from a .env file if present.
# Transformation: Merge YAML settings with sane defaults, validate them, and read
#                 AI credentials from the environment ONLY (never from the YAML, so a
#                 secret can never be committed). Expose everything as one frozen object.
# Output:         An immutable Config used by every other module.

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

import yaml

ENGINES = ("rule_based", "ai", "ai_vision")
OUTPUT_FORMATS = ("xlsx", "csv")

_DEFAULTS = {
    "engine": "rule_based",
    "input_dir": "samples/receipts",
    "output_dir": "output",
    "output_format": "xlsx",
    "ocr_language": "eng",
    "ocr_dpi": 300,
    "preprocess_images": True,
    "ocr_auto_rotate": True,
    "currency_symbols": ["$", "£", "€", "₱", "¥"],
    "date_dayfirst": False,
    "deduplicate": True,
    "ai_requests_per_minute": 10,   # pace AI calls under the free-tier limit
    "ai_max_retries": 5,            # retries (with backoff) on rate-limit/transient errors
    "ai_timeout_seconds": 120,      # how long to wait for one AI response before retrying
}


class ConfigError(ValueError):
    """Raised for any invalid or unrecognized configuration value."""


@dataclass(frozen=True)
class Config:
    engine: str
    input_dir: Path
    output_dir: Path
    output_format: str
    ocr_language: str
    ocr_dpi: int
    preprocess_images: bool
    ocr_auto_rotate: bool
    currency_symbols: tuple[str, ...]
    date_dayfirst: bool
    deduplicate: bool
    ai_requests_per_minute: float
    ai_max_retries: int
    ai_timeout_seconds: float
    # AI credentials — sourced from the environment, never persisted to disk by us.
    ai_provider: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None

    @property
    def ai_enabled(self) -> bool:
        """AI is usable only when the engine is 'ai' AND a key was supplied."""
        return self.engine == "ai" and bool(self.ai_api_key)

    @classmethod
    def load(cls, yaml_path: Optional[str | Path] = None) -> "Config":
        data = dict(_DEFAULTS)
        if yaml_path is not None:
            path = Path(yaml_path)
            if not path.exists():
                raise ConfigError(f"config file not found: {path}")
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            unknown = set(loaded) - set(_DEFAULTS)
            if unknown:
                raise ConfigError(f"unrecognized config field(s): {sorted(unknown)}")
            data.update(loaded)

        _require(data["engine"] in ENGINES,
                 f"engine must be one of {ENGINES}, got {data['engine']!r}")
        _require(data["output_format"] in OUTPUT_FORMATS,
                 f"output_format must be one of {OUTPUT_FORMATS}, got {data['output_format']!r}")
        _require(int(data["ocr_dpi"]) > 0, "ocr_dpi must be a positive integer")

        # AI credentials come from the environment only (loaded from .env by main.py).
        ai_key = os.environ.get("AI_API_KEY") or None

        return cls(
            engine=str(data["engine"]),
            input_dir=Path(str(data["input_dir"])),
            output_dir=Path(str(data["output_dir"])),
            output_format=str(data["output_format"]),
            ocr_language=str(data["ocr_language"]),
            ocr_dpi=int(data["ocr_dpi"]),
            preprocess_images=bool(data["preprocess_images"]),
            ocr_auto_rotate=bool(data["ocr_auto_rotate"]),
            currency_symbols=tuple(data["currency_symbols"]),
            date_dayfirst=bool(data["date_dayfirst"]),
            deduplicate=bool(data["deduplicate"]),
            ai_requests_per_minute=float(data["ai_requests_per_minute"]),
            ai_max_retries=int(data["ai_max_retries"]),
            ai_timeout_seconds=float(data["ai_timeout_seconds"]),
            ai_provider=(os.environ.get("AI_PROVIDER") or None),
            ai_api_key=ai_key,
            ai_model=(os.environ.get("AI_MODEL") or None),
        )

    def with_overrides(self, **kwargs) -> "Config":
        """Return a copy with specific fields replaced (used by the CLI/tests)."""
        return replace(self, **kwargs)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)

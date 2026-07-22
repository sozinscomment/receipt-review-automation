# LOGIC HEADER
# Input:          Raw receipt text, the source filename, and AI credentials that the
#                 END USER supplies via environment variables (provider, API key, model).
# Transformation: This is the "bring your own key" slot. When a user has pasted their
#                 own API key into .env, this engine would send the receipt text to
#                 their chosen provider and parse the structured JSON reply. By default
#                 NO KEY IS SET, so this engine is never invoked and NO paid call is
#                 ever made — the tool stays free to run. The provider call itself is
#                 deliberately left as a single, clearly-marked method to implement,
#                 so wiring a real API later is an additive change, not a rewrite.
# Output:         An ExtractedReceipt, or a clear error if AI was selected without a key.

from __future__ import annotations

from typing import Optional

from extractor.engines.base import ExtractedReceipt, Extractor
from extractor.engines._parsing import parse_receipt_json

# The instruction the AI would be given. Kept here so it is easy to tune later.
_EXTRACTION_PROMPT = (
    "You are a receipt parser. Read the receipt text and return ONLY a JSON object "
    "with keys: vendor (string), date (YYYY-MM-DD), total (number), tax (number), "
    "currency (string), line_items (array of {description, amount}). Use null for "
    "anything you cannot find. Do not add commentary."
)


class AIExtractionNotConfigured(Exception):
    """Raised when the AI engine is selected but no user API key is available."""


class AIExtractor(Extractor):
    name = "ai"

    def __init__(self, provider: Optional[str], api_key: Optional[str],
                 model: Optional[str] = None) -> None:
        self._provider = (provider or "openai").lower()
        self._api_key = api_key
        self._model = model

    def extract(self, text: str, source_file: str) -> ExtractedReceipt:
        if not self._api_key:
            # This is the guard that keeps the tool free: no key -> no call.
            raise AIExtractionNotConfigured(
                "The AI engine is selected but no API key was provided. Add your own "
                "key to .env (AI_API_KEY=...) or set engine: rule_based in config.yaml."
            )
        raw_json = self._call_provider(text)          # <-- the one seam to implement
        return self._parse_response(raw_json, source_file)

    # ------------------------------------------------------------------
    # THE ONLY PART TO IMPLEMENT WHEN YOU ADD REAL AI.
    # Wire this to the user's provider using self._provider / self._api_key /
    # self._model and return the model's raw JSON string. Everything above and
    # below this method already works, so adding AI is purely additive.
    # ------------------------------------------------------------------
    def _call_provider(self, text: str) -> str:
        raise NotImplementedError(
            "AI provider call is not implemented yet. This is the intended plug-in "
            "point: send `_EXTRACTION_PROMPT` + the receipt text to the user's "
            "provider and return the JSON string reply. Until then, use the free "
            "rule_based engine (the default)."
        )

    # ------------------------------------------------------------------
    def _parse_response(self, raw_json: str, source_file: str) -> ExtractedReceipt:
        """Turn the provider's JSON reply into an ExtractedReceipt (shared parser)."""
        return parse_receipt_json(raw_json, source_file, self.name)

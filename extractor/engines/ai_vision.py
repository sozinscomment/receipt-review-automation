# LOGIC HEADER
# Input:          A receipt FILE (image or PDF) and the user's own free Gemini API key
#                 (from the environment). Rate/retry settings come from Config.
# Transformation: Read the receipt as a picture — convert it to JPEG (handling HEIC and
#                 rendering PDF pages) — and ask Google's Gemini vision model to return a
#                 JSON object of vendor/date/total/tax/line_items. Unlike OCR+rules, the
#                 model SEES the receipt, so it isn't fooled by an ID number that looks
#                 like a total. Calls are paced to stay under the free-tier per-minute
#                 limit, and a rate-limit/transient error is retried with exponential
#                 backoff. With NO key set, the engine refuses (keeping the tool free) —
#                 the actual network call is the one part verified by the user, not in
#                 the test suite.
# Output:         An ExtractedReceipt per file.

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

from extractor.config import Config
from extractor.engines._parsing import parse_receipt_json
from extractor.engines._ratelimit import RateLimiter, backoff_delay
from extractor.engines.ai_engine import AIExtractionNotConfigured
from extractor.engines.base import ExtractedReceipt, Extractor

_PROMPT = (
    "You are a receipt/invoice parser. Look at the image and return ONLY a JSON object "
    "with keys: vendor (string), date (YYYY-MM-DD), total (number, the grand total the "
    "customer paid — NOT a tax id, order number, or reference number), tax (number), "
    "currency (string), line_items (array of {description, amount}). Use null for "
    "anything not present. Return only the JSON, no commentary or code fences."
)

_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")
# "gemini-flash-latest" is an alias that always resolves to Google's current
# recommended flash model, so it never deprecates out from under us (specific older
# versions like gemini-2.0-flash / gemini-2.5-flash get retired or dropped from the
# free tier over time). Override per-user with AI_MODEL in .env.
_DEFAULT_MODEL = "gemini-flash-latest"


class AIRequestError(Exception):
    """A systemic AI request failure (bad key, no access, quota) — abort the run."""


class AIVisionExtractor(Extractor):
    name = "ai_vision"
    consumes_image = True

    def __init__(self, api_key: Optional[str], model: Optional[str],
                 config: Config, rate_limiter: Optional[RateLimiter] = None) -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_MODEL
        self._config = config
        self._max_retries = config.ai_max_retries
        self._limiter = rate_limiter or RateLimiter(per_minute=config.ai_requests_per_minute)
        self._had_success = False   # once any file succeeds, later failures only flag that file

    # Text-engine interface method; not used by a vision engine.
    def extract(self, text: str, source_file: str) -> ExtractedReceipt:  # pragma: no cover
        raise NotImplementedError("AIVisionExtractor consumes images, not text.")

    def extract_image(self, path: Path, source_file: str) -> ExtractedReceipt:
        if not self._api_key:
            raise AIExtractionNotConfigured(
                "The AI vision engine is selected but no API key was provided. Get a free "
                "key from Google AI Studio, put it in .env (AI_API_KEY=...), or switch "
                "engine back to rule_based in config.yaml."
            )
        jpeg_images = self._file_to_jpegs(path)
        if not jpeg_images:
            r = ExtractedReceipt(source_file=source_file, engine=self.name)
            r.warnings.append("could not render file to an image for vision")
            r.extraction_failed = True
            return r

        text, status, message = self._call_with_retries(jpeg_images)
        if text is not None:
            self._had_success = True
            return parse_receipt_json(text, source_file, self.name)

        # The request failed. If NOTHING has succeeded yet, this is almost certainly a
        # systemic problem (wrong/kes-less key, API not enabled, quota) that will hit
        # every file — so stop now with the real error instead of grinding all 44.
        detail = f"HTTP {status}: {message}" if status else message
        if not self._had_success:
            raise AIRequestError(
                f"The AI vision request failed on the first receipt — {detail}. "
                "Nothing else was sent. Common causes: the API key is wrong or lacks "
                "access, the Generative Language API isn't enabled for the key's Google "
                "project, or the free-tier quota is exhausted. No further quota was used."
            )
        # We've had successes, so treat this as a one-off bad file: flag and continue.
        r = ExtractedReceipt(source_file=source_file, engine=self.name)
        r.warnings.append(f"AI vision failed for this file — {detail}")
        r.extraction_failed = True
        return r

    # ------------------------------------------------------------------
    # File -> JPEG bytes (handles HEIC via pillow-heif; renders PDF pages).
    # ------------------------------------------------------------------
    def _file_to_jpegs(self, path: Path) -> list[bytes]:
        import io

        from PIL import Image
        try:  # ensure HEIC support is registered
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        images = []
        if path.suffix.lower() == ".pdf":
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(str(path), dpi=self._config.ocr_dpi)
            except Exception:
                return []
        else:
            try:
                images = [Image.open(path)]
            except Exception:
                return []

        out: list[bytes] = []
        for img in images:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            out.append(buf.getvalue())
        return out

    # ------------------------------------------------------------------
    # Paced, retried network call. This is the seam verified live by the user.
    # ------------------------------------------------------------------
    def _call_with_retries(self, jpeg_images: list[bytes]):
        """Return (text|None, last_status, last_message). Retries 429/5xx with backoff."""
        last_status = 0
        last_message = "no response"
        for attempt in range(self._max_retries + 1):
            self._limiter.wait()
            status, body = self._post(jpeg_images)
            last_status = status
            last_message = _error_message(body) if status != 200 else ""
            if status == 200:
                text = self._extract_text_from_response(body)
                if text is not None:
                    return text, status, ""
                last_message = "response contained no text"
                break
            # status 0 = a network error/timeout (no HTTP response); 429/5xx = rate
            # limit or transient server error. All are worth retrying with backoff.
            if status == 0 or status == 429 or 500 <= status < 600:
                if attempt < self._max_retries:
                    self._limiter._sleep(backoff_delay(attempt))
                    continue
            # Non-retryable error (bad key/request) or retries exhausted: stop.
            break
        return None, last_status, last_message

    def _post(self, jpeg_images: list[bytes]) -> tuple[int, dict]:
        import requests

        parts = [{"text": _PROMPT}]
        for data in jpeg_images:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(data).decode("ascii"),
                }
            })
        payload = {"contents": [{"parts": parts}]}
        url = _ENDPOINT.format(model=self._model)
        try:
            # (connect timeout, read timeout). A slow model reply hits the read timeout;
            # we return status 0 so the caller retries instead of crashing.
            resp = requests.post(url, params={"key": self._api_key}, json=payload,
                                 timeout=(15, self._config.ai_timeout_seconds))
        except requests.exceptions.RequestException as exc:
            return 0, {"error": {"message": f"network error: {exc}"}}
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return resp.status_code, body

    def _extract_text_from_response(self, body: dict) -> Optional[str]:
        try:
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None


def list_available_models(api_key: str) -> tuple[int, list[str], str]:
    """Ask Gemini which models this key can use for generateContent (vision-capable).

    Returns (http_status, model_ids, error_message). A diagnostic helper — lets a user
    see exactly what their own key supports instead of guessing at model names.
    """
    import requests

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        resp = requests.get(url, params={"key": api_key}, timeout=30)
    except Exception as exc:  # noqa: BLE001 - network failure reported, not raised
        return 0, [], f"could not reach Google: {exc}"
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200:
        return resp.status_code, [], _error_message(body)

    models = []
    for m in body.get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            models.append(str(m.get("name", "")).replace("models/", ""))
    return 200, models, ""


def _error_message(body: dict) -> str:
    """Pull a human-readable error out of a Gemini error response body."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err.get("message") or err.get("status") or str(err)
        if err:
            return str(err)
    return "no error detail returned"

# LOGIC HEADER
# Input:          Raw receipt/invoice text and the source filename, plus the set of
#                 currency symbols to recognize (from Config).
# Transformation: Parse structure out of messy text using ordered heuristics — find
#                 labelled totals/tax first (most reliable), fall back to the largest
#                 currency amount for the total; sniff a date in several common formats;
#                 guess the vendor from the first meaningful line; collect priced line
#                 items. Every guess is recorded; nothing here calls a paid service.
# Output:         An ExtractedReceipt with whatever could be confidently parsed, plus
#                 warnings describing any fallback or failure.

from __future__ import annotations

import re
from typing import Optional

from extractor.engines.base import ExtractedReceipt, Extractor, LineItem


def _iso_or_none(year, month, day) -> Optional[str]:
    """Return a valid ISO date string, or None if the components are out of range."""
    try:
        y, mo, d = int(year), int(month), int(day)
    except (TypeError, ValueError):
        return None
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"

# Words that, on a line, strongly indicate that line's amount is the grand total.
_TOTAL_LABELS = ("grand total", "total due", "amount due", "balance due", "total")
_TAX_LABELS = ("tax", "vat", "gst", "sales tax")
# Lines matching these are structural noise, never a vendor name.
_VENDOR_SKIP = ("receipt", "invoice", "tax invoice", "order", "date", "time")


class RuleBasedExtractor(Extractor):
    name = "rule_based"

    def __init__(self, currency_symbols: tuple[str, ...] = ("$",),
                 date_dayfirst: bool = False) -> None:
        self._symbols = tuple(currency_symbols)
        # For a numeric date where BOTH parts are <= 12 (e.g. 07/08/2026) the order
        # is genuinely ambiguous. date_dayfirst decides: True -> DD/MM, False -> MM/DD.
        # When one part is > 12 the order is unambiguous and this flag is ignored.
        self._dayfirst = date_dayfirst
        # A regex fragment matching any configured currency symbol.
        symbol_class = "".join(re.escape(s) for s in currency_symbols)
        # Matches "$1,234.56", "1234.56", "£ 99.00", etc. Captures symbol + number.
        self._amount_re = re.compile(
            rf"(?P<sym>[{symbol_class}])?\s*(?P<num>\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{1,2}})?|\d+(?:\.\d{{1,2}})?)"
        )

    def extract(self, text: str, source_file: str) -> ExtractedReceipt:
        result = ExtractedReceipt(source_file=source_file, engine=self.name)
        if not text or not text.strip():
            result.warnings.append("no text to parse")
            return result

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        result.currency = self._detect_currency(text)
        result.total = self._find_labelled_amount(lines, _TOTAL_LABELS)
        result.tax = self._find_labelled_amount(lines, _TAX_LABELS)
        result.date = self._find_date(text)
        result.vendor = self._find_vendor(lines)
        result.line_items = self._find_line_items(lines)

        if result.total is None:
            fallback = self._largest_amount(text)
            if fallback is not None:
                result.total = fallback
                result.warnings.append("total not labelled; used largest amount on receipt")
        for missing in result.missing_fields():
            result.warnings.append(f"could not find {missing}")
        return result

    # --- currency ---------------------------------------------------------
    def _detect_currency(self, text: str) -> Optional[str]:
        for sym in self._symbols:
            if sym in text:
                return sym
        return None

    # --- amounts ----------------------------------------------------------
    def _parse_amount(self, raw: str) -> Optional[float]:
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            return None

    def _find_labelled_amount(self, lines: list[str], labels: tuple[str, ...]) -> Optional[float]:
        """Return the amount on the last line whose text contains one of `labels`.

        Last match wins because receipts often repeat a label (e.g. 'subtotal' then
        'total'), and the final labelled occurrence is typically the definitive one.
        """
        found: Optional[float] = None
        for line in lines:
            low = line.lower()
            if any(label in low for label in labels):
                # Avoid matching 'subtotal' when we asked for 'total'? 'subtotal'
                # contains 'total', so only accept if not clearly a subtotal line.
                if "total" in labels and "subtotal" in low and "grand total" not in low:
                    continue
                amounts = self._all_amounts(line)
                if amounts:
                    found = amounts[-1]
        return found

    def _all_amounts(self, text: str) -> list[float]:
        out = []
        for m in self._amount_re.finditer(text):
            val = self._parse_amount(m.group("num"))
            # Require either a currency symbol or a decimal point to count as money,
            # so we don't treat quantities/dates as amounts.
            if val is not None and (m.group("sym") or "." in m.group("num")):
                out.append(val)
        return out

    def _largest_amount(self, text: str) -> Optional[float]:
        amounts = self._all_amounts(text)
        return max(amounts) if amounts else None

    # --- date -------------------------------------------------------------
    def _find_date(self, text: str) -> Optional[str]:
        # Ordered (regex, parser) pairs. First confident hit wins.
        patterns = [
            (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
             lambda m: _iso_or_none(m.group(1), m.group(2), m.group(3))),
            (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
             lambda m: self._parse_numeric_dmy(m.group(1), m.group(2), m.group(3))),
            (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"),
             lambda m: self._parse_numeric_dmy(m.group(1), m.group(2), m.group(3))),
            (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"),
             self._parse_textual_date),
            (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"),
             self._parse_textual_date_mdy),
        ]
        for regex, parser in patterns:
            m = regex.search(text)
            if m:
                parsed = parser(m)
                if parsed:
                    return parsed
        return None

    def _parse_numeric_dmy(self, a: str, b: str, year: str) -> Optional[str]:
        """Parse a two-number date (a/b/year) into ISO, disambiguating day vs month.

        Rules, in order: if one part is > 12 it can only be the day (the other is the
        month); if both are <= 12 the order is ambiguous, so honor self._dayfirst.
        An impossible date (e.g. month 14, day 40) returns None rather than garbage.
        """
        x, y = int(a), int(b)
        if x > 12 and y <= 12:
            day, month = x, y
        elif y > 12 and x <= 12:
            month, day = x, y
        else:
            # Both <= 12 (ambiguous) or both invalid: fall back to configured order.
            day, month = (x, y) if self._dayfirst else (y, x)
        return _iso_or_none(year, month, day)

    _MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    def _parse_textual_date(self, m: re.Match) -> Optional[str]:
        day, month_name, year = m.group(1), m.group(2)[:3].lower(), m.group(3)
        month = self._MONTHS.get(month_name)
        return _iso_or_none(year, month, day) if month else None

    def _parse_textual_date_mdy(self, m: re.Match) -> Optional[str]:
        month_name, day, year = m.group(1)[:3].lower(), m.group(2), m.group(3)
        month = self._MONTHS.get(month_name)
        return _iso_or_none(year, month, day) if month else None

    # --- vendor -----------------------------------------------------------
    def _find_vendor(self, lines: list[str]) -> Optional[str]:
        """First non-noise line near the top is usually the business name."""
        for line in lines[:6]:
            low = line.lower()
            if any(skip in low for skip in _VENDOR_SKIP):
                continue
            if self._all_amounts(line):        # a line that's mostly a number isn't a name
                continue
            letters = sum(c.isalpha() for c in line)
            if letters >= 3:
                return line
        return None

    # --- line items -------------------------------------------------------
    def _find_line_items(self, lines: list[str]) -> list[LineItem]:
        """A priced item line: some description text ending in a money amount."""
        items: list[LineItem] = []
        for line in lines:
            low = line.lower()
            if any(label in low for label in _TOTAL_LABELS + _TAX_LABELS):
                continue
            if "subtotal" in low:
                continue
            money = list(self._money_matches(line))
            if not money:
                continue
            # Description = everything before the LAST money amount on the line, so a
            # quantity like "5kg" in the middle of the description is preserved.
            last = money[-1]
            desc = line[: last.start()].strip(" .:-\t")
            if desc and sum(c.isalpha() for c in desc) >= 2:
                items.append(LineItem(description=desc, amount=self._parse_amount(last.group("num"))))
        return items

    def _money_matches(self, text: str):
        """Yield regex matches that are genuine money (have a symbol or a decimal)."""
        for m in self._amount_re.finditer(text):
            if m.group("sym") or "." in m.group("num"):
                yield m

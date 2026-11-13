"""
ISIN -> coupon and maturity date.

There is no free official data feed for this in India, so this module works in two layers:

1. parse_bond_text(text)   Reads coupon, maturity date, face value and payment frequency out of ANY
                           bond page text (copied from IndiaBonds, Groww, your broker app, a term
                           sheet...). Pure Python, tested.
2. lookup_isin(isin)       Best effort. Searches the web for the ISIN, opens the public bond pages it
                           finds, and runs the same parser. It can fail (site blocks, layout change,
                           no network), so the app always shows the source and lets you correct values.
Only the standard library is used.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

ISIN_RE = re.compile(r"^IN[A-Z0-9]{10}$")


def valid_isin(isin: str) -> bool:
    """Format and check-digit test (the standard ISIN Luhn check)."""
    isin = (isin or "").strip().upper()
    if not ISIN_RE.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            n = n // 10 + n % 10
        total += n
    return total % 10 == 0


@dataclass
class BondInfo:
    coupon: Optional[float] = None          # percent, e.g. 9.5
    maturity: Optional[date] = None
    face_value: Optional[float] = None
    frequency: Optional[str] = None
    source: str = ""

    @property
    def complete(self) -> bool:
        return self.coupon is not None and self.maturity is not None


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

_DATE_PATTERNS = [
    (re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"), "dmy"),
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), "ymd"),
    (re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-,]+([A-Za-z]{3})[A-Za-z]*\.?[\s\-,]+(\d{4})"), "dMy"),
    (re.compile(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"), "Mdy"),
]


def _to_date(kind: str, a: str, b: str, c: str) -> Optional[date]:
    try:
        if kind == "dmy":
            return date(int(c), int(b), int(a))
        if kind == "ymd":
            return date(int(a), int(b), int(c))
        if kind == "dMy":
            return date(int(c), MONTHS[b.lower()[:3]], int(a))
        if kind == "Mdy":
            return date(int(c), MONTHS[a.lower()[:3]], int(b))
    except (ValueError, KeyError):
        return None
    return None


def _first_date(text: str) -> Optional[date]:
    best = None
    for rx, kind in _DATE_PATTERNS:
        m = rx.search(text)
        if m:
            d = _to_date(kind, *m.groups())
            if d and (best is None or m.start() < best[0]):
                best = (m.start(), d)
    return best[1] if best else None


def parse_bond_text(text: str) -> BondInfo:
    """Pull coupon, maturity, face value and frequency out of page text. Missing items stay None."""
    t = re.sub(r"[ \t ]+", " ", text or "")
    info = BondInfo()

    # Coupon: label, then a percentage within a short distance
    m = re.search(r"coupon(?:\s*rate)?(?:\s*\(returns\))?\s*(?:\(.*?\))?[^0-9\n]{0,25}?(?<![\d.])(\d{1,2}(?:\.\d{1,4})?)\s*%",
                  t, re.I)
    if not m:
        m = re.search(r"coupon(?:\s*rate)?[^0-9]{0,40}?(?<![\d.])(\d{1,2}(?:\.\d{1,4})?)(?![\d.]\d*)\s*%?", t, re.I)
    if m:
        v = float(m.group(1))
        if 0 < v <= 30:
            info.coupon = v

    # Maturity: label (several spellings), then the first date that follows
    for label in (r"date\s+of\s+maturity", r"maturity\s+date", r"redemption\s+date",
                  r"date\s+of\s+redemption", r"matures?\s+on", r"maturity"):
        for lm in re.finditer(label, t, re.I):
            window = t[lm.end(): lm.end() + 60]
            d = _first_date(window)
            if d:
                info.maturity = d
                break
        if info.maturity:
            break

    m = re.search(r"face\s*value[^0-9]{0,20}?([\d,]+(?:\.\d+)?)", t, re.I)
    if m:
        try:
            info.face_value = float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = re.search(r"(?:interest|coupon)\s*(?:payment)?\s*(?:frequency)?[^A-Za-z]{0,10}"
                  r"(monthly|quarterly|half[\s-]?yearly|semi[\s-]?annual|annual(?:ly)?|yearly|cumulative|"
                  r"at\s+maturity)", t, re.I)
    if m:
        info.frequency = m.group(1).lower()
    return info


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|td|th)>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


# ----------------------------------------------------------------------------
# Fetching (best effort, cannot be unit-tested offline)
# ----------------------------------------------------------------------------

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9"}


def _get(url: str, timeout: float = 12.0) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000).decode("utf-8", "ignore")


def _candidate_urls(isin: str, limit: int = 8) -> List[str]:
    q = urllib.parse.quote(f"{isin} bond coupon rate maturity date")
    page = _get(f"https://html.duckduckgo.com/html/?q={q}")
    urls = []
    for m in re.finditer(r'href="([^"]+)"', page):
        u = html.unescape(m.group(1))
        if "uddg=" in u:
            u = urllib.parse.unquote(u.split("uddg=", 1)[1].split("&", 1)[0])
        if u.startswith("http") and "duckduckgo.com" not in u and u not in urls:
            urls.append(u)
    urls.sort(key=lambda u: isin.lower() not in u.lower())     # pages with the ISIN in the URL first
    return urls[:limit]


@dataclass
class LookupResult:
    found: List[BondInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def best(self) -> Optional[BondInfo]:
        return self.found[0] if self.found else None

    @property
    def sources_agree(self) -> bool:
        return len({(b.coupon, b.maturity) for b in self.found}) <= 1


def lookup_isin(isin: str, max_pages: int = 5) -> LookupResult:
    """Search for the ISIN, read the pages found, keep pages that mention the ISIN and give both values."""
    res = LookupResult()
    isin = isin.strip().upper()
    try:
        urls = _candidate_urls(isin)
    except Exception as e:      # network blocked, DNS, timeout...
        res.errors.append(f"Search failed: {type(e).__name__}: {e}")
        return res
    if not urls:
        res.errors.append("The search returned no pages.")
    for u in urls[:max_pages]:
        try:
            text = html_to_text(_get(u))
        except Exception as e:
            res.errors.append(f"{urllib.parse.urlparse(u).netloc}: {type(e).__name__}")
            continue
        if isin not in text.upper() and isin.lower() not in u.lower():
            continue            # page is about some other bond
        info = parse_bond_text(text)
        info.source = u
        if info.complete:
            res.found.append(info)
    if not res.found and not res.errors:
        res.errors.append("No page with this ISIN showed both a coupon and a maturity date.")
    return res

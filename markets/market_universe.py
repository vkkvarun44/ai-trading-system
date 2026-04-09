"""Dynamic market-universe discovery from live market websites."""

from __future__ import annotations

from io import StringIO
import re

import pandas as pd

from core.logger import get_logger

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

logger = get_logger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_US_QUOTE_PATTERNS = [
    re.compile(r"/quote/([A-Z][A-Z0-9.\-]{0,14})"),
    re.compile(r"/market-activity/stocks/([a-z][a-z0-9.\-]{0,14})"),
]
_INDIA_TOKEN_PATTERN = re.compile(r"\b([A-Z][A-Z0-9&.\-]{1,20})(?:\.(?:NS|BO))?\b")


def fetch_dynamic_market_universe(market: str, source_urls: list[str]) -> list[str]:
    """Fetch a dynamic candidate universe from configured market websites."""

    if requests is None:
        logger.warning("Requests is unavailable; cannot fetch dynamic market universe for %s", market)
        return []

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    collected: list[str] = []
    seen: set[str] = set()

    for url in source_urls:
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            html = response.text
            source_tickers = _extract_tickers_from_html(market.upper(), html)
            for ticker in source_tickers:
                if ticker in seen:
                    continue
                seen.add(ticker)
                collected.append(ticker)
        except Exception as exc:
            logger.warning("Could not fetch market universe from %s: %s", url, exc)

    return collected


def _extract_tickers_from_html(market: str, html: str) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()

    for ticker in _extract_from_tables(market, html):
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)

    for ticker in _extract_from_patterns(market, html):
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)

    return tickers


def _extract_from_tables(market: str, html: str) -> list[str]:
    tickers: list[str] = []
    try:
        tables = pd.read_html(StringIO(html))
    except Exception:
        return tickers

    for frame in tables:
        for column in frame.columns:
            column_name = str(column).strip().lower()
            if not any(key in column_name for key in ("symbol", "ticker", "security", "securities", "underlying")):
                continue
            for value in frame[column].astype(str).tolist():
                normalized = _normalize_ticker(market, value)
                if normalized:
                    tickers.append(normalized)
    return tickers


def _extract_from_patterns(market: str, html: str) -> list[str]:
    tickers: list[str] = []
    if market == "US":
        for pattern in _US_QUOTE_PATTERNS:
            tickers.extend(match.upper() for match in pattern.findall(html))
        return [ticker for ticker in tickers if _normalize_ticker(market, ticker)]

    for token in _INDIA_TOKEN_PATTERN.findall(html):
        normalized = _normalize_ticker(market, token)
        if normalized:
            tickers.append(normalized)
    return tickers


def _normalize_ticker(market: str, raw_value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9&.\-]", "", raw_value.strip().upper())
    if not cleaned:
        return ""

    if market == "INDIA":
        if cleaned in {"SYMBOL", "SECURITIES", "SECURITY", "UNDERLYING", "TOTAL", "FUTURES", "OPTIONS"}:
            return ""
        if not cleaned.endswith((".NS", ".BO")):
            cleaned = f"{cleaned}.NS"
        return cleaned if re.fullmatch(r"[A-Z][A-Z0-9&.\-]{0,20}\.(NS|BO)", cleaned) else ""

    if cleaned.endswith((".NS", ".BO")):
        return ""
    return cleaned if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", cleaned) else ""

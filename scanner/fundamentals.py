"""Fundamentals scrape from screener.in (free, no API).

Kite/Yahoo don't give reliable Indian debt/equity, so we read the public
company page: market cap from the top ratios, debt/equity computed from the
latest balance-sheet row (Borrowings / (Equity Capital + Reserves)).

This is HTML scraping — it will break when screener changes markup, and it must
be polite (cache hard, rate-limit). Treated as a validation spike here.
"""
from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _to_float(text: str):
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _top_ratio(soup: BeautifulSoup, label: str):
    """Read a value from the #top-ratios list (e.g. 'Market Cap')."""
    ul = soup.find("ul", id="top-ratios")
    if not ul:
        return None
    for li in ul.find_all("li"):
        name = li.find("span", class_="name")
        if name and label.lower() in name.get_text(strip=True).lower():
            val = li.find("span", class_="value")
            return _to_float(val.get_text(" ", strip=True)) if val else None
    return None


def _bs_row_latest(soup: BeautifulSoup, label: str):
    """Most-recent value of a balance-sheet row matching `label`."""
    section = soup.find("section", id="balance-sheet")
    if not section:
        return None
    for row in section.select("table tbody tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        name = cells[0].get_text(strip=True).lower()
        if name.startswith(label.lower()):
            return _to_float(cells[-1].get_text(strip=True))
    return None


def _fetch_page(symbol: str) -> BeautifulSoup | None:
    for path in (f"{symbol}/consolidated", symbol):
        url = f"https://www.screener.in/company/{path}/"
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code == 200 and "balance-sheet" in r.text:
            return BeautifulSoup(r.text, "lxml")
    return None


def fetch_fundamentals(symbol: str, polite_seconds: float = 1.5) -> dict:
    """Return {market_cap_cr, debt_to_equity, source}. Values are None on miss."""
    time.sleep(polite_seconds)  # be a good citizen
    soup = _fetch_page(symbol)
    if soup is None:
        return {"market_cap_cr": None, "debt_to_equity": None, "source": "screener:miss"}

    mcap = _top_ratio(soup, "Market Cap")

    borrowings = _bs_row_latest(soup, "Borrowings")
    equity_cap = _bs_row_latest(soup, "Equity Capital")
    reserves = _bs_row_latest(soup, "Reserves")
    de = None
    if borrowings is not None and equity_cap is not None and reserves is not None:
        net_worth = equity_cap + reserves
        if net_worth > 0:
            de = round(borrowings / net_worth, 3)

    return {"market_cap_cr": mcap, "debt_to_equity": de, "source": "screener"}

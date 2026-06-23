"""Universe loading and the financials rule.

Banks, NBFCs and insurers are excluded by default: screener's "Borrowings" is
not ordinary debt for them, so the debt/equity quality gate is meaningless.
They can be opted back in, but the mean-reversion + low-debt thesis is built
for non-financials.
"""
from __future__ import annotations

import csv
from pathlib import Path

# NIFTY 50 banks / NBFCs / insurers — D/E gate does not apply.
FINANCIALS = {
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN",
    "SBILIFE", "HDFCLIFE",
}

_DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "universe_nifty50.csv"


def is_financial(symbol: str, financials: set[str] = FINANCIALS) -> bool:
    return symbol.upper() in financials


def select_universe(symbols, include_financials: bool, financials: set[str] = FINANCIALS):
    """Filter a symbol list by the financials rule, preserving order."""
    if include_financials:
        return list(symbols)
    return [s for s in symbols if not is_financial(s, financials)]


def load_symbols(csv_path: Path = _DEFAULT_CSV) -> list[str]:
    """Load NSE symbols from the universe CSV, stripping any `.NS` suffix."""
    out = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ticker = row["ticker"].strip()
            out.append(ticker[:-3] if ticker.upper().endswith(".NS") else ticker)
    return out

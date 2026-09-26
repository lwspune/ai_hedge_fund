"""NSE IPO bid details (`api/ipo-bid-details?symbol=&series=EQ`, a plain Referer session): the
retail category's times-subscribed as bid on NSE. chittorgarh publishes the consolidated retail
figure only for recent issues (older ones sit behind its paywall), so for older mainboard issues
this is the free source. NSE carries a stable share of retail bids — NSE / consolidated = 0.647
median over 32 mainboard IPOs (Aug-Sep 2026, range 0.51-0.72) — so the NSE figure is scaled up.
SME rows carry no offer size (times = 0): no retail figure for SME from here.
"""
from __future__ import annotations

import requests

API = "https://www.nseindia.com/api/ipo-bid-details"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Referer": "https://www.nseindia.com/", "Accept-Encoding": "gzip, deflate"}
NSE_SHARE = 0.647


def parse_bid_details(payload) -> float | None:
    """Retail Individual Investors' times subscribed on NSE, or None when absent / zero."""
    rows = (payload or {}).get("data") or []
    rii = next((r for r in rows if str(r.get("category", "")).startswith("Retail Individual")), None)
    try:
        t = float(rii["noOfTime"]) if rii else 0.0
    except (TypeError, ValueError):
        return None
    return t if t > 0 else None


def final_retail_from_nse(nse_times: float | None) -> float | None:
    return nse_times / NSE_SHARE if nse_times else None


def session() -> requests.Session:
    s = requests.Session()
    s.get("https://www.nseindia.com/", headers=_HEADERS, timeout=20)   # sets the cookies the API wants
    return s


def fetch_retail_times(symbol: str, s: requests.Session) -> float | None:
    r = s.get(API, params={"symbol": symbol, "series": "EQ"}, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return parse_bid_details(r.json())

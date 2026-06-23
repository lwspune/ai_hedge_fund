"""Bulk/block-deal 'smart money' tracker — NSE static archive CSVs (free).

The thesis: named institutional *buys* in the daily bulk/block deal feed precede
positive abnormal returns. The hard part is separating real institutions
(mutual funds, insurers, FIIs) from the prop/arb LLPs that dominate the raw feed.

Data: nsearchives static CSVs (current-day), CDN-served, no anti-bot gate.
"""
from __future__ import annotations

import csv
import io
import time

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_BULK_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
_BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"

# Client-name classification. Ordered: first matching category wins, so
# institutional keywords are checked before the generic prop/broker ones.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("mutual_fund", ("MUTUAL FUND",)),
    ("insurance", ("INSURANCE", "LIFE INSUR", "ASSURANCE")),
    ("pension", ("PENSION", "PROVIDENT", "RETIREMENT")),
    ("aif", ("ALTERNATIVE INVESTMENT", " AIF", "AIF ")),
    ("asset_manager", ("INVESTMENT MANAG", "ASSET MANAG", "ASSET MGMT",
                       "FUND MANAG", "INVESTMENT TRUST", "GLOBAL FUND",
                       "INVESTMENT FUND", "PORTFOLIO MANAG")),
    ("prop_broker", ("LLP", "SECURITIES", "BROKING", "BROKERAGE", "BROKER",
                     "STOCK", "SHARE", "CAPITAL SERVICES", "VENTURES",
                     "TRADING", "COMMODIT", "FINANCIAL SERVICES")),
]

# Categories treated as informed institutional capital.
NOTABLE = {"mutual_fund", "insurance", "pension", "aif", "asset_manager"}


def classify_client(name: str) -> str:
    up = (name or "").upper()
    for category, keywords in _RULES:
        if any(k in up for k in keywords):
            return category
    return "other"


def is_notable_buy(deal: dict, value_min: float) -> bool:
    return (
        deal.get("side") == "BUY"
        and classify_client(deal.get("client", "")) in NOTABLE
        and deal.get("value", 0) >= value_min
    )


def aggregate_by_symbol(deals: list[dict], value_min: float) -> list[dict]:
    """Group notable institutional buys per symbol; rank by #buyers then value."""
    grouped: dict[str, dict] = {}
    for d in deals:
        if not is_notable_buy(d, value_min):
            continue
        g = grouped.setdefault(
            d["symbol"],
            {"symbol": d["symbol"], "buyers": [], "categories": set(),
             "total_qty": 0, "total_value": 0.0},
        )
        g["buyers"].append(d["client"])
        g["categories"].add(classify_client(d["client"]))
        g["total_qty"] += d["qty"]
        g["total_value"] += d["value"]
    for g in grouped.values():
        g["n_buyers"] = len(set(g["buyers"]))
    return sorted(
        grouped.values(),
        key=lambda g: (g["n_buyers"], g["total_value"]),
        reverse=True,
    )


# --- live data ---------------------------------------------------------------

def _fetch_csv(url: str, tries: int = 3) -> str:
    headers = {"User-Agent": _UA, "Accept": "*/*"}
    last = None
    for i in range(tries):
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and "Symbol" in r.text:
            return r.text
        last = r.status_code
        time.sleep(1 + i)
    raise RuntimeError(f"fetch failed for {url}: status {last}")


def _parse(text: str, kind: str) -> list[dict]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {k.strip(): (v.strip() if v else v) for k, v in row.items()}
        try:
            qty = int(row["Quantity Traded"].replace(",", ""))
            price = float(row["Trade Price / Wght. Avg. Price"].replace(",", ""))
        except (KeyError, ValueError):
            continue
        out.append({
            "date": row.get("Date"),
            "symbol": row.get("Symbol"),
            "security": row.get("Security Name"),
            "client": row.get("Client Name"),
            "side": (row.get("Buy/Sell") or "").upper(),
            "qty": qty,
            "price": price,
            "value": qty * price,
            "kind": kind,
        })
    return out


def fetch_deals() -> list[dict]:
    """Today's bulk + block deals, normalised."""
    deals = []
    for url, kind in ((_BULK_URL, "bulk"), (_BLOCK_URL, "block")):
        deals.extend(_parse(_fetch_csv(url), kind))
    return deals

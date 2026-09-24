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
from pathlib import Path

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


# --- Full company page (infra I4) ---------------------------------------------
# Everything screener.in shows publicly: top ratios, sector hierarchy, and every
# statement table in long format (section, line_item, period, value). The full
# history goes to a local parquet cache; a one-row `company_snapshot` goes to Supabase.

_SECTIONS = ("quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding")
_RATIO_KEYS = {"Market Cap": "market_cap_cr", "Current Price": "price", "Stock P/E": "pe",
               "Book Value": "book_value", "Dividend Yield": "dividend_yield", "ROCE": "roce",
               "ROE": "roe", "Face Value": "face_value"}
_MONTH_END = {"Jan": 31, "Feb": 28, "Mar": 31, "Apr": 30, "May": 31, "Jun": 30, "Jul": 31,
              "Aug": 31, "Sep": 30, "Oct": 31, "Nov": 30, "Dec": 31}
_MONTH_NUM = {m: i for i, m in enumerate(_MONTH_END, 1)}
_SKIP_ITEMS = {"Raw PDF"}


def parse_number(text):
    """'₹ 7,55,677 Cr.' -> 755677.0; '3.06 %' -> 3.06; blank/dash -> None."""
    if text is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text))
    return float(m.group(0).replace(",", "")) if m else None


def period_end(label: str):
    """'Mar 2026' -> '2026-03-31' (leap-aware); 'TTM' / junk -> None."""
    m = re.match(r"^([A-Z][a-z]{2}) (\d{4})$", (label or "").strip())
    if not m or m.group(1) not in _MONTH_END:
        return None
    y, mon = int(m.group(2)), m.group(1)
    day = 29 if mon == "Feb" and y % 4 == 0 and (y % 100 or y % 400 == 0) else _MONTH_END[mon]
    return f"{y:04d}-{_MONTH_NUM[mon]:02d}-{day:02d}"


def _clean_item(name: str) -> str:
    return re.sub(r"\s*\+\s*$", "", name.replace("\xa0", " ")).strip()


def _section_table(section):
    if section.get("id") == "shareholding":
        q = section.find("div", id="quarterly-shp")
        if q is not None and q.find("table"):
            return q.find("table")
    for t in section.find_all("table"):
        if t.select("thead th"):
            return t
    return None


def parse_statements(soup: BeautifulSoup) -> list[dict]:
    rows = []
    for sid in _SECTIONS:
        sec = soup.find("section", id=sid)
        table = _section_table(sec) if sec else None
        if table is None:
            continue
        periods = [th.get_text(" ", strip=True) for th in table.select("thead th")][1:]
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            item = _clean_item(cells[0].get_text(" ", strip=True))
            if not item or item in _SKIP_ITEMS:
                continue
            for per, td in zip(periods, cells[1:]):
                v = parse_number(td.get_text(" ", strip=True))
                if v is not None:
                    rows.append({"section": sid, "line_item": item, "period": per,
                                 "period_end": period_end(per), "value": v})
    return rows


def parse_company_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    ratios = {}
    for li in soup.select("#top-ratios li"):
        name, val = li.find("span", class_="name"), li.find("span", class_="value")
        if not name or not val:
            continue
        label, text = name.get_text(" ", strip=True), val.get_text(" ", strip=True)
        if label in _RATIO_KEYS:
            ratios[_RATIO_KEYS[label]] = parse_number(text)
        elif label.startswith("High / Low"):
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
            if len(nums) == 2:
                ratios["high_52w"], ratios["low_52w"] = nums
    levels = {}
    for a in soup.select("#peers a[href^='/market/']"):
        depth = len([p for p in a["href"].split("/") if p]) - 1  # /market/IN08/ -> 1
        levels.setdefault(depth, a.get_text(" ", strip=True))
    return {"ratios": ratios, "sector": levels.get(1), "broad_industry": levels.get(2),
            "industry": levels.get(3), "basic_industry": levels.get(4),
            "statements": parse_statements(soup)}


def has_financials(page: dict) -> bool:
    return any(r["section"] in ("quarters", "profit-loss") for r in page["statements"])


def _latest(statements, section, items, period=None):
    cand = [r for r in statements if r["section"] == section and r["line_item"] in items
            and (period is None or r["period"] == period) and (period or r["period_end"])]
    return max(cand, key=lambda r: r["period_end"] or "")["value"] if cand else None


def _pct(v):
    return v if v is not None and 0 <= v <= 100 else None


def snapshot_row(symbol: str, page: dict, consolidated: bool) -> dict:
    st, r = page["statements"], page["ratios"]
    pl_items = ("Sales", "Revenue")
    rev = _latest(st, "profit-loss", pl_items, "TTM") or _latest(st, "profit-loss", pl_items)
    np_ = _latest(st, "profit-loss", ("Net Profit",), "TTM") or _latest(st, "profit-loss", ("Net Profit",))
    de = None
    if page["sector"] != "Financial Services":
        bs = [x for x in st if x["section"] == "balance-sheet" and x["period_end"]]
        last = max((x["period_end"] for x in bs), default=None)
        vals = {x["line_item"]: x["value"] for x in bs if x["period_end"] == last}
        borrow = vals.get("Borrowings", vals.get("Borrowing"))
        nw = (vals.get("Equity Capital") or 0) + (vals.get("Reserves") or 0)
        if borrow is not None and nw > 0:
            de = round(borrow / nw, 3)
    shp = [x for x in st if x["section"] == "shareholding" and x["period_end"]]
    shp_last = max((x["period_end"] for x in shp), default=None)
    sh = {x["line_item"]: x["value"] for x in shp if x["period_end"] == shp_last}
    nsh = sh.get("No. of Shareholders")
    return {
        "symbol": symbol, "consolidated": consolidated,
        **{k: r.get(k) for k in ("market_cap_cr", "price", "pe", "book_value", "dividend_yield",
                                 "roce", "roe", "face_value", "high_52w", "low_52w")},
        "revenue_ttm": rev, "net_profit_ttm": np_, "debt_to_equity": de,
        "promoter_pct": _pct(sh.get("Promoters")), "fii_pct": _pct(sh.get("FIIs")),
        "dii_pct": _pct(sh.get("DIIs")), "govt_pct": _pct(sh.get("Government")),
        "public_pct": _pct(sh.get("Public")),
        "n_shareholders": int(nsh) if nsh is not None and nsh >= 0 else None,
        "shp_period": shp_last,
        "sector": page["sector"], "broad_industry": page["broad_industry"],
        "industry": page["industry"], "basic_industry": page["basic_industry"],
        "history": history_json(page),
    }


_HISTORY = {
    "annual": ("profit-loss", {"Sales": "revenue", "Revenue": "revenue", "Net Profit": "net_profit",
                               "EPS in Rs": "eps", "OPM %": "opm"}),
    "quarterly": ("quarters", {"Sales": "revenue", "Revenue": "revenue", "Net Profit": "net_profit",
                               "EPS in Rs": "eps", "OPM %": "opm"}),
    "shareholding": ("shareholding", {"Promoters": "promoter", "FIIs": "fii", "DIIs": "dii",
                                      "Public": "public", "No. of Shareholders": "holders"}),
}


def history_json(page: dict) -> dict:
    """Compact per-period series for the dashboard company page (a few KB per company).
    Works from `page["statements"]`, so it can be rebuilt from the local parquet cache."""
    out = {}
    for key, (section, fields) in _HISTORY.items():
        periods: dict[str, dict] = {}
        for r in page["statements"]:
            if r["section"] == section and r["line_item"] in fields:
                periods.setdefault(r["period"], {"period": r["period"]})[fields[r["line_item"]]] = r["value"]
        out[key] = list(periods.values())
    return out


def latest_quarter(page: dict | None):
    """Most recent dated quarterly-results period ('YYYY-MM-DD'), or None."""
    if not page:
        return None
    return max((r["period_end"] for r in page["statements"]
                if r["section"] == "quarters" and r["period_end"]), default=None)


def pick_view(consolidated: dict | None, standalone: dict | None):
    """(page, is_consolidated): consolidated unless standalone reports a later quarter —
    some companies' consolidated statements silently stop updating (e.g. 3M India, 2024)."""
    if consolidated is None and standalone is None:
        return None
    if standalone is None:
        return consolidated, True
    if consolidated is None:
        return standalone, False
    if (latest_quarter(standalone) or "") > (latest_quarter(consolidated) or ""):
        return standalone, False
    return consolidated, True


def _get_page(s, path: str, retries: int):
    for attempt in range(retries):
        r = s.get(f"https://www.screener.in/company/{path}/", headers=_HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        page = parse_company_page(r.text)
        return page if has_financials(page) else None
    return None


def fetch_company_page(symbol: str, session=None, retries: int = 3):
    """(page, consolidated) via `pick_view` of both views; None if screener has neither.
    Backs off on HTTP 429."""
    s = session or requests
    return pick_view(_get_page(s, f"{symbol}/consolidated", retries), _get_page(s, symbol, retries))


STATEMENTS_DIR = Path(__file__).resolve().parent.parent / "cache" / "fundamentals"
BUCKET = "fundamentals"  # private Supabase Storage bucket: the durable copy (CI has no disk)


def _statements_name(symbol: str) -> str:
    return f"{symbol.replace('&', '_and_')}.parquet"


def save_statements(symbol: str, page: dict, directory: Path = STATEMENTS_DIR,
                    upload: bool = False) -> Path:
    """Write the full statement history locally; with upload=True also to the bucket."""
    import pandas as pd
    directory.mkdir(parents=True, exist_ok=True)
    fp = directory / _statements_name(symbol)
    pd.DataFrame(page["statements"], columns=["section", "line_item", "period", "period_end",
                                             "value"]).to_parquet(fp, index=False)
    if upload:
        from scanner import db
        db.storage_put(BUCKET, fp.name, fp.read_bytes())
    return fp


def load_statements(symbol: str, directory: Path = STATEMENTS_DIR):
    """Full statement history (long format): local cache first, else the Storage bucket
    (cached locally after download). None if never fetched."""
    import pandas as pd
    fp = directory / _statements_name(symbol)
    if not fp.exists():
        from scanner import db
        data = db.storage_get(BUCKET, fp.name)
        if data is None:
            return None
        directory.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    return pd.read_parquet(fp)

"""Sector indices v1 (docs/SECTOR_INDICES_SPEC.md): which NSE sector index each stock belongs to, and the
latest-day sector table.

  data/sector_map.csv      NSE industry (company_snapshot.industry) -> primary + fallback sector index
                           (reviewed by the owner; NIFTY 500 written `^CRSLDX`, only for Diversified)
  data/sector_indices.csv  the indices loaded into index_prices (symbol = the NSE name) + NSE name aliases

A stock uses its primary index once that index has a year of closes (MIN_SECTOR_SESSIONS), else the
fallback, else NIFTY 500 — so a newly launched NSE index takes over by itself. Closes come from NSE's daily
index-close file (scripts/refresh_prices.py). Measurements, not a rotation signal.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scanner.pricestore import clean_series

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "sector_map.csv"
INDICES_PATH = ROOT / "data" / "sector_indices.csv"
N500 = "^CRSLDX"
MIN_SECTOR_SESSIONS = 250
MIN_BREADTH_STOCKS = 5           # fewer mapped stocks: no breadth share for the sector


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_sector_map(path: Path = MAP_PATH) -> dict[str, tuple[str, str]]:
    """{NSE industry: (primary index, fallback index)} — industry strings exactly as NSE writes them."""
    return {r["industry"]: (r["primary"].strip(), r["fallback"].strip()) for r in _rows(path)}


def load_sector_indices(path: Path = INDICES_PATH) -> dict[str, str]:
    """{lowercase NSE name or alias: index_symbol}. An alias may map to one symbol only."""
    out: dict[str, str] = {}
    for r in _rows(path):
        sym = r["index_symbol"].strip()
        for name in (r["nse_names"] or "").split("|"):
            key = name.strip().lower()
            if key:
                if key in out and out[key] != sym:
                    raise ValueError(f"NSE name {name!r} maps to both {out[key]} and {sym}")
                out[key] = sym
    return out


def sector_symbols(path: Path = INDICES_PATH) -> list[str]:
    return [r["index_symbol"].strip() for r in _rows(path)]


def pick_index(industry: str | None, sessions_by_index: dict[str, int],
               smap: dict[str, tuple[str, str]] | None = None) -> tuple[str | None, bool]:
    """(index to use, whether it is a fallback). Primary when it has MIN_SECTOR_SESSIONS closes, else the
    fallback when it does, else NIFTY 500. (None, False) for a stock without a mapped industry."""
    smap = load_sector_map() if smap is None else smap
    if industry not in smap:
        return None, False
    primary, fallback = smap[industry]
    if primary == N500:
        return N500, False
    if sessions_by_index.get(primary, 0) >= MIN_SECTOR_SESSIONS:
        return primary, False
    if sessions_by_index.get(fallback, 0) >= MIN_SECTOR_SESSIONS:
        return fallback, True
    return N500, True


def assign_indices(industries: dict[str, str | None], closes: dict[str, pd.Series], since,
                   smap: dict[str, tuple[str, str]] | None = None) -> dict[str, tuple[str | None, bool]]:
    """{symbol: (index, is_fallback)} for every symbol, judging each index's history by its closes on or
    after `since` (the risk window)."""
    smap = load_sector_map() if smap is None else smap
    lo = pd.Timestamp(since)
    sessions = {i: int((c.index >= lo).sum()) for i, c in closes.items()}
    return {s: pick_index(ind, sessions, smap) for s, ind in industries.items()}


# --- thin I/O ------------------------------------------------------------------------------

def load_industries() -> dict[str, str | None]:
    """{symbol: NSE industry} from company_snapshot (the classification the map is keyed on)."""
    from scanner import db
    return {r["symbol"]: r.get("industry") for r in db.select_all("company_snapshot", {"select": "symbol,industry"})}


def load_sector_closes(start, end) -> dict[str, pd.Series]:
    """{index_symbol: closes} for the configured sector indices from index_prices, [start, end]."""
    from scanner import db
    names = ",".join(f'"{s}"' for s in sector_symbols())
    rows = db.select_all("index_prices", {"select": "index_symbol,trade_date,close", "index_symbol": f"in.({names})",
                                          "and": f"(trade_date.gte.{start},trade_date.lte.{end})",
                                          "order": "index_symbol,trade_date"})
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["index_symbol"], []).append((pd.Timestamp(r["trade_date"]), float(r["close"])))
    return {s: pd.Series([c for _, c in v], index=pd.DatetimeIndex([d for d, _ in v], name="date"))
            for s, v in out.items()}


def _r(v, dp=4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, dp) if math.isfinite(f) else None


def _ret(c: pd.Series, k: int):
    return c.iloc[-1] / c.iloc[-1 - k] - 1 if len(c) > k else None


def sector_rows(closes: dict[str, pd.Series], n500: pd.Series, states_last: dict[str, tuple[bool, bool]],
                symbol_index: dict[str, str | None]) -> list[dict]:
    """One `sector_regime` row per sector index some stock maps to. `closes`: each index's full stored
    history; `states_last`: {symbol: (in the breadth universe, above its 200-DMA)} on the last date;
    `symbol_index`: {symbol: index it uses}. NIFTY 500 is the benchmark, not a sector row."""
    n5 = clean_series(n500) if n500 is not None and len(n500) else pd.Series(dtype="float64")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for idx in sorted({i for i in symbol_index.values() if i and i != N500}):
        raw = closes.get(idx)
        if raw is None or not len(raw):
            continue
        c = clean_series(raw)
        last = c.index[-1]
        ret_3m = _ret(c, 63)
        n5_to = n5[n5.index <= last]
        n5_3m = _ret(n5_to, 63) if len(n5_to) else None
        members = [states_last[s] for s, i in symbol_index.items() if i == idx and s in states_last]
        eligible = [above for ok, above in members if ok]
        rows.append({
            "index_name": idx, "as_of": last.date().isoformat(), "close": _r(c.iloc[-1], 2),
            "dd": _r(c.iloc[-1] / c.max() - 1), "ret_1m": _r(_ret(c, 21)), "ret_3m": _r(ret_3m),
            "rel_3m": _r(ret_3m - n5_3m) if ret_3m is not None and n5_3m is not None else None,
            "n_stocks": len(eligible),
            "pct_above_200": _r(sum(eligible) / len(eligible)) if len(eligible) >= MIN_BREADTH_STOCKS else None,
            "updated_at": now,
        })
    return rows

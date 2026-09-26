"""Price consolidation: a liquid stock trading in a tight range, and the first close outside it.

A consolidation is a 40-session window whose (highest high - lowest low) / mean close is <= 10%,
on a stock whose median daily turnover is >= Rs 1 crore (illiquid stocks look flat because nothing
trades). A breakout is the first close above the range high (up) or below the range low (down) —
the range is the window ending the session before, so it is frozen when the break happens. Wide-
range breakouts (a 40-day high / low out of a range > 10%) are recorded as the control. One event
per symbol, kind and direction per 40 sessions. Validation: scripts/validate_consolidation.py;
live scan: `python -m scanner.run consolidation`. Tested in tests/test_consolidation.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 40
MAX_RANGE = 0.10
MIN_TURNOVER_LAKH = 100.0      # Rs 1 crore / day, median over the window
PRIOR = 60                     # the move before the base: 60 sessions before the window starts


def _run_length(flags: pd.Series) -> pd.Series:
    """Consecutive True count ending at each row."""
    grp = (~flags).cumsum()
    return flags.astype(int).groupby(grp).cumsum()


def _window_stats(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Range stats of the n-session window ending at each row (not shifted)."""
    hi, lo = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    mean_close = df["close"].rolling(n).mean()
    out = pd.DataFrame({"hi": hi, "lo": lo, "range": (hi - lo) / mean_close,
                        "liquid": df["turnover_lakh"].rolling(n).median() >= MIN_TURNOVER_LAKH,
                        "vol_mean": df["volume"].rolling(n).mean()}, index=df.index)
    out["tight"] = (out["range"] <= MAX_RANGE) & out["liquid"]
    out["run"] = _run_length(out["tight"].fillna(False))
    return out


def breakout_events(df: pd.DataFrame, symbol: str, n: int = WINDOW) -> list[dict]:
    """Every breakout of the window ending the session before: tight (the event) or wide (control).
    `df`: daily bars indexed by date with close, high, low, volume, turnover_lakh, delivery_pct."""
    if len(df) <= n:
        return []
    df = df.sort_index()
    w = _window_stats(df, n).shift(1)                       # the range as it stood before today
    prior = df["close"].shift(n) / df["close"].shift(n + PRIOR) - 1
    up, down = df["close"] > w["hi"], df["close"] < w["lo"]
    out, last = [], {}
    for i in np.flatnonzero((up | down).to_numpy() & w["liquid"].fillna(False).to_numpy().astype(bool)):
        t = df.index[i]
        tight = bool(w["tight"].iat[i])
        direction = "up" if up.iat[i] else "down"
        key = (tight, direction)
        if key in last and i - last[key] < n:
            continue
        last[key] = i
        vm = w["vol_mean"].iat[i]
        out.append({
            "symbol": symbol, "date": t, "direction": direction, "tight": tight,
            "range_pct": float(w["range"].iat[i]),
            "days_in_range": int(n + w["run"].iat[i] - 1) if tight else 0,
            "prior_move": float(prior.iat[i]) if pd.notna(prior.iat[i]) else None,
            "vol_ratio": float(df["volume"].iat[i] / vm) if vm and vm > 0 else None,
            "delivery_pct": float(df["delivery_pct"].iat[i]) if pd.notna(df["delivery_pct"].iat[i]) else None,
            "turnover_lakh": float(df["turnover_lakh"].iloc[max(0, i - n):i].median()),
            "close": float(df["close"].iat[i]),
        })
    return out


def current_state(df: pd.DataFrame, symbol: str, n: int = WINDOW) -> dict | None:
    """The live scan: is the stock in a tight range right now, for how long, and where in it."""
    if len(df) < n:
        return None
    df = df.sort_index()
    w = _window_stats(df, n).iloc[-1]
    last = df.iloc[-1]
    span = w["hi"] - w["lo"]
    recent = df["volume"].iloc[-10:].mean()
    return {"symbol": symbol, "date": df.index[-1], "in_range": bool(w["tight"]),
            "range_pct": float(w["range"]), "days_in_range": int(n + w["run"] - 1) if w["tight"] else 0,
            "position": float((last["close"] - w["lo"]) / span) if span > 0 else 0.5,
            "vol_trend": float(recent / w["vol_mean"]) if w["vol_mean"] else None,
            "close": float(last["close"]), "hi": float(w["hi"]), "lo": float(w["lo"])}


def scan_now(panel: dict[str, pd.DataFrame], n: int = WINDOW, universe: set | None = None) -> list[dict]:
    """The live scan over a recent bar panel: stocks in a tight range on the last session, and
    tight-range breakouts that happened on it. Every stock is judged on its own last session.
    `universe`: company symbols only — ETFs (liquid funds sit in a sub-1% range forever) are out."""
    out = []
    for sym, df in panel.items():
        if (universe is not None and sym not in universe) or len(df) <= n:
            continue
        last = df.index.max()
        brk = [e for e in breakout_events(df, sym, n) if e["tight"] and e["date"] == last]
        if brk:
            e = brk[0]
            out.append({"symbol": sym, "date": last, "status": f"breakout {e['direction']}",
                        "range_pct": e["range_pct"], "days_in_range": e["days_in_range"], "position": None,
                        "vol_trend": e["vol_ratio"], "close": e["close"]})
            continue
        s = current_state(df, sym, n)
        if s and s["in_range"]:
            out.append({**{k: s[k] for k in ("symbol", "date", "range_pct", "days_in_range", "position",
                                            "vol_trend", "close")}, "status": "in range"})
    return sorted(out, key=lambda r: (r["status"] == "in range", r["range_pct"]))


def consolidation_candidates(rows: list[dict]) -> list[dict]:
    """scan_now rows -> `candidates` rows (score = range %, tighter first) for the dashboard."""
    keys = ("status", "range_pct", "days_in_range", "position", "vol_trend", "close")
    return [{"symbol": r["symbol"], "score": r["range_pct"],
             "payload": {**{k: r.get(k) for k in keys}, "date": str(pd.Timestamp(r["date"]).date())}} for r in rows]


def format_scan(rows: list[dict]) -> str:
    if not rows:
        return "No liquid stock is in a tight 40-session range."
    lines = [f"{'symbol':<12} {'status':<14} {'range':>6} {'days':>5} {'position':>9} {'vol trend':>9} {'close':>10}"]
    for r in rows:
        pos = "" if r["position"] is None else f"{r['position'] * 100:7.0f}%"
        vt = "" if r["vol_trend"] is None else f"{r['vol_trend']:8.2f}x"
        lines.append(f"{r['symbol']:<12} {r['status']:<14} {r['range_pct'] * 100:5.1f}% {r['days_in_range']:>5} "
                     f"{pos:>9} {vt:>9} {r['close']:>10.2f}")
    return "\n".join(lines)


def live_scan(days: int = 120) -> list[dict]:
    """Today's scan from the raw bhavcopy months (the store's table keeps closes, not highs / lows)."""
    from datetime import date, timedelta
    from scanner import db
    from scanner.pricestore import bar_panel
    today = date.today()
    companies = {c["symbol"] for c in db.select_all("companies", {"select": "symbol", "status": "eq.listed"})}
    return scan_now(bar_panel(today - timedelta(days=days), today), universe=companies)

"""Market regime view v1 (docs/REGIME_VIEW_SPEC.md): one row per trading day of market-wide measurements.

  index    NIFTY 500 / NIFTY 50 drawdown from the high since 2020, 1m / 3m returns, 20-session realised
           vol and its percentile against every earlier day (expanding, point-in-time)
  breadth  over liquid mainboard stocks as of each date: share above the 50 / 200-DMA, new 52-week
           highs / lows, share of advancers

Measurements, not a signal: no verdict, no risk-on / risk-off label, never gates an alert.

Breadth runs on split / bonus-adjusted closes. Unlike `adjust_for_actions` (all or nothing), an action
the prices don't confirm, a one-session move beyond `risk.PRICE_BREAK` or a demerger becomes a *break*:
the stock sits out of breadth for the 250 prints after it (the longest lookback), and is counted in
`n_excluded`. Loader: scripts/refresh_regime.py -> table `market_regime`.
"""
from __future__ import annotations

import bisect
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from scanner.consolidation import MIN_TURNOVER_LAKH
from scanner.pricestore import action_groups, clean_series, confirmed_factor
from scanner.risk import ANN, PRICE_BREAK, log_returns

START = date(2020, 1, 1)          # bucket floor; first breadth row once 200 prints exist (~Oct 2020)
DMA_LONG, DMA_SHORT, HIGH_LOW = 200, 50, 250
VOL_WINDOW, VOL_PCT_MIN = 20, 250
MAINBOARD = ("EQ", "BE", "BZ")
LOOKBACK_DAYS = 520               # daily run: ~355 sessions, so 250 prints of any regular stock (>= 80%) fit
RECOMPUTE_SESSIONS = 10           # daily run rewrites the last 10 sessions (heals a late bhavcopy)
MAX_MOVE_GAP = 5                  # a previous print further back than this is not a one-day move
MAX_GAP_RESET = 20                # a longer gap (a suspension) starts a new segment: history restarts
REGULAR_SESSIONS, REGULAR_MIN_PRINTS = 250, 200   # in the universe only if it printed on >= 80% of the
                                  # last 250 sessions (risk.SPARSE_COVERAGE); intermittent trading is out

STATE_COLS = ["eligible", "excluded", "above_200", "above_50", "new_high", "new_low", "move"]
INDEX_COLS = ["n500_close", "n500_dd", "n50_dd", "n500_ret_1m", "n500_ret_3m", "n500_vol_20", "n500_vol_pct"]
BREADTH_COLS = ["pct_above_200", "pct_above_50", "new_highs", "new_lows", "up_share", "n_universe", "n_excluded"]
INT_COLS = ("new_highs", "new_lows", "n_universe", "n_excluded")


# --- index block --------------------------------------------------------------------

def vol_percentile(vol: pd.Series, min_n: int = VOL_PCT_MIN) -> pd.Series:
    """Percentile (0-100) of each value among all non-null values up to and including it; NaN until
    `min_n` values exist. Ties take the average rank. A later value never changes an earlier one."""
    out = pd.Series(np.nan, index=vol.index, dtype="float64")
    seen: list[float] = []
    for i, v in enumerate(vol.to_numpy(dtype="float64")):
        if math.isnan(v):
            continue
        bisect.insort(seen, v)
        n = len(seen)
        if n < min_n:
            continue
        lo, hi = bisect.bisect_left(seen, v), bisect.bisect_right(seen, v)
        out.iloc[i] = ((lo + hi + 1) / 2 - 1) / (n - 1) * 100 if n > 1 else 100.0
    return out


def index_metrics(n500: pd.Series, n50: pd.Series | None) -> pd.DataFrame:
    """Per NIFTY 500 date: close, drawdown (both indices), 1m / 3m return, 20-session vol + percentile.
    Pass the whole history from START: the running high and the percentile need it."""
    c = clean_series(n500)
    out = pd.DataFrame(index=c.index)
    out["n500_close"] = c
    out["n500_dd"] = c / c.cummax() - 1
    if n50 is not None and len(n50):
        c50 = clean_series(n50)
        out["n50_dd"] = (c50 / c50.cummax() - 1).reindex(c.index)
    else:
        out["n50_dd"] = np.nan
    out["n500_ret_1m"] = c / c.shift(21) - 1
    out["n500_ret_3m"] = c / c.shift(63) - 1
    lr = np.log(c / c.shift(1))
    out["n500_vol_20"] = lr.rolling(VOL_WINDOW).std(ddof=1) * ANN
    out["n500_vol_pct"] = vol_percentile(out["n500_vol_20"])
    return out[INDEX_COLS]


# --- per-stock states ----------------------------------------------------------------

def adjust_segments(closes: pd.Series, actions: list[dict]) -> tuple[pd.Series, list[pd.Timestamp]]:
    """Apply every same-date action group the prices confirm; everything else is a break date:
    an unconfirmed group, a one-session move beyond PRICE_BREAK after adjustment, a demerger ex-date."""
    out = closes.sort_index().astype("float64").copy()
    breaks = set()
    for ex, same_day in action_groups(out.index, actions).items():
        f = confirmed_factor(out, ex, same_day)
        if f is None:
            breaks.add(ex)
        else:
            out[out.index < ex] = out[out.index < ex] * f
    if len(out) >= 2:
        jump = log_returns(out).abs() > -math.log(1 - PRICE_BREAK)
        breaks.update(jump[jump].index)
        lo, hi = out.index.min(), out.index.max()
        breaks.update(pd.Timestamp(a["event_date"]) for a in actions
                      if a.get("event_type") == "demerger" and lo < pd.Timestamp(a["event_date"]) <= hi)
    return out, sorted(breaks)


def _positions(index: pd.DatetimeIndex, sessions) -> np.ndarray:
    """Session number of each print (business days when `sessions` is omitted)."""
    if sessions is not None:
        return pd.DatetimeIndex(sessions).searchsorted(index)
    d = index.values.astype("datetime64[D]")
    return np.busday_count(d[0], d)


def _regular(pos: np.ndarray) -> np.ndarray:
    """True where the stock printed on >= REGULAR_MIN_PRINTS of the last REGULAR_SESSIONS sessions."""
    first = np.searchsorted(pos, pos - REGULAR_SESSIONS + 1)
    return (np.arange(len(pos)) - first + 1) >= REGULAR_MIN_PRINTS


def _segment_states(closes: pd.Series, series: pd.Series, turnover: pd.Series, actions: list[dict],
                    gaps: np.ndarray, regular: np.ndarray) -> pd.DataFrame:
    """States over one unbroken trading stretch (no gap > MAX_GAP_RESET inside it)."""
    n = len(closes)
    adj, breaks = adjust_segments(closes, actions)
    in_break = np.zeros(n, dtype=bool)
    for b in breaks:
        pb = closes.index.searchsorted(b)                    # first print on / after the break
        in_break[pb:pb + HIGH_LOW] = True
    prints = np.arange(1, n + 1)
    liquid = (turnover.rolling(20).median() >= MIN_TURNOVER_LAKH).to_numpy()
    base = series.isin(MAINBOARD).to_numpy() & (prints >= DMA_LONG) & liquid & regular
    move = np.sign(adj.diff()).to_numpy(dtype="float64", copy=True)
    move[1:][gaps > MAX_MOVE_GAP] = np.nan
    hi, lo = adj.rolling(HIGH_LOW).max(), adj.rolling(HIGH_LOW).min()
    return pd.DataFrame({
        "eligible": base & ~in_break,
        "excluded": base & in_break,
        "above_200": (adj > adj.rolling(DMA_LONG).mean()).to_numpy(),
        "above_50": (adj > adj.rolling(DMA_SHORT).mean()).to_numpy(),
        "new_high": (adj >= hi).to_numpy() & (prints >= HIGH_LOW),
        "new_low": (adj <= lo).to_numpy() & (prints >= HIGH_LOW),
        "move": move,
    }, index=closes.index)


def stock_states(bars: pd.DataFrame, actions: list[dict], sessions=None) -> pd.DataFrame:
    """Per print date: in the breadth universe (`eligible`) or kept out by a break (`excluded`), and the
    stock's flags that day. `sessions`: every market session (gap and regular-trading rules); business
    days when omitted. Intermittently traded stocks (< 80% of the last 250 sessions) are never in it.
    A gap of more than MAX_GAP_RESET sessions (a suspension) starts a new segment: prints are counted and
    every window measured inside the segment, and the jump across the gap is not a break — so the daily
    run's short panel and the full rebuild agree. BadPriceData from clean_series propagates."""
    closes = clean_series(bars["close"])
    if not len(closes):
        return pd.DataFrame(columns=STATE_COLS, index=pd.DatetimeIndex([], name="date"))
    series = (bars["series"] if "series" in bars else pd.Series("EQ", index=bars.index))
    series = series[~series.index.duplicated(keep="last")].reindex(closes.index)
    turnover = pd.to_numeric(bars["turnover_lakh"], errors="coerce")
    turnover = turnover[~turnover.index.duplicated(keep="last")].reindex(closes.index)
    pos = _positions(closes.index, sessions)
    gaps, regular = np.diff(pos), _regular(pos)
    starts = np.concatenate([[0], np.flatnonzero(gaps > MAX_GAP_RESET) + 1, [len(closes)]])
    parts = [_segment_states(closes.iloc[a:b], series.iloc[a:b], turnover.iloc[a:b], actions, gaps[a:b - 1],
                             regular[a:b])
             for a, b in zip(starts[:-1], starts[1:])]
    return pd.concat(parts)[STATE_COLS]


# --- breadth ----------------------------------------------------------------------------

def breadth(states: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per date, over the eligible stocks: shares above the DMAs, new highs / lows, advancer share,
    universe size and the count kept out by breaks. Shares are NaN when the universe is empty."""
    keys = ["n_universe", "n_excluded", "a200", "a50", "highs", "lows", "adv", "dec"]
    acc = {k: pd.Series(dtype="int64") for k in keys}
    for st in states.values():
        if st is None or not len(st):
            continue
        e = st["eligible"].astype(bool)
        mv = st["move"].astype("float64")
        parts = {"n_universe": e, "n_excluded": st["excluded"].astype(bool),
                 "a200": e & st["above_200"].astype(bool), "a50": e & st["above_50"].astype(bool),
                 "highs": e & st["new_high"].astype(bool), "lows": e & st["new_low"].astype(bool),
                 "adv": e & (mv > 0), "dec": e & (mv < 0)}
        for k, v in parts.items():
            acc[k] = acc[k].add(v.astype("int64"), fill_value=0)
    dates = acc["n_universe"].index.union(acc["n_excluded"].index).sort_values()
    c = {k: v.reindex(dates, fill_value=0).astype("int64") for k, v in acc.items()}
    n = c["n_universe"].astype("float64").where(c["n_universe"] > 0)
    moved = (c["adv"] + c["dec"]).astype("float64").where(c["adv"] + c["dec"] > 0)
    out = pd.DataFrame({
        "pct_above_200": c["a200"] / n, "pct_above_50": c["a50"] / n,
        "new_highs": c["highs"], "new_lows": c["lows"], "up_share": c["adv"] / moved,
        "n_universe": c["n_universe"], "n_excluded": c["n_excluded"],
    }, index=dates)
    out.index.name = "date"
    return out[BREADTH_COLS]


# --- DB boundary + print -------------------------------------------------------------------

def _clean(v, as_int: bool, dp: int):
    if v is None or v is pd.NaT:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(round(f)) if as_int else round(f, dp)


def regime_rows(index_df: pd.DataFrame, breadth_df: pd.DataFrame, since: date | None = None) -> list[dict]:
    """One `market_regime` row per date in either frame (>= since), plain JSON values only."""
    df = index_df.reindex(columns=INDEX_COLS).join(breadth_df.reindex(columns=BREADTH_COLS), how="outer")
    df = df.sort_index()
    if since is not None:
        df = df[df.index >= pd.Timestamp(since)]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for t, r in df.iterrows():
        row = {"trade_date": pd.Timestamp(t).date().isoformat()}
        for k in INDEX_COLS + BREADTH_COLS:
            row[k] = _clean(r[k], k in INT_COLS, 2 if k == "n500_close" else 4)
        row["updated_at"] = now
        rows.append(row)
    return rows


def format_table(rows: list[dict]) -> str:
    """CLI print, one line per date; blanks as '-'."""
    def pct(v, dp=0):
        return "-" if v is None else f"{v * 100:.{dp}f}%"

    def num(v, spec="d"):
        return "-" if v is None else format(v, spec)

    head = (f"{'date':<12}{'N500 dd':>9}{'vol20':>8}{'vol pct':>8}{'>200d':>7}{'>50d':>7}"
            f"{'highs':>7}{'lows':>7}{'up':>6}{'univ':>6}{'excl':>6}")
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(f"{r['trade_date']:<12}{pct(r.get('n500_dd'), 1):>9}{pct(r.get('n500_vol_20')):>8}"
                     f"{num(r.get('n500_vol_pct'), '.0f'):>8}{pct(r.get('pct_above_200')):>7}"
                     f"{pct(r.get('pct_above_50')):>7}{num(r.get('new_highs')):>7}{num(r.get('new_lows')):>7}"
                     f"{pct(r.get('up_share')):>6}{num(r.get('n_universe')):>6}{num(r.get('n_excluded')):>6}")
    return "\n".join(lines)

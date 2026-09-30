"""Risk lens v1 (docs/RISK_LENS_SPEC.md): per-symbol risk measurements over the listed universe —
volatility, beta / correlation / idiosyncratic vol vs NIFTY 500, drawdown, worst day / week,
trailing returns and liquidity (ADV, days to exit a Rs 5 lakh position at 10% participation).

Measurements, not a signal: no verdict, not in the catalog, never a ranking by itself, and no
composite score — raw numbers plus percentile ranks within the run.

Prices are the cloud store's UNADJUSTED closes, cleaned (`pricestore.clean_series`) and adjusted
through the guarded `pricestore.adjust_for_actions`; a split / bonus the prices don't show gets
null price metrics and the `action_unverified` flag, never a fake -50% day. Turnover is in rupees,
so liquidity needs no adjustment. Loader: scripts/refresh_risk.py -> table `risk_metrics`.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from scanner.pricestore import adjust_for_actions, clean_series

WINDOW_DAYS = 400            # calendar days back from as_of (~270 sessions) = daily_prices retention
POSITION_INR = 5e5           # the days-to-exit position: Rs 5 lakh
PARTICIPATION = 0.10         # share of a day's turnover one can sell without moving the price
MIN_SESSIONS_1Y, MIN_SESSIONS_3M, MIN_SESSIONS_LIQ = 120, 60, 10
SPARSE_COVERAGE = 0.80       # printed on < 80% of the benchmark's sessions = suspended / illiquid
ILLIQUID_ADV_CR = 1.0        # the consolidation scan's Rs 1 crore/day line
PRICE_BREAK = 0.30           # a one-session fall >= 30% (or rise >= 43%) is outside every NSE price
                             # band (max 20%): a split / bonus / demerger missing from corporate_events
ANN = math.sqrt(252)
SME_SERIES = ("SM", "ST", "SZ")
FLAGS = ("short_history", "sparse", "action_unverified", "price_break", "illiquid", "sme", "asm", "gsm")

PRICE_KEYS = ("vol_1y", "vol_3m", "beta_1y", "corr_1y", "idio_vol_1y", "max_dd_1y", "dd_now",
              "worst_day_1y", "worst_week_1y", "ret_1m", "ret_3m", "ret_1y")
LIQ_KEYS = ("adv_20_cr", "delivery_pct_20", "days_to_exit_5l")
COLUMNS = ("symbol", "as_of", "sessions", *PRICE_KEYS, *LIQ_KEYS, "vol_rank", "liq_rank", "flags")
INT_COLUMNS = ("sessions", "days_to_exit_5l")


def _num(v) -> float | None:
    """A finite float, or None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# --- pure measurements ------------------------------------------------------------

def log_returns(closes: pd.Series) -> pd.Series:
    """ln(P_t / P_{t-1}) on the series' own consecutive prints."""
    return np.log(closes / closes.shift(1)).iloc[1:]


def ann_vol(r: pd.Series, n: int | None = None) -> float | None:
    """Annualised volatility of the last `n` returns (all if None); None if fewer than 2."""
    r = r.dropna()
    if n is not None:
        r = r.iloc[-n:]
    if len(r) < 2:
        return None
    return _num(r.std(ddof=1) * ANN)


def beta_stats(r_stock: pd.Series, r_mkt: pd.Series, n: int = 250) -> dict:
    """Beta, correlation and idiosyncratic vol on the last `n` dates both series have.
    The minimum-sample rule (120) is the caller's; degenerate inputs give None, never raise."""
    df = pd.concat([r_stock.rename("s"), r_mkt.rename("m")], axis=1, join="inner").dropna().iloc[-n:]
    out = {"beta": None, "corr": None, "idio_vol": None, "n_aligned": len(df)}
    if len(df) < 2:
        return out
    var_m = df["m"].var(ddof=1)
    if not var_m or not math.isfinite(var_m):
        return out
    beta = df["s"].cov(df["m"], ddof=1) / var_m
    out["beta"] = _num(beta)
    if df["s"].std(ddof=1) > 0:
        out["corr"] = _num(max(-1.0, min(1.0, df["s"].corr(df["m"]))))
    out["idio_vol"] = ann_vol(df["s"] - beta * df["m"])
    return out


def drawdowns(closes: pd.Series) -> dict:
    """Deepest peak-to-trough fall and the current distance below the window high."""
    if not len(closes):
        return {"max_dd": None, "dd_now": None}
    dd = closes / closes.cummax() - 1
    return {"max_dd": _num(dd.min()), "dd_now": _num(closes.iloc[-1] / closes.max() - 1)}


def worst_moves(closes: pd.Series) -> dict:
    """Worst one-session and worst five-session simple return."""
    return {"worst_day": _num((closes / closes.shift(1) - 1).min()),
            "worst_week": _num((closes / closes.shift(5) - 1).min())}


def trailing_returns(closes: pd.Series) -> dict:
    """P_last / P_{last-k} - 1 for k = 21 / 63 / 250 sessions; None when the series is shorter."""
    def ret(k):
        return _num(closes.iloc[-1] / closes.iloc[-1 - k] - 1) if len(closes) > k else None
    return {"ret_1m": ret(21), "ret_3m": ret(63), "ret_1y": ret(250)}


def days_to_exit(position_inr: float, adv_cr: float | None,
                 participation: float = PARTICIPATION) -> int | None:
    """Sessions to sell `position_inr` trading `participation` of the median day (floor 1)."""
    adv = _num(adv_cr)
    if adv is None or adv <= 0:
        return None
    return max(1, math.ceil(round(position_inr / (participation * adv * 1e7), 9)))


def liquidity(bars: pd.DataFrame) -> dict:
    """Median turnover (Rs crore/day) and delivery % over the last 20 sessions (>= 10 needed)."""
    tail = bars.sort_index().tail(20)
    t = pd.to_numeric(tail["turnover_lakh"], errors="coerce").dropna()
    d = pd.to_numeric(tail["delivery_pct"], errors="coerce").dropna()
    adv = _num(t.median() / 100) if len(t) >= MIN_SESSIONS_LIQ else None
    dlv = _num(d.median()) if len(d) >= MIN_SESSIONS_LIQ else None
    return {"adv_20_cr": adv, "delivery_pct_20": dlv, "days_to_exit_5l": days_to_exit(POSITION_INR, adv)}


def coverage(stock_dates, mkt_dates) -> float:
    """Share of the benchmark's sessions, inside the stock's own first..last print, it printed on."""
    s, m = pd.DatetimeIndex(stock_dates), pd.DatetimeIndex(mkt_dates)
    if not len(s):
        return 0.0
    m = m[(m >= s.min()) & (m <= s.max())]
    return float(len(m.intersection(s)) / len(m)) if len(m) else 0.0


def price_break(adj: pd.Series, actions: list[dict]) -> bool:
    """True when the adjusted series still holds a discontinuity it can't be trusted across: a
    one-session move beyond PRICE_BREAK, or a demerger ex-date inside the series (the child's value
    leaves the parent's price; adjust_for_actions has no factor for it)."""
    if len(adj) >= 2 and (log_returns(adj).abs() > -math.log(1 - PRICE_BREAK)).any():
        return True
    lo, hi = adj.index.min(), adj.index.max()
    return any(a.get("event_type") == "demerger" and lo < pd.Timestamp(a["event_date"]) <= hi
               for a in actions)


# --- orchestrator -------------------------------------------------------------------

def symbol_metrics(sym: str, bars: pd.DataFrame, mkt_closes: pd.Series, actions: list[dict],
                   series: str | None, surveillance: set[str]) -> dict:
    """One flat dict of every metric + flags for one symbol. `bars`: the window's bars (unadjusted);
    `actions`: its split / bonus / consolidation corporate_events rows; `surveillance`: the list
    names (asm_lt / asm_st / gsm) it is on today. Price metrics are null when the adjustment can't
    be verified (`action_unverified`) or a break remains after it (`price_break`). Never raises on a bad stock — flags it — but a
    BadPriceData from clean_series propagates (a corrupt store, not a bad stock)."""
    closes = clean_series(bars["close"])
    last = closes.index.max() if len(closes) else (bars.index.max() if len(bars) else None)
    m = {"symbol": sym, "sessions": len(closes), "last_date": last,
         **{k: None for k in PRICE_KEYS}, **liquidity(bars)}
    flags = set()
    n = len(closes)
    if n < MIN_SESSIONS_1Y:
        flags.add("short_history")
    mkt = clean_series(mkt_closes)
    sparse = coverage(closes.index, mkt.index) < SPARSE_COVERAGE
    if sparse and n:
        flags.add("sparse")
    adj = adjust_for_actions(closes, actions) if n >= MIN_SESSIONS_LIQ else None
    if n >= MIN_SESSIONS_LIQ and adj is None:
        flags.add("action_unverified")
    elif adj is not None and price_break(adj, actions):
        flags.add("price_break")
        adj = None
    if adj is not None:
        r = log_returns(adj)
        m.update(trailing_returns(adj))
        if n >= MIN_SESSIONS_3M:
            m["vol_3m"] = ann_vol(r, 60)
            dd, wm = drawdowns(adj), worst_moves(adj)
            m.update(max_dd_1y=dd["max_dd"], dd_now=dd["dd_now"],
                     worst_day_1y=wm["worst_day"], worst_week_1y=wm["worst_week"])
        if n >= MIN_SESSIONS_1Y:
            m["vol_1y"] = ann_vol(r, 250)
            if not sparse:
                common = adj.index.intersection(mkt.index)   # market return over the stock's own intervals
                b = beta_stats(log_returns(adj[common]), log_returns(mkt[common]), 250)
                if b["n_aligned"] >= MIN_SESSIONS_1Y:
                    m.update(beta_1y=b["beta"], corr_1y=b["corr"], idio_vol_1y=b["idio_vol"])
    if m["adv_20_cr"] is not None and m["adv_20_cr"] < ILLIQUID_ADV_CR:
        flags.add("illiquid")
    if series in SME_SERIES:
        flags.add("sme")
    if any(s.startswith("asm") for s in surveillance):
        flags.add("asm")
    if "gsm" in surveillance:
        flags.add("gsm")
    m["flags"] = [f for f in FLAGS if f in flags]
    return m


def _pct_ranks(rows: list[dict], key: str, out_key: str) -> None:
    idx = [i for i, r in enumerate(rows) if _num(r.get(key)) is not None]
    for r in rows:
        r[out_key] = None
    if not idx:
        return
    ranks = pd.Series([float(rows[i][key]) for i in idx]).rank(method="average")
    n = len(idx)
    for i, rk in zip(idx, ranks):
        rows[i][out_key] = round((rk - 1) / (n - 1) * 100, 1) if n > 1 else 100.0


def add_ranks(rows: list[dict]) -> list[dict]:
    """Percentile (0-100) of vol_1y (100 = most volatile) and adv_20_cr (100 = most liquid)
    among the run's symbols that have a value; the rest stay None."""
    rows = [dict(r) for r in rows]
    _pct_ranks(rows, "vol_1y", "vol_rank")
    _pct_ranks(rows, "adv_20_cr", "liq_rank")
    return rows


def _iso_date(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(v).date().isoformat()


def risk_row(m: dict, as_of: date) -> dict:
    """DB boundary: one `risk_metrics` row of plain JSON values. NaN / inf / NaT -> None, floats
    rounded, ints as int. `as_of` = the symbol's last session in the window (else the run date)."""
    row = {"symbol": m["symbol"], "as_of": _iso_date(m.get("last_date")) or _iso_date(as_of)}
    for k in COLUMNS[2:-1]:
        v = m.get(k)
        f = None if v is pd.NaT else _num(v)
        row[k] = None if f is None else (int(round(f)) if k in INT_COLUMNS else round(f, 4))
    row["flags"] = [str(f) for f in (m.get("flags") or [])]
    row["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return row


def format_table(rows: list[dict]) -> str:
    """CLI print: one line per symbol, blanks as "-"."""
    def pct(v):
        return "-" if v is None else f"{v * 100:.0f}%"

    def num(v, spec):
        return "-" if v is None else format(v, spec)

    head = f"{'symbol':<14}{'vol 1y':>8}{'beta':>7}{'max dd':>8}{'dd now':>8}{'ADV cr':>10}{'exit d':>7}  flags"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(f"{r['symbol']:<14}{pct(r.get('vol_1y')):>8}{num(r.get('beta_1y'), '.2f'):>7}"
                     f"{pct(r.get('max_dd_1y')):>8}{pct(r.get('dd_now')):>8}"
                     f"{num(r.get('adv_20_cr'), ',.1f'):>10}{num(r.get('days_to_exit_5l'), 'd'):>7}"
                     f"  {','.join(r.get('flags') or [])}")
    return "\n".join(lines)

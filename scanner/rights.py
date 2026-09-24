"""Rights-entitlement (RE) mispricing study (candidate signal #4).

Since Jan-2020 NSE lists rights entitlements as `<SYMBOL>-RE` (series BE) while the issue is
open. One RE + the issue price = one new share, so the RE's fair value is S - issue_price
(face value + premium). Gap = (S - issue - RE) / S: positive = the RE is cheap, i.e. a buyer
who wants the stock gets it cheaper via RE + subscription than via the market.

Pure logic (tested); runner scripts/validate_rights_re.py.
"""
from __future__ import annotations

import pandas as pd

def re_gap(stock_close, re_close, issue):
    """(S - issue - RE) / S; None on missing/invalid inputs."""
    if not stock_close or re_close is None or issue is None or stock_close <= 0:
        return None
    return float((stock_close - issue - re_close) / stock_close)


def re_symbol(symbol: str) -> str:
    return f"{symbol}-RE"


def gap_series(stock: pd.Series, re_px: pd.Series, issue: float, bound: float = 0.5) -> pd.Series:
    """Daily gap on dates both trade; drops non-positive RE prints and |gap| > bound (bad data)."""
    both = pd.concat({"s": stock, "r": re_px}, axis=1).dropna()
    both = both[(both["r"] > 0) & (both["s"] > 0)]
    g = (both["s"] - issue - both["r"]) / both["s"]
    return g[g.abs() <= bound]


def events_from_issues(rows: list[dict]) -> list[dict]:
    """rights_issues rows -> study/scan events. Exact issue price from the offer document;
    partly-paid issues (RE fair value differs) and withdrawn issues are skipped. The RE trades
    from its credit date (else issue open) to the renunciation date (else issue close)."""
    out = []
    for r in rows:
        if r.get("partly_paid") or r.get("withdrawn") or not r.get("issue_price"):
            continue
        frm = r.get("re_credit_date") or r.get("issue_open")
        to = r.get("renunciation_date") or r.get("issue_close")
        if not frm or not to:
            continue
        ratio = f"{r['ratio_rights']}:{r['ratio_held']}" if r.get("ratio_rights") and r.get("ratio_held") else None
        out.append({"symbol": r["symbol"], "ratio": ratio, "issue_price": float(r["issue_price"]),
                    "re_from": frm, "re_to": to, "issue_close": r.get("issue_close"),
                    "re_symbol": r.get("re_symbol")})
    return out


def re_symbols(symbol: str, stored: str | None) -> list[str]:
    """NSE RE symbols vary (NDTVR, TILRR, SATIN-RE): try the stored one, then <SYM>-RE."""
    cands = [s for s in (stored, re_symbol(symbol)) if s]
    return list(dict.fromkeys(cands))


MIN_TURNOVER = 5e5   # Rs 5 lakh / day: below this an RE print isn't reliably tradable
HURDLE = 0.005       # 0.5% of S: RE brokerage/STT + a few weeks' capital lock on application money
PENNY_ISSUE, PENNY_STOCK = 10.0, 20.0  # validated on issue >= Rs 10 and stock >= Rs 20 only (tick noise)


def fetch_re_frame(symbol: str, start, end, stored_re: str | None = None) -> pd.DataFrame | None:
    """Daily RE close + turnover from nselib (first RE symbol that has data); None if none."""
    from nselib import capital_market as cm
    from scanner.pricestore import nse_frame_to_series
    raw = None
    for sym in re_symbols(symbol, stored_re):
        try:
            raw = cm.price_volume_and_deliverable_position_data(
                symbol=sym, from_date=pd.Timestamp(start).strftime("%d-%m-%Y"),
                to_date=pd.Timestamp(end).strftime("%d-%m-%Y"))
        except Exception:  # nselib raises on symbols with no data in the window
            raw = None
        if raw is not None and len(raw):
            break
    if raw is None or len(raw) == 0:
        return None
    d = pd.to_datetime(raw["Date"], format="%d-%b-%Y", errors="coerce")
    turn = pd.Series(pd.to_numeric(raw["TurnoverInRs"], errors="coerce").values, index=d).groupby(level=0).sum()
    df = pd.DataFrame({"close": nse_frame_to_series(raw), "turnover": turn}).dropna(subset=["close"])
    df.index.name = "date"
    return df if len(df) else None


def open_res(today=None) -> list[dict]:
    """Rights issues whose RE is trading now (credit/open date <= today <= renunciation date),
    with the latest gap and the deadlines (live scan)."""
    from scanner import db
    from scanner.pricestore import get_closes
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    iso = today.date().isoformat()
    rows = db.select_all("rights_issues", {
        "select": "symbol,issue_price,ratio_rights,ratio_held,record_date,re_credit_date,issue_open,"
                  "renunciation_date,issue_close,re_symbol,partly_paid,withdrawn",
        "issue_close": f"gte.{iso}"})
    out = []
    for e in events_from_issues(rows):
        if not (e["re_from"] <= iso <= e["re_to"]):
            continue
        re_df = fetch_re_frame(e["symbol"], pd.Timestamp(e["re_from"]) - pd.Timedelta(days=3), today, e["re_symbol"])
        if re_df is None:
            continue
        stock = get_closes(e["symbol"], today - pd.Timedelta(days=15), today, source="nse")
        g = gap_series(stock, re_df["close"], e["issue_price"]) if stock is not None else pd.Series(dtype=float)
        if not len(g):
            continue
        d = g.index.max()
        out.append({"symbol": e["symbol"], "ratio": e["ratio"], "issue_price": e["issue_price"],
                    "stock": float(stock.asof(d)), "re": float(re_df["close"].asof(d)),
                    "gap": float(g.iloc[-1]), "turnover": float(re_df["turnover"].asof(d)),
                    "re_date": d.date().isoformat(), "re_last_day": e["re_to"],
                    "issue_close": e["issue_close"]})
    return out


def re_action(r: dict) -> str:
    """What to do with an open RE (one rule for the CLI, the saved scan and the dashboard)."""
    if r["turnover"] < MIN_TURNOVER:
        return "illiquid"
    if r["issue_price"] < PENNY_ISSUE or r["stock"] < PENNY_STOCK:
        return "penny: tick noise, not validated"
    if r["gap"] > HURDLE:
        return "BUY RE (instead of the stock; subscribe)"
    if r["gap"] < -HURDLE:
        return "RE rich: holders sell RE, buy stock"
    return "fair"


def rights_candidates(rows: list[dict]) -> list[dict]:
    """open_res rows -> `candidates` rows (score = gap) for the dashboard panel."""
    keys = ("ratio", "issue_price", "stock", "re", "gap", "turnover", "re_date", "re_last_day",
            "issue_close")
    return [{"symbol": r["symbol"], "score": r["gap"],
             "payload": {**{k: r.get(k) for k in keys}, "action": re_action(r)}} for r in rows]


def format_open_res(rows: list[dict]) -> str:
    if not rows:
        return "No rights entitlements trading right now."
    out = [f"{'symbol':<12} {'ratio':<7} {'issue':>8} {'stock':>9} {'RE':>8} {'gap':>7} "
           f"{'RE turnover':>12} {'RE last':>10} {'apply by':>10}  action"]
    for r in sorted(rows, key=lambda r: -r["gap"]):
        act = re_action(r)
        out.append(f"{r['symbol']:<12} {r['ratio'] or '—':<7} {r['issue_price']:>8.2f} {r['stock']:>9.2f} "
                   f"{r['re']:>8.2f} {r['gap']*100:>6.2f}% {r['turnover']/1e5:>9.1f} L "
                   f"{r.get('re_last_day') or '—':>10} {r.get('issue_close') or '—':>10}  {act}")
    return "\n".join(out)

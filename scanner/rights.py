"""Rights-entitlement (RE) mispricing study (candidate signal #4).

Since Jan-2020 NSE lists rights entitlements as `<SYMBOL>-RE` (series BE) while the issue is
open. One RE + the issue price = one new share, so the RE's fair value is S - issue_price
(face value + premium). Gap = (S - issue - RE) / S: positive = the RE is cheap, i.e. a buyer
who wants the stock gets it cheaper via RE + subscription than via the market.

Pure logic (tested); runner scripts/validate_rights_re.py.
"""
from __future__ import annotations

import pandas as pd

SHARE_COUNT_CHANGES = {"split", "consolidation", "bonus"}  # make today's face value wrong


def issue_price(face_value, premium):
    if face_value is None or premium is None:
        return None
    return float(face_value) + float(premium)


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


def rights_events(rights: list[dict], face_values: dict, actions: list[dict]) -> list[dict]:
    """corporate_events rights rows -> study events with the issue price. Dropped: no face value
    on record, or a split/bonus/consolidation after the issue (today's FV isn't the old FV)."""
    out = []
    for r in rights:
        sym, d = r["symbol"], r["event_date"]
        fv = face_values.get(sym)
        det = r.get("details") or {}
        if fv is None or det.get("premium") is None:
            continue
        if any(a["symbol"] == sym and a["event_type"] in SHARE_COUNT_CHANGES and a["event_date"] > d
               for a in actions):
            continue
        out.append({"symbol": sym, "ex_date": d, "ratio": det.get("ratio"),
                    "premium": float(det["premium"]), "face_value": float(fv),
                    "issue_price": issue_price(fv, det["premium"])})
    return out


MIN_TURNOVER = 5e5   # Rs 5 lakh / day: below this an RE print isn't reliably tradable
HURDLE = 0.005       # 0.5% of S: RE brokerage/STT + a few weeks' capital lock on application money
PENNY_ISSUE, PENNY_STOCK = 10.0, 20.0  # validated on issue >= Rs 10 and stock >= Rs 20 only (tick noise)


def fetch_re_frame(symbol: str, start, end) -> pd.DataFrame | None:
    """Daily RE close + turnover from nselib (`<SYM>-RE`); None if it never traded."""
    from nselib import capital_market as cm
    from scanner.pricestore import nse_frame_to_series
    try:
        raw = cm.price_volume_and_deliverable_position_data(
            symbol=re_symbol(symbol), from_date=pd.Timestamp(start).strftime("%d-%m-%Y"),
            to_date=pd.Timestamp(end).strftime("%d-%m-%Y"))
    except Exception:  # nselib raises on symbols with no data in the window
        return None
    if raw is None or len(raw) == 0:
        return None
    d = pd.to_datetime(raw["Date"], format="%d-%b-%Y", errors="coerce")
    turn = pd.Series(pd.to_numeric(raw["TurnoverInRs"], errors="coerce").values, index=d).groupby(level=0).sum()
    df = pd.DataFrame({"close": nse_frame_to_series(raw), "turnover": turn}).dropna(subset=["close"])
    df.index.name = "date"
    return df if len(df) else None


def open_res(today=None, lookback_days: int = 40) -> list[dict]:
    """Rights issues whose RE traded in the last few days, with the latest gap (live scan)."""
    from scanner import db
    from scanner.pricestore import get_closes
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    since = (today - pd.Timedelta(days=lookback_days)).date().isoformat()
    rights = db.select_all("corporate_events", {"select": "symbol,event_date,record_date,details",
                                                "event_type": "eq.rights", "event_date": f"gte.{since}"})
    fv = {c["symbol"]: c["face_value"] for c in db.select_all(
        "companies", {"select": "symbol,face_value",
                      "symbol": f"in.({','.join(sorted({r['symbol'] for r in rights}))})"})} if rights else {}
    out = []
    for e in rights_events(rights, fv, []):
        re_df = fetch_re_frame(e["symbol"], pd.Timestamp(e["ex_date"]) - pd.Timedelta(days=3), today)
        if re_df is None or re_df.index.max() < today - pd.Timedelta(days=5):
            continue  # RE not trading (yet / any more)
        stock = get_closes(e["symbol"], today - pd.Timedelta(days=15), today, source="nse")
        g = gap_series(stock, re_df["close"], e["issue_price"]) if stock is not None else pd.Series(dtype=float)
        if not len(g):
            continue
        d = g.index.max()
        out.append({"symbol": e["symbol"], "ratio": e["ratio"], "issue_price": e["issue_price"],
                    "stock": float(stock.asof(d)), "re": float(re_df["close"].asof(d)),
                    "gap": float(g.iloc[-1]), "turnover": float(re_df["turnover"].asof(d)),
                    "re_date": d.date().isoformat()})
    return out


def format_open_res(rows: list[dict]) -> str:
    if not rows:
        return "No rights entitlements trading right now."
    out = [f"{'symbol':<12} {'ratio':<7} {'issue':>8} {'stock':>9} {'RE':>8} {'gap':>7} "
           f"{'RE turnover':>12}  action"]
    for r in sorted(rows, key=lambda r: -r["gap"]):
        if r["turnover"] < MIN_TURNOVER:
            act = "illiquid"
        elif r["issue_price"] < PENNY_ISSUE or r["stock"] < PENNY_STOCK:
            act = "penny: tick noise, not validated"
        elif r["gap"] > HURDLE:
            act = "BUY RE (instead of the stock; subscribe)"
        elif r["gap"] < -HURDLE:
            act = "RE rich: holders sell RE, buy stock"
        else:
            act = "fair"
        out.append(f"{r['symbol']:<12} {r['ratio'] or '—':<7} {r['issue_price']:>8.2f} {r['stock']:>9.2f} "
                   f"{r['re']:>8.2f} {r['gap']*100:>6.2f}% {r['turnover']/1e5:>9.1f} L  {act}")
    return "\n".join(out)

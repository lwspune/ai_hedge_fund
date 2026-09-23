"""Unified EOD price store (infra I2): one cached, guarded `get_closes` for every signal
and validation script.

Sources (FETCHERS):
  "yf"  — yfinance `.NS`, split/bonus-adjusted, full history. Default; also serves
          benchmarks (pass the raw Yahoo ticker, e.g. "^NSEI", with raw=True).
  "nse" — nselib bhavcopy-derived closes, EQ series only, UNADJUSTED. For delisted /
          historical symbols Yahoo lacks, and for ANY comparison against a nominal rupee
          price (buyback / open-offer / delisting price): Yahoo's back-adjustment for later
          splits and bonuses makes such premiums wrong (SPORTKING 1:10 split -> "+1282%").

Cache: `cache/px/<source>/<SYMBOL>.parquet` (full history per symbol) + `_fetched.json`
(fetch date per symbol). A symbol is refetched when its cache ends > STALE_DAYS before the
requested end and it wasn't already fetched that day. Every series passes `clean_series`.

Replaces the old per-script caches in `cache/prices/`, whose millisecond timestamps now read
back as 1970 dates under pandas 3 + fastparquet — this store round-trip-tests its own format.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "px"
STALE_DAYS = 4           # weekend + a holiday
MIN_YEAR = 1990          # anything earlier is a corrupt timestamp, not NSE history
SPIKE = 1.0              # a >100% one-day move that fully reverts next day = bad print


class BadPriceData(ValueError):
    """Raised when a price series is structurally corrupt (not just noisy)."""


def clean_series(s: pd.Series) -> pd.Series:
    """Sort, dedupe (keep last print per date), drop NaN/non-positive and isolated spikes
    that fully revert the next day. Raises BadPriceData on pre-1990 timestamps."""
    s = pd.Series(pd.to_numeric(s, errors="coerce"), index=pd.DatetimeIndex(s.index))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s[s > 0].dropna().astype("float64")
    if len(s) and s.index.min().year < MIN_YEAR:
        raise BadPriceData(f"timestamp before {MIN_YEAR}: {s.index.min()}")
    if len(s) >= 3:
        prev, nxt = s.shift(1), s.shift(-1)
        jump = (s / prev - 1).abs()
        revert = (nxt / prev - 1).abs()
        s = s[~((jump > SPIKE) & (revert < 0.2 * jump))]
    s.index = pd.DatetimeIndex(s.index.as_unit("ns"), freq=None, name="date")
    return s


def write_cache(fp: Path, s: pd.Series) -> None:
    fp.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex(s.index).as_unit("us")  # MICROS round-trips; MILLIS did not
    pd.DataFrame({"close": s.values}, index=idx.rename("date")).to_parquet(fp)


def read_cache(fp: Path) -> pd.Series:
    df = pd.read_parquet(fp)
    return clean_series(pd.Series(df["close"].values, index=df.index))


# --- fetchers (network; not unit-tested) ------------------------------------

def _fetch_yf(symbol: str, raw: bool = False) -> pd.Series:
    import yfinance as yf
    ticker = symbol if raw else f"{symbol}.NS"
    h = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=True)
    if h is None or h.empty:
        return pd.Series(dtype="float64")
    s = h["Close"].dropna()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s


def _fetch_nse(symbol: str, start: str = "2010-01-01") -> pd.Series:
    from nselib import capital_market as cm
    parts = []
    for y in range(pd.Timestamp(start).year, pd.Timestamp.today().year + 1):
        f = pd.Timestamp(max(pd.Timestamp(start), pd.Timestamp(f"{y}-01-01")))
        t = min(pd.Timestamp(f"{y}-12-31"), pd.Timestamp.today())
        try:
            df = cm.price_volume_and_deliverable_position_data(
                symbol=symbol, from_date=f.strftime("%d-%m-%Y"), to_date=t.strftime("%d-%m-%Y"))
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        df = df[df["Series"].astype(str).str.strip() == "EQ"] if "Series" in df else df
        d = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
        c = pd.to_numeric(df["ClosePrice"].astype(str).str.replace(",", ""), errors="coerce")
        parts.append(pd.Series(c.values, index=d.values))
    return pd.concat(parts) if parts else pd.Series(dtype="float64")


FETCHERS = {"yf": _fetch_yf, "nse": _fetch_nse}


# --- public API --------------------------------------------------------------

def _fetched_log(d: Path) -> dict:
    fp = d / "_fetched.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_closes(symbol: str, start=None, end=None, source: str = "yf",
               cache_dir: Path | None = None, today=None) -> pd.Series | None:
    """Daily closes for `symbol` in [start, end] (inclusive), cleaned; None if the source has
    nothing. Benchmarks: get_closes("^NSEI") (a leading ^ is passed to Yahoo verbatim)."""
    d = Path(cache_dir or CACHE_DIR) / source
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    target = min(pd.Timestamp(end), today) if end is not None else today
    safe = symbol.replace("^", "_").replace("&", "_and_")
    fp = d / f"{safe}.parquet"
    log = _fetched_log(d)

    s = read_cache(fp) if fp.exists() else None
    fresh = s is not None and (
        (len(s) and s.index.max() >= target - pd.Timedelta(days=STALE_DAYS))
        or log.get(symbol) == today.date().isoformat())
    if not fresh:
        fetch = FETCHERS[source]
        raw = fetch(symbol, raw=True) if (source == "yf" and symbol.startswith("^")) else fetch(symbol)
        s = clean_series(raw) if len(raw) else pd.Series(dtype="float64")
        write_cache(fp, s)
        log[symbol] = today.date().isoformat()
        (d / "_fetched.json").write_text(json.dumps(log, indent=0), encoding="utf-8")
    if s is None or not len(s):
        return None
    lo = pd.Timestamp(start) if start is not None else s.index.min()
    hi = pd.Timestamp(end) if end is not None else s.index.max()
    out = s[(s.index >= lo) & (s.index <= hi)]
    return out if len(out) else None

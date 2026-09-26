"""Unified EOD price store (infra I2): one cached, guarded `get_closes` for every signal
and validation script.

`source` is REQUIRED on every call (no default: adjusted Yahoo closes silently used for a
nominal-price premium is a bug class this store exists to prevent).

  "db"  — the cloud store (DATA_INFRA_SPEC WP3): Supabase `daily_prices` (~2 years) + the
          `prices` bucket month files (2020->), from NSE bhavcopies. UNADJUSTED. Benchmarks
          ("^NSEI", "^CRSLDX") from `index_prices`. `get_bars` adds volume/turnover/delivery.
          Works on any runner — use it for scans and anything compared to a nominal price.
Local-cache sources (FETCHERS):
  "yf"  — yfinance `.NS`, split/bonus-adjusted, full history — return studies only. Also
          serves benchmarks (pass the raw Yahoo ticker, e.g. "^NSEI", with raw=True).
  "nse" — nselib closes, equity series only (EQ preferred; BE/BZ/SME SM/ST/SZ kept), UNADJUSTED,
          fetched from the requested `start` (coverage tracked in `_fetched.json`). For delisted /
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


# Real equity series, in preference order when one date prints in several (EQ first).
# Excludes warrants (W*), rights entitlements (E*/RE), debt, etc. SM/ST/SZ = SME board.
NSE_SERIES = ("EQ", "BE", "BZ", "SM", "ST", "SZ")
NSE_FROM = "2010-01-01"


def nse_frame_to_series(df: pd.DataFrame) -> pd.Series:
    """nselib price frame -> close series: allowed series only, one print per date (EQ first)."""
    if df is None or len(df) == 0:
        return pd.Series(dtype="float64")
    ser = df["Series"].astype(str).str.strip() if "Series" in df else pd.Series("EQ", index=df.index)
    rank = ser.map({s: i for i, s in enumerate(NSE_SERIES)})
    d = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
    c = pd.to_numeric(df["ClosePrice"].astype(str).str.replace(",", ""), errors="coerce")
    f = pd.DataFrame({"d": d, "c": c, "r": rank}).dropna().sort_values(["d", "r"])
    f = f.drop_duplicates("d", keep="first")
    return pd.Series(f["c"].values, index=pd.DatetimeIndex(f["d"].values), dtype="float64")


def _fetch_nse(symbol: str, start: str = NSE_FROM, end=None) -> pd.Series:
    from nselib import capital_market as cm
    parts = []
    last = min(pd.Timestamp(end), pd.Timestamp.today()) if end is not None else pd.Timestamp.today()
    for y in range(pd.Timestamp(start).year, last.year + 1):
        f = pd.Timestamp(max(pd.Timestamp(start), pd.Timestamp(f"{y}-01-01")))
        t = min(pd.Timestamp(f"{y}-12-31"), last)
        try:
            df = cm.price_volume_and_deliverable_position_data(
                symbol=symbol, from_date=f.strftime("%d-%m-%Y"), to_date=t.strftime("%d-%m-%Y"))
        except Exception:
            continue
        parts.append(nse_frame_to_series(df))
    parts = [x for x in parts if len(x)]
    return pd.concat(parts) if parts else pd.Series(dtype="float64")


FETCHERS = {"yf": _fetch_yf, "nse": _fetch_nse}


# --- source="db": the cloud store (DATA_INFRA_SPEC WP3) ------------------------------------
# Recent ~2 years from the Supabase `daily_prices` table; older dates from the `prices` bucket
# month files (bhav/YYYY-MM.parquet, raw bhavcopy, 2020->), cached in cache/px/bhav/.
# Benchmarks ("^NSEI", "^CRSLDX") come from `index_prices`. UNADJUSTED closes.

BAR_COLS = ["close", "volume", "turnover_lakh", "delivery_pct"]
_BHAV_COLS = {"CLOSE_PRICE": "close", "TTL_TRD_QNTY": "volume", "TURNOVER_LACS": "turnover_lakh",
              "DELIV_PER": "delivery_pct"}
_month_mem: dict = {}


def _db_rows(symbol: str, lo: str, hi: str) -> list[dict]:
    from scanner import db
    if symbol.startswith("^"):
        return db.select_all("index_prices", {"select": "trade_date,close", "index_symbol": f"eq.{symbol}",
                                              "and": f"(trade_date.gte.{lo},trade_date.lte.{hi})",
                                              "order": "trade_date"})
    return db.select_all("daily_prices", {"select": "trade_date," + ",".join(BAR_COLS),
                                          "symbol": f"eq.{symbol}",
                                          "and": f"(trade_date.gte.{lo},trade_date.lte.{hi})",
                                          "order": "trade_date"})


_floor_mem: list = []


def _table_floor() -> pd.Timestamp:
    """Earliest date held in daily_prices (older dates are read from the bucket)."""
    if not _floor_mem:
        from scanner import db
        rows = db.select("daily_prices", {"select": "trade_date", "order": "trade_date", "limit": "1"})
        _floor_mem.append(pd.Timestamp(rows[0]["trade_date"]) if rows else pd.Timestamp.max)
    return _floor_mem[0]


def _bhav_month(ym: str) -> pd.DataFrame | None:
    """Raw bhavcopy frame for one month from the bucket; closed months are cached on disk."""
    if ym in _month_mem:
        return _month_mem[ym]
    fp = CACHE_DIR / "bhav" / f"{ym}.parquet"
    closed = ym < pd.Timestamp.today().strftime("%Y-%m")
    df = None
    if closed and fp.exists():
        df = pd.read_parquet(fp)
    else:
        import io
        from scanner import db
        blob = db.storage_get("prices", f"bhav/{ym}.parquet")
        if blob:
            df = pd.read_parquet(io.BytesIO(blob))
            if closed:
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(blob)
    _month_mem[ym] = df
    return df


def first_bar(symbol: str, day, max_days: int = 10) -> dict | None:
    """The first session on/after `day` (within `max_days`) from the raw bhavcopy months, with its
    OPEN — the table keeps closes only. For listing-day studies: {"date", "open", "close"} or None."""
    lo = pd.Timestamp(day).normalize()
    hi = lo + pd.Timedelta(days=max_days)
    rank = {s: i for i, s in enumerate(NSE_SERIES)}
    for m in pd.period_range(lo, hi, freq="M"):
        raw = _bhav_month(str(m))
        if raw is None or raw.empty:
            continue
        f = raw[(raw["SYMBOL"] == symbol) & raw["SERIES"].isin(NSE_SERIES)
                & (raw["DATE1"] >= lo) & (raw["DATE1"] <= hi)]
        if len(f):
            r = f.assign(_r=f["SERIES"].map(rank)).sort_values(["DATE1", "_r"]).iloc[0]
            return {"date": r["DATE1"], "open": float(r["OPEN_PRICE"]), "close": float(r["CLOSE_PRICE"])}
    return None


def _month_bars(symbol: str, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for m in pd.period_range(lo, hi, freq="M"):
        raw = _bhav_month(str(m))
        if raw is None or raw.empty:
            continue
        f = raw[(raw["SYMBOL"] == symbol) & raw["SERIES"].isin(NSE_SERIES)
                & (raw["DATE1"] >= lo) & (raw["DATE1"] <= hi)]
        if len(f):
            f = (f.assign(_r=f["SERIES"].map({s: i for i, s in enumerate(NSE_SERIES)}))
                  .sort_values(["DATE1", "_r"]).drop_duplicates("DATE1"))
            frames.append(f.set_index("DATE1").rename(columns=_BHAV_COLS)[BAR_COLS])
    return pd.concat(frames) if frames else pd.DataFrame(columns=BAR_COLS)


def get_bars(symbol: str, start, end) -> pd.DataFrame | None:
    """Daily close / volume / turnover (lakh) / delivery % from the cloud store, [start, end]."""
    lo = pd.Timestamp(start).normalize()
    hi = pd.Timestamp(end if end is not None else pd.Timestamp.today()).normalize()
    if symbol.startswith("^"):  # benchmarks: index_prices only, close only
        rows = _db_rows(symbol, lo.date().isoformat(), hi.date().isoformat())
        df = pd.DataFrame(rows, columns=["trade_date", "close"])
        df = df.set_index(pd.to_datetime(df["trade_date"]))[["close"]].reindex(columns=BAR_COLS)
    else:
        floor = _table_floor()
        parts = []
        if lo < floor:
            parts.append(_month_bars(symbol, lo, min(hi, floor - pd.Timedelta(days=1))))
        if hi >= floor:
            rows = _db_rows(symbol, max(lo, floor).date().isoformat(), hi.date().isoformat())
            t = pd.DataFrame(rows, columns=["trade_date", *BAR_COLS])
            parts.append(t.set_index(pd.to_datetime(t["trade_date"]))[BAR_COLS])
        parts = [p for p in parts if len(p)]
        df = pd.concat(parts) if parts else pd.DataFrame(columns=BAR_COLS)
    if df.empty:
        return None
    df.index = pd.DatetimeIndex(df.index, name="date")
    return df.sort_index()


def _db_closes(symbol: str, start, end) -> pd.Series | None:
    bars = get_bars(symbol, start if start is not None else "2020-01-01", end)
    if bars is None:
        return None
    s = clean_series(bars["close"])
    return s if len(s) else None


# --- public API --------------------------------------------------------------

def _fetched_log(d: Path) -> dict:
    fp = d / "_fetched.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_closes(symbol: str, start=None, end=None, *, source: str,
               cache_dir: Path | None = None, today=None) -> pd.Series | None:
    """Daily closes for `symbol` in [start, end] (inclusive), cleaned; None if the source has
    nothing. `source` is required — "db" (cloud store, unadjusted, 2020->), "nse" (nselib,
    unadjusted, any date) or "yf" (Yahoo, split/bonus-ADJUSTED: only for return studies, never
    a premium against a nominal price). Benchmarks: get_closes("^NSEI", source="db"|"yf")."""
    if source == "db":
        return _db_closes(symbol, start, end)
    d = Path(cache_dir or CACHE_DIR) / source
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    target = min(pd.Timestamp(end), today) if end is not None else today
    safe = symbol.replace("^", "_").replace("&", "_and_")
    fp = d / f"{safe}.parquet"
    log = _fetched_log(d)
    entry = log.get(symbol)
    if isinstance(entry, str):  # legacy log format: fetch date only, full history
        entry = {"on": entry, "from": NSE_FROM}
    # nse fetches are windowed (one request per year): only pull from the requested start.
    need_from = (pd.Timestamp(start).date().isoformat() if start is not None else NSE_FROM)         if source == "nse" else None
    covered = need_from is None or (entry and entry.get("from") and entry["from"] <= need_from)

    s = read_cache(fp) if fp.exists() else None
    fresh = s is not None and covered and (
        (len(s) and s.index.max() >= target - pd.Timedelta(days=STALE_DAYS))
        # fetched today already (e.g. a delisted symbol whose data just ends) — unless that
        # fetch was window-bounded short of what is asked now
        or ((entry or {}).get("on") == today.date().isoformat()
            and (entry or {}).get("to", "9999") >= target.date().isoformat()))
    if not fresh:
        fetch = FETCHERS[source]
        if source == "yf" and symbol.startswith("^"):
            raw = fetch(symbol, raw=True)
        elif source == "nse":  # bounded to the requested end: one nselib call per year
            raw = fetch(symbol, start=need_from, end=target.date().isoformat())
        else:
            raw = fetch(symbol)
        s = clean_series(raw) if len(raw) else pd.Series(dtype="float64")
        write_cache(fp, s)
        log[symbol] = {"on": today.date().isoformat(), "from": need_from,
                       "to": target.date().isoformat()}
        (d / "_fetched.json").write_text(json.dumps(log, indent=0), encoding="utf-8")
    if s is None or not len(s):
        return None
    lo = pd.Timestamp(start) if start is not None else s.index.min()
    hi = pd.Timestamp(end) if end is not None else s.index.max()
    out = s[(s.index >= lo) & (s.index <= hi)]
    return out if len(out) else None

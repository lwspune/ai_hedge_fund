"""NSE daily bhavcopy (`sec_bhavdata_full_DDMMYYYY.csv`) — the input of the cloud price store
(DATA_INFRA_SPEC WP3).

One static CSV per trading day on nsearchives (reachable from GitHub runners; non-trading days
404; archive probed back to 2019). Closes are UNADJUSTED by construction — the right basis for
any premium against a nominal rupee price (buyback / open offer / rights issue price).

  parse_bhavcopy -> rows for the `daily_prices` table (equity series, one per symbol, guarded)
  parse_raw      -> every column and series as published, for the `prices` bucket
                    (`bhav/YYYY-MM.parquet`, the durable full history)
  parse_index_closes -> NSE's daily index-close file (`ind_close_all_DDMMYYYY.csv`), the fallback for
                    the benchmark sessions Yahoo misses (Muhurat, Budget Saturdays, some 1 Jan / 26 Dec)
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

BHAV_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
# Equity series in preference order when one symbol prints in several (same rule as
# pricestore.NSE_SERIES): EQ first; BE/BZ trade-for-trade; SM/ST/SZ = SME board.
SERIES_RANK = {s: i for i, s in enumerate(("EQ", "BE", "BZ", "SM", "ST", "SZ"))}
MIN_EQ_ROWS = 1000        # a real trading day has ~2,700 EQ rows; fewer = truncated / wrong file
_NUM = ["PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE",
        "AVG_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER"]


class BadBhavcopy(ValueError):
    """The file is structurally wrong (truncated, mixed dates, impossible prices)."""


def bhav_url(d: date) -> str:
    return BHAV_URL.format(d=d)


def parse_raw(text: str) -> pd.DataFrame:
    """Every row/column as published: headers and values stripped, `-` -> NaN, DATE1 parsed."""
    df = pd.read_csv(io.StringIO(text), dtype=str, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda c: c.str.strip())
    for c in _NUM:
        if c in df:
            df[c] = pd.to_numeric(df[c].replace("-", None), errors="coerce")
    df["DATE1"] = pd.to_datetime(df["DATE1"], format="%d-%b-%Y", errors="coerce")
    return df


def _opt(v):
    return None if pd.isna(v) else v


def parse_bhavcopy(text: str, min_eq: int = MIN_EQ_ROWS) -> list[dict]:
    """`daily_prices` rows: equity series only, one per symbol (EQ preferred). Raises BadBhavcopy
    on a truncated file (< min_eq EQ rows), mixed dates or any close <= 0."""
    df = parse_raw(text)
    df = df[df["SERIES"].isin(SERIES_RANK)]
    if (df["SERIES"] == "EQ").sum() < min_eq:
        raise BadBhavcopy(f"only {(df['SERIES'] == 'EQ').sum()} EQ rows (< {min_eq})")
    dates = df["DATE1"].dropna().unique()
    if len(dates) != 1 or df["DATE1"].isna().any():
        raise BadBhavcopy(f"expected one trade date, got {len(dates)}")
    if (df["CLOSE_PRICE"].isna() | (df["CLOSE_PRICE"] <= 0)).any():
        raise BadBhavcopy("close <= 0 or missing")
    df = (df.assign(_r=df["SERIES"].map(SERIES_RANK)).sort_values(["SYMBOL", "_r"])
            .drop_duplicates("SYMBOL", keep="first"))
    day = pd.Timestamp(dates[0]).date().isoformat()
    return [{"symbol": r.SYMBOL, "trade_date": day, "series": r.SERIES, "close": float(r.CLOSE_PRICE),
             "prev_close": _opt(r.PREV_CLOSE),
             "volume": None if pd.isna(r.TTL_TRD_QNTY) else int(r.TTL_TRD_QNTY),
             "turnover_lakh": _opt(r.TURNOVER_LACS), "delivery_pct": _opt(r.DELIV_PER)}
            for r in df.itertuples()]


def to_month_frame(month: pd.DataFrame | None, day: pd.DataFrame) -> pd.DataFrame:
    """Merge one day's raw frame into its month's frame, replacing that date if already there."""
    if month is None or month.empty:
        out = day
    else:
        dates = set(day["DATE1"].dropna().unique())
        out = pd.concat([month[~month["DATE1"].isin(dates)], day], ignore_index=True)
    return out.sort_values(["DATE1", "SYMBOL", "SERIES"], kind="stable").reset_index(drop=True)


def decode_bhavcopy(content: bytes) -> str:
    """CSV text from the archive's bytes. Some days (2022-08-08) NSE serves an Excel workbook
    under the .csv name; it carries the same columns, so it is re-emitted as CSV."""
    if content[:2] == b"PK":                       # zip container = .xlsx
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        return df.to_csv(index=False)
    return content.decode("utf-8", errors="replace")


def fetch_bhavcopy(d: date, session=None) -> str | None:
    """The day's CSV text; None on 404 (non-trading day / not yet published). Other errors raise."""
    import requests
    r = (session or requests).get(bhav_url(d), headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return decode_bhavcopy(r.content)


# --- NSE daily index closes ---------------------------------------------------------------

INDEX_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
NSE_INDEX_NAMES = {"nifty 50": "^NSEI", "nifty 500": "^CRSLDX"}   # exact names; "Nifty Next 50" is another index


def index_url(d: date) -> str:
    return INDEX_URL.format(d=d)


def parse_index_closes(text: str, names: dict[str, str] | None = None) -> dict:
    """{index_symbol: {date, close, change}} for the indices in `names` ({lowercase NSE name: symbol};
    default: the NIFTY 50 / NIFTY 500 benchmarks) in one day's index-close file. Rows whose date or close
    can't be read are skipped (never a guessed value)."""
    import csv
    from datetime import datetime
    names = NSE_INDEX_NAMES if names is None else names
    out = {}
    rows = csv.reader(io.StringIO(text or ""))
    header = [h.strip() for h in next(rows, [])]
    col = {h: i for i, h in enumerate(header)}
    need = ("Index Name", "Index Date", "Closing Index Value")
    if not all(k in col for k in need):
        return out
    for rec in rows:
        sym = names.get(rec[col["Index Name"]].strip().lower()) if rec else None
        if not sym:
            continue
        try:
            d = datetime.strptime(rec[col["Index Date"]].strip(), "%d-%m-%Y").date()
            close = float(rec[col["Closing Index Value"]])
        except (ValueError, IndexError):
            continue
        try:
            change = float(rec[col["Points Change"]]) if "Points Change" in col else None
        except (ValueError, IndexError):
            change = None
        out[sym] = {"date": d, "close": close, "change": change}
    return out


def confirm_close(prev: float | None, close: float, change: float | None) -> bool:
    """NSE's close agrees with the stored previous close + NSE's points change (within rounding: the
    table stores `real`). The guard that keeps a wrong day's or wrong index's file out."""
    if prev is None or change is None:
        return False
    return abs(prev + change - close) <= max(1.0, 5e-5 * close)


def fetch_index_closes(d: date, session=None) -> str | None:
    """The day's index-close CSV text; None on 404 (no such session). Other errors raise."""
    import requests
    r = (session or requests).get(index_url(d), headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")

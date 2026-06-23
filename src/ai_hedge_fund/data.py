"""Data layer: yfinance fetch with parquet cache."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import yfinance as yf


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ohlcv_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str) -> Path:
    safe = ticker.replace(":", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}.parquet"


def fetch_ohlc(
    ticker: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch daily OHLC for one ticker. Caches to parquet keyed by ticker.

    Returns DataFrame with columns: Open, High, Low, Close, Volume; DatetimeIndex.
    """
    cache_file = _cache_path(ticker)
    if use_cache and cache_file.exists():
        df = pd.read_parquet(cache_file)
        # If the cache covers the requested range, return it; otherwise re-fetch.
        if df.index[0] <= pd.Timestamp(start) and df.index[-1] >= pd.Timestamp(end) - pd.Timedelta(days=7):
            return df.loc[pd.Timestamp(start) : pd.Timestamp(end)]

    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Date"
    df.to_parquet(cache_file)
    return df


def fetch_universe_closes(
    tickers: list[str],
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DataFrame:
    """Fetch closes for many tickers, return a DataFrame (date × ticker) of close prices."""
    closes = {}
    failed = []
    for t in tickers:
        try:
            df = fetch_ohlc(t, start, end)
            if df.empty or "Close" not in df.columns:
                failed.append(t)
                continue
            closes[t] = df["Close"]
        except Exception as e:
            print(f"  ! {t}: {e}")
            failed.append(t)
    if failed:
        print(f"  Failed/empty for {len(failed)} tickers: {failed}")
    if not closes:
        return pd.DataFrame()
    return pd.DataFrame(closes).sort_index()

"""EOD close fetchers for NSE equities (free sources).

Primary: yfinance (`.NS`), split/bonus-adjusted and proven for this universe.
Fallback: jugaad-data (official NSE bhavcopy) when Yahoo rate-limits or returns
nothing. Both return a plain list of closes, oldest first.
"""
from __future__ import annotations

from datetime import date, timedelta


def fetch_closes_yf(symbol: str, period: str = "2y") -> list[float]:
    import yfinance as yf

    hist = yf.Ticker(f"{symbol}.NS").history(
        period=period, interval="1d", auto_adjust=True
    )
    closes = hist["Close"].dropna().tolist() if not hist.empty else []
    if len(closes) < 200:
        raise RuntimeError(f"yfinance returned {len(closes)} closes for {symbol}")
    return [float(c) for c in closes]


def fetch_closes_jugaad(symbol: str, lookback_days: int = 420) -> list[float]:
    from jugaad_data.nse import stock_df

    to_d = date.today()
    from_d = to_d - timedelta(days=lookback_days)
    df = stock_df(symbol=symbol, from_date=from_d, to_date=to_d, series="EQ")
    if df is None or df.empty:
        raise RuntimeError(f"jugaad-data returned nothing for {symbol}")
    df = df.sort_values("DATE")
    return [float(c) for c in df["CLOSE"].tolist()]


def fetch_closes(symbol: str) -> tuple[list[float], str]:
    """Return (closes, source_used). Tries yfinance, falls back to jugaad-data."""
    try:
        return fetch_closes_yf(symbol), "yfinance"
    except Exception as e_yf:
        try:
            return fetch_closes_jugaad(symbol), "jugaad"
        except Exception as e_jg:
            raise RuntimeError(
                f"both price sources failed for {symbol}: yf={e_yf!r} jugaad={e_jg!r}"
            )

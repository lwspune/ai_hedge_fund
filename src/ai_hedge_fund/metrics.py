"""Performance metrics for equity curves."""
from __future__ import annotations

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def cagr(equity: pd.Series) -> float:
    """Compound annual growth rate from an equity curve."""
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return float("nan")
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return total_return ** (1 / years) - 1


def daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def sharpe_ratio(equity: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio (assumes daily series, 252 trading days/year)."""
    rets = daily_returns(equity)
    if len(rets) < 2:
        return float("nan")
    excess = rets - risk_free / TRADING_DAYS_PER_YEAR
    sd = excess.std()
    if sd == 0 or np.isnan(sd):
        return float("inf") if excess.mean() > 0 else float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(equity: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio — Sharpe but using downside std."""
    rets = daily_returns(equity)
    if len(rets) < 2:
        return float("nan")
    excess = rets - risk_free / TRADING_DAYS_PER_YEAR
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf") if excess.mean() > 0 else float("nan")
    dd_std = downside.std()
    if dd_std == 0 or np.isnan(dd_std):
        return float("inf") if excess.mean() > 0 else float("nan")
    return float(excess.mean() / dd_std * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough drawdown, expressed as a (negative) fraction."""
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return float(drawdown.min())


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return float("nan")
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def summarize(equity: pd.Series) -> dict:
    return {
        "cagr": cagr(equity),
        "sharpe": sharpe_ratio(equity),
        "sortino": sortino_ratio(equity),
        "max_drawdown": max_drawdown(equity),
        "total_return": total_return(equity),
    }

"""Portfolio backtester: equal-weight signal-driven, daily rebalance, per-leg costs."""
from __future__ import annotations

import numpy as np
import pandas as pd


def run_backtest(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    initial_capital: float = 100_000.0,
    cost_per_trade: float = 0.003,
) -> dict:
    """Run a daily-rebalanced equal-weight backtest.

    Args:
        prices: DataFrame (date × ticker) of close prices. NaN = no price for that day.
        signals: DataFrame (date × ticker) of booleans. True = include in target portfolio.
        initial_capital: starting cash.
        cost_per_trade: fractional cost per leg (e.g. 0.003 = 0.3% per buy *or* sell).

    Returns:
        dict with:
            - "equity": pd.Series of total portfolio value per day
            - "cash": pd.Series of cash component
            - "holdings": pd.DataFrame of share counts per ticker per day
            - "trades": pd.DataFrame of trade notional per ticker per day (+ buy / − sell)
    """
    if not prices.index.equals(signals.index):
        raise ValueError("prices and signals must share the same date index")
    tickers = list(prices.columns)
    if list(signals.columns) != tickers:
        raise ValueError("prices and signals must share the same ticker columns")

    n_days = len(prices)
    cash = initial_capital
    shares = {t: 0.0 for t in tickers}

    equity_curve = np.zeros(n_days)
    cash_curve = np.zeros(n_days)
    holdings_log = np.zeros((n_days, len(tickers)))
    trades_log = np.zeros((n_days, len(tickers)))

    prices_arr = prices.to_numpy()
    signals_arr = signals.to_numpy()

    for d in range(n_days):
        day_prices = prices_arr[d]
        day_signals = signals_arr[d]

        # Mark of holdings using last-known price (handle NaN by carrying forward)
        # For target sizing we only consider stocks with valid prices today.
        valid_mask = ~np.isnan(day_prices)

        # Compute current portfolio value (use today's price where valid, else previous price for the
        # stock we already hold — ensures NaN doesn't propagate into equity).
        portfolio_value = cash
        for i, t in enumerate(tickers):
            if shares[t] != 0:
                if valid_mask[i]:
                    portfolio_value += shares[t] * day_prices[i]
                else:
                    # use last non-nan price up to and including today
                    px = prices.iloc[: d + 1, i].dropna()
                    if len(px) > 0:
                        portfolio_value += shares[t] * px.iloc[-1]

        # Active signals: stock must have signal True AND a valid price today
        active = [i for i, t in enumerate(tickers) if day_signals[i] and valid_mask[i]]
        n_active = len(active)

        # Target shares: equal-weight cash allocation across active signals
        target_shares = {t: 0.0 for t in tickers}
        if n_active > 0:
            per_stock_target_value = portfolio_value / n_active
            for i in active:
                target_shares[tickers[i]] = per_stock_target_value / day_prices[i]
        # Stocks with NaN price today: hold whatever shares we have (no rebalance)
        for i, t in enumerate(tickers):
            if not valid_mask[i]:
                target_shares[t] = shares[t]

        # Execute rebalance: trade = target - current
        for i, t in enumerate(tickers):
            delta = target_shares[t] - shares[t]
            if abs(delta) < 1e-9:
                continue
            if not valid_mask[i]:
                continue  # cannot trade without a price
            notional = abs(delta) * day_prices[i]
            cost = notional * cost_per_trade
            cash -= delta * day_prices[i]  # buy → delta>0 → cash decreases
            cash -= cost
            shares[t] = target_shares[t]
            trades_log[d, i] = delta * day_prices[i]

        # End-of-day equity (re-mark with latest valid price)
        eod_value = cash
        for i, t in enumerate(tickers):
            if shares[t] != 0:
                if valid_mask[i]:
                    eod_value += shares[t] * day_prices[i]
                else:
                    px = prices.iloc[: d + 1, i].dropna()
                    if len(px) > 0:
                        eod_value += shares[t] * px.iloc[-1]
        equity_curve[d] = eod_value
        cash_curve[d] = cash
        for i, t in enumerate(tickers):
            holdings_log[d, i] = shares[t]

    return {
        "equity": pd.Series(equity_curve, index=prices.index, name="equity"),
        "cash": pd.Series(cash_curve, index=prices.index, name="cash"),
        "holdings": pd.DataFrame(holdings_log, index=prices.index, columns=tickers),
        "trades": pd.DataFrame(trades_log, index=prices.index, columns=tickers),
    }

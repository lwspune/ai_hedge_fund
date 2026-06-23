"""Run the mean-reversion screen over a small universe and print candidates.

Spike entrypoint: proves the free data stack (yfinance/jugaad prices +
screener.in fundamentals) feeds the pure signal end to end. No DB, no schedule.

    python -m scanner.scan
"""
from __future__ import annotations

from scanner.prices import fetch_closes
from scanner.fundamentals import fetch_fundamentals
from scanner.signals import evaluate

# A handful of liquid NIFTY names across sectors — enough to prove the pipeline.
UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC",
    "SBIN", "TATASTEEL", "HINDALCO", "COALINDIA", "ONGC",
]

CFG = {
    "rsi_period": 14,
    "dma_window": 200,
    "rsi_max": 30,          # oversold
    "below_dma_min": 0.20,  # >= 20% below the 200-DMA
    "min_mcap_cr": 20_000,  # large-cap quality floor
    "max_de": 0.50,         # low-debt quality ceiling
}


def scan(universe=UNIVERSE, cfg=CFG) -> list[dict]:
    rows = []
    for sym in universe:
        try:
            closes, psrc = fetch_closes(sym)
            fund = fetch_fundamentals(sym)
            res = evaluate(closes, fund["market_cap_cr"], fund["debt_to_equity"], cfg)
            res.update(symbol=sym, price=round(closes[-1], 2), price_src=psrc)
            rows.append(res)
        except Exception as e:  # one bad name shouldn't kill the scan
            rows.append({"symbol": sym, "error": repr(e)})
    return rows


def _fmt(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    bad = [r for r in rows if "error" in r]
    # Most oversold first: deepest below the 200-DMA, then lowest RSI.
    ok.sort(key=lambda r: (r["pct_from_dma"], r["rsi"]))

    head = f"{'SYM':<11}{'PRICE':>9}{'RSI':>7}{'vs200DMA':>10}{'MCAP_CR':>11}{'D/E':>7}  SIGNAL"
    lines = [head, "-" * len(head)]
    for r in ok:
        de = "-" if r["debt_to_equity"] is None else f"{r['debt_to_equity']:.2f}"
        mc = "-" if r["market_cap_cr"] is None else f"{r['market_cap_cr']:,.0f}"
        flag = "*** BUY" if r["signal"] else ""
        lines.append(
            f"{r['symbol']:<11}{r['price']:>9,.2f}{r['rsi']:>7.1f}"
            f"{r['pct_from_dma']*100:>9.1f}%{mc:>11}{de:>7}  {flag}"
        )
    for r in bad:
        lines.append(f"{r['symbol']:<11} ERROR {r['error']}")
    hits = sum(1 for r in ok if r["signal"])
    lines.append("-" * len(head))
    lines.append(f"{len(ok)} scanned, {len(bad)} failed, {hits} candidate(s).")
    return "\n".join(lines)


if __name__ == "__main__":
    print(_fmt(scan()))

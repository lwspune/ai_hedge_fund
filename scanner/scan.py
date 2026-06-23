"""Run the mean-reversion screen over the universe and print ranked candidates.

    python -m scanner.scan                      # NIFTY 50, non-financials, defaults
    python -m scanner.scan --rsi-max 35 --below-dma 0.15
    python -m scanner.scan --include-financials --limit 10

No DB, no schedule yet — this is the same code the scheduler will eventually run.
"""
from __future__ import annotations

import argparse

from scanner.prices import fetch_closes
from scanner.fundamentals import fetch_fundamentals
from scanner.signals import evaluate
from scanner.universe import load_symbols, select_universe


def build_cfg(args) -> dict:
    return {
        "rsi_period": 14,
        "dma_window": 200,
        "rsi_max": args.rsi_max,
        "below_dma_min": args.below_dma,
        "min_mcap_cr": args.min_mcap,
        "max_de": args.max_de,
    }


def scan(symbols, cfg) -> list[dict]:
    rows = []
    for sym in symbols:
        try:
            closes, psrc = fetch_closes(sym)
            fund = fetch_fundamentals(sym)
            res = evaluate(closes, fund["market_cap_cr"], fund["debt_to_equity"], cfg)
            res.update(symbol=sym, price=round(closes[-1], 2), price_src=psrc)
            rows.append(res)
        except Exception as e:  # one bad name shouldn't kill the scan
            rows.append({"symbol": sym, "error": repr(e)})
    return rows


def format_table(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    bad = [r for r in rows if "error" in r]
    # Most oversold first: deepest below the 200-DMA, then lowest RSI.
    ok.sort(key=lambda r: (r["pct_from_dma"], r["rsi"]))

    head = f"{'SYM':<11}{'PRICE':>10}{'RSI':>7}{'vs200DMA':>10}{'MCAP_CR':>12}{'D/E':>7}  SIGNAL"
    lines = [head, "-" * len(head)]
    for r in ok:
        de = "-" if r["debt_to_equity"] is None else f"{r['debt_to_equity']:.2f}"
        mc = "-" if r["market_cap_cr"] is None else f"{r['market_cap_cr']:,.0f}"
        flag = "*** BUY" if r["signal"] else ""
        lines.append(
            f"{r['symbol']:<11}{r['price']:>10,.2f}{r['rsi']:>7.1f}"
            f"{r['pct_from_dma']*100:>9.1f}%{mc:>12}{de:>7}  {flag}"
        )
    for r in bad:
        lines.append(f"{r['symbol']:<11} ERROR {r['error']}")
    hits = sum(1 for r in ok if r["signal"])
    lines.append("-" * len(head))
    lines.append(f"{len(ok)} scanned, {len(bad)} failed, {hits} candidate(s).")
    return "\n".join(lines)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Free-data mean-reversion scanner (NSE).")
    p.add_argument("--rsi-max", type=float, default=35.0, help="oversold RSI ceiling")
    p.add_argument("--below-dma", type=float, default=0.20,
                   help="min fractional distance below the 200-DMA (0.20 = 20%%)")
    p.add_argument("--min-mcap", type=float, default=20_000.0, help="min market cap (cr)")
    p.add_argument("--max-de", type=float, default=0.50, help="max debt/equity")
    p.add_argument("--include-financials", action="store_true",
                   help="include banks/NBFCs/insurers (D/E gate is meaningless for them)")
    p.add_argument("--limit", type=int, default=None, help="cap number of symbols (debug)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    symbols = select_universe(load_symbols(), include_financials=args.include_financials)
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Scanning {len(symbols)} names | RSI<{args.rsi_max:g} | "
          f">{args.below_dma*100:g}% below 200-DMA | mcap>{args.min_mcap:,.0f}cr | "
          f"D/E<{args.max_de:g}\n")
    print(format_table(scan(symbols, build_cfg(args))))


if __name__ == "__main__":
    main()

"""Print today's institutional 'smart money' buys from NSE bulk/block deals.

    python -m scanner.scan_deals                 # >= 1 cr notable buys
    python -m scanner.scan_deals --min-cr 5      # only >= 5 cr

Names where multiple institutions bought the same session rank highest.
"""
from __future__ import annotations

import argparse

from scanner.deals import fetch_deals, aggregate_by_symbol, classify_client


def format_table(ranked: list[dict]) -> str:
    if not ranked:
        return "No notable institutional buys today at this threshold."
    head = f"{'SYMBOL':<14}{'#INST':>6}{'BUY_VALUE_CR':>14}  CATEGORIES / BUYERS"
    lines = [head, "-" * len(head)]
    for r in ranked:
        cats = ",".join(sorted(r["categories"]))
        buyers = "; ".join(sorted(set(r["buyers"])))[:70]
        lines.append(
            f"{r['symbol']:<14}{r['n_buyers']:>6}{r['total_value']/1e7:>14,.2f}  "
            f"[{cats}] {buyers}"
        )
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="NSE bulk/block smart-money buys.")
    p.add_argument("--min-cr", type=float, default=1.0,
                   help="minimum deal value in crore to count (default 1)")
    args = p.parse_args(argv)
    value_min = args.min_cr * 1e7

    deals = fetch_deals()
    n_buy = sum(1 for d in deals if d["side"] == "BUY")
    ranked = aggregate_by_symbol(deals, value_min=value_min)

    print(f"Pulled {len(deals)} deals ({n_buy} buys). "
          f"Notable institutional buys >= {args.min_cr:g} cr:\n")
    print(format_table(ranked))


if __name__ == "__main__":
    main()

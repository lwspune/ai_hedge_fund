"""Unified signal runner.

    python -m scanner.run --list          # all signals + verdicts
    python -m scanner.run buyback_arb     # run one signal (shows its verdict first)

The verdict banner prints before every scan so a falsified signal is never read
as if it carried edge.
"""
from __future__ import annotations

import argparse

from scanner.catalog import SIGNALS, get_signal, list_signals

_BADGE = {"edge": "[EDGE]", "conditional": "[CONDITIONAL EDGE]",
          "thin": "[THIN]", "null": "[NO EDGE]"}


def list_table() -> str:
    head = f"{'SIGNAL':<20}{'TYPE':<12}{'VERDICT':<14}{'ROLE':<12}SUMMARY"
    lines = [head, "-" * 100]
    order = {"primary": 0, "watch": 1, "lens": 2, "documented": 3}
    for m in sorted(list_signals(), key=lambda m: order.get(m.role, 9)):
        lines.append(f"{m.name:<20}{m.type:<12}{m.verdict:<14}{m.role:<12}{m.summary[:46]}")
    return "\n".join(lines)


def banner(name: str) -> str:
    m = get_signal(name).meta
    bar = "=" * 72
    return (f"{bar}\n{_BADGE.get(m.verdict, '')} {m.name}  ({m.type}, role={m.role})\n"
            f"{m.summary}\n{bar}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Run a validated market-intel signal.")
    p.add_argument("signal", nargs="?", help="signal name (omit with --list)")
    p.add_argument("--list", action="store_true", help="list all signals + verdicts")
    args = p.parse_args(argv)

    if args.list or not args.signal:
        print(list_table())
        return
    if args.signal not in SIGNALS:
        print(f"Unknown signal '{args.signal}'. Use --list to see options.")
        return
    print(banner(args.signal))
    print(get_signal(args.signal).run())


if __name__ == "__main__":
    main()

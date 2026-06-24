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


def _save_buyback(rows) -> None:
    from scanner import db
    meta = get_signal("buyback_arb").meta
    cands = [{"symbol": r["symbol"], "score": r["est_return"],
              "payload": {"premium": r["premium"], "entitlement_small": r["entitlement_small"],
                          "buyback_price": r["buyback_price"], "cur_price": r["cur_price"],
                          "record_date": db._iso(r["record_date"]),
                          "close_date": db._iso(r["close_date"])}}
             for r in rows]
    try:
        db.upsert_buybacks(rows)
        rid = db.log_scan(meta.name, meta.verdict, cands)
        print(f"\n[saved] run #{rid} | {len(rows)} buybacks upserted, {len(cands)} candidates")
    except Exception as e:
        print(f"\n[save skipped] {e}")


def _save_run(meta) -> None:
    from scanner import db
    try:
        rid = db.log_scan(meta.name, meta.verdict, [])
        print(f"\n[saved] run #{rid} (metadata only)")
    except Exception as e:
        print(f"\n[save skipped] {e}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Run a validated market-intel signal.")
    p.add_argument("signal", nargs="?", help="signal name (omit with --list)")
    p.add_argument("--list", action="store_true", help="list all signals + verdicts")
    p.add_argument("--save", action="store_true", help="persist the run to Supabase (needs .env)")
    args = p.parse_args(argv)

    if args.list or not args.signal:
        print(list_table())
        return
    if args.signal not in SIGNALS:
        print(f"Unknown signal '{args.signal}'. Use --list to see options.")
        return
    print(banner(args.signal))

    if args.signal == "buyback_arb":
        from scanner.buyback import scan_current_buybacks, format_buyback_table
        rows = scan_current_buybacks()
        print(format_buyback_table(rows))
        if args.save:
            _save_buyback(rows)
    else:
        print(get_signal(args.signal).run())
        if args.save:
            _save_run(get_signal(args.signal).meta)


if __name__ == "__main__":
    main()

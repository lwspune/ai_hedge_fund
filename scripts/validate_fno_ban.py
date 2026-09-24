"""Validate candidate signal #6: F&O ban reversal.

Episodes: consecutive trading days a stock is on NSE's F&O ban list (corporate_events,
source nse_fo, 2020->). E = first ban day, X = first trading day after the ban lifts.
Pre-ban move = abnormal return T-6 -> T-1 before E (vs NIFTY 500).

Measured (fixed in advance): each window's abnormal return SIGNED against the pre-ban move
(positive = the move reversed) — entry E-1->E+2, during E-1->last ban day, exit X-1->X+5,
post X->X+10. CONTROL: the same windows on the same stocks at dates 60 trading days away
(>= 20 trading days from any ban), signed against their own prior 5-day move — short-term
reversal is a generic effect, so the ban must beat this, not zero.
Segments: pre-move direction, episode length (1-2 vs 3+ days), era (2020-21 / 2022-23 / 2024-26).
Prices: yfinance (adjusted; liquid F&O names); split/bonus/rights near an episode -> dropped.

    python scripts/validate_fno_ban.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, parse_args  # noqa: E402
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize, window_return  # noqa: E402
from scanner.fnoban import PLACEBO_GAP, PRE_DAYS, WINDOWS, ban_episodes, far_from_bans, reversal  # noqa: E402
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402

BENCH = "^CRSLDX"            # NIFTY 500
COST = 0.003                 # ~30 bps round trip
CONTROL_SHIFT = 60           # trading days from the episode to its control date
OUT = Path(__file__).resolve().parent.parent / "cache" / "fnoban_results.csv"


def fmt(label: str, xs) -> str:
    s = summarize(list(xs))
    if not s["n"]:
        return f"  {label:<40} n=  0"
    t = f"{s['t_stat']:+5.1f}" if s["t_stat"] is not None else "  n/a"
    return (f"  {label:<40} n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  pos={s['pct_positive']*100:4.0f}%  t={t}")


def windows_at(s, bench, first, last_off, exit_):
    """Abnormal returns for each pre-specified window (None where data is missing)."""
    out = {}
    for w, (anchor, a, b) in WINDOWS.items():
        d = first if anchor == "first" else exit_
        if d is None:
            out[w] = None
            continue
        out[w] = window_return(s, bench, d, a, last_off if b is None else b)
    return out


def build() -> pd.DataFrame:
    bans = db.select_all("corporate_events", {"select": "symbol,event_date",
                                              "event_type": "eq.fo_ban", "order": "event_date"})
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2019-06-01"})
    bench = get_closes(BENCH, "2019-01-01")
    cal = bench.index
    eps = [e for e in ban_episodes([(b["symbol"], b["event_date"]) for b in bans], cal) if e["exit"]]
    ban_days = {}
    for b in bans:
        ban_days.setdefault(b["symbol"], []).append(b["event_date"])
    print(f"{len(bans)} ban-days -> {len(eps)} closed episodes across "
          f"{len({e['symbol'] for e in eps})} stocks", flush=True)

    prices, rows = {}, []
    for e in eps:
        sym = e["symbol"]
        if sym not in prices:
            prices[sym] = get_closes(sym, "2019-01-01")
        s = prices[sym]
        first, exit_ = pd.Timestamp(e["first"]), pd.Timestamp(e["exit"])
        blocked = blocking_action(acts, sym, first - pd.Timedelta(days=15), exit_ + pd.Timedelta(days=25))
        row = {**e, "priced": s is not None, "blocked": blocked}
        if s is not None and not blocked:
            row["pre"] = window_return(s, bench, first, -PRE_DAYS - 1, -1)
            for w, r in windows_at(s, bench, first, e["days"] - 1, exit_).items():
                row[w] = r
                row[f"rev_{w}"] = reversal(row["pre"], r)
            # control: same stock, same windows, CONTROL_SHIFT trading days away, far from bans
            p = cal.searchsorted(first)
            for tag, shift in (("ctl_after", CONTROL_SHIFT), ("ctl_before", -CONTROL_SHIFT)):
                q = p + shift
                if not 0 <= q < len(cal) - 20:
                    continue
                cd = cal[q]
                if not far_from_bans(sym, cd, ban_days, cal, PLACEBO_GAP) or \
                        blocking_action(acts, sym, cd - pd.Timedelta(days=15), cd + pd.Timedelta(days=40)):
                    continue
                c_pre = window_return(s, bench, cd, -PRE_DAYS - 1, -1)
                c_exit = cal[min(q + e["days"], len(cal) - 1)]
                for w, r in windows_at(s, bench, cd, e["days"] - 1, c_exit).items():
                    row[f"{tag}_{w}"] = reversal(c_pre, r)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    ok = df[df["priced"] & ~df["blocked"] & df["pre"].notna()]
    print(f"\nepisodes: {len(df)} | unpriced {int((~df['priced']).sum())} | "
          f"dropped for corporate actions {int((df['priced'] & df['blocked']).sum())} | usable {len(ok)}")
    print("\n=== REVERSAL of the pre-ban move (positive = reversed) vs same-stock CONTROL ===")
    for w in WINDOWS:
        ctl = pd.concat([ok.get(f"ctl_after_{w}", pd.Series(dtype=float)),
                         ok.get(f"ctl_before_{w}", pd.Series(dtype=float))]).dropna()
        print(fmt(f"{w:<7} ban", ok[f"rev_{w}"].dropna()))
        print(fmt(f"{w:<7} control", ctl))

    print("\n=== SEGMENTS (pre-specified) — exit X-1->X+5 | post X->X+10 ===")
    yr = pd.to_datetime(ok["first"]).dt.year
    cuts = {
        "pre-move UP (ran into ban)": ok["pre"] > 0,
        "pre-move DOWN (sold into ban)": ok["pre"] < 0,
        "episode 1-2 days": ok["days"] <= 2,
        "episode 3+ days": ok["days"] >= 3,
        "era 2020-21": yr.between(2020, 2021),
        "era 2022-23": yr.between(2022, 2023),
        "era 2024-26": yr.between(2024, 2026),
    }
    for label, m in cuts.items():
        for w in ("entry", "exit", "post"):
            print(fmt(f"{label} [{w}]", ok.loc[m, f"rev_{w}"].dropna()))

    print("\n=== RAW abnormal return by pre-move direction (tradability: long = cash, "
          "short = futures only after exit) ===")
    for label, m in (("pre UP", ok["pre"] > 0), ("pre DOWN", ok["pre"] < 0)):
        for w in WINDOWS:
            print(fmt(f"{label} raw {w}", ok.loc[m, w].dropna()))
    print(f"\nNet of costs: subtract ~{COST*100:.1f}% per round trip from any tradable window.")


if __name__ == "__main__":
    args = parse_args()
    report(exclude_results(build(), "first", args.exclude_results_window))

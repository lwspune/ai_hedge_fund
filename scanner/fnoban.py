"""F&O ban reversal study (candidate signal #6): when a stock's open interest crosses 95% of
its market-wide position limit it enters the F&O ban (no fresh derivative positions). Does the
forced unwind overshoot, so the pre-ban move reverses — during the ban or once it lifts?

Pure event logic (tested); the runner is scripts/validate_fno_ban.py. Everything below was
fixed BEFORE looking at results.
"""
from __future__ import annotations

import pandas as pd

# Windows: (anchor, from, to) in trading days. anchor "first" = first ban day E, "exit" = first
# trading day after the ban lifts X. to=None on "during" means the last ban day (X-1).
WINDOWS = {"entry": ("first", -1, 2), "during": ("first", -1, None),
           "exit": ("exit", -1, 5), "post": ("exit", 0, 10)}
PRE_DAYS = 5          # the pre-ban move that should reverse: return T-6 -> T-1 vs benchmark
PLACEBO_GAP = 20      # control dates must be >= 20 trading days from any ban of that stock


def ban_episodes(rows, calendar: pd.DatetimeIndex) -> list[dict]:
    """(symbol, date) ban-list rows -> episodes of consecutive trading days in ban.
    `exit` = first trading day after the last ban day (None if still banned at data end)."""
    cal = pd.DatetimeIndex(calendar).sort_values()
    by_sym: dict[str, set[int]] = {}
    for sym, d in rows:
        p = int(cal.searchsorted(pd.Timestamp(d)))
        if p < len(cal):  # dates after the calendar's end (e.g. today's list) can't be measured
            by_sym.setdefault(sym, set()).add(p)
    out = []
    for sym in sorted(by_sym):
        pos = sorted(by_sym[sym])
        start = prev = pos[0]
        for p in pos[1:] + [None]:
            if p is not None and p == prev + 1:
                prev = p
                continue
            nxt = prev + 1
            out.append({"symbol": sym, "first": cal[start].date().isoformat(),
                        "last": cal[prev].date().isoformat(), "days": prev - start + 1,
                        "exit": cal[nxt].date().isoformat() if nxt < len(cal) else None})
            if p is not None:
                start = prev = p
    return out


def reversal(pre_move, window_ret):
    """Window return signed against the pre-ban move: positive = the move reversed."""
    if pre_move is None or window_ret is None or pre_move == 0:
        return None
    return -window_ret if pre_move > 0 else window_ret


def far_from_bans(symbol: str, date, bans: dict[str, list], calendar: pd.DatetimeIndex,
                  gap: int = PLACEBO_GAP) -> bool:
    """True if `date` is at least `gap` trading days from every ban day of `symbol`."""
    cal = pd.DatetimeIndex(calendar)
    p = cal.searchsorted(pd.Timestamp(date))
    return all(abs(cal.searchsorted(pd.Timestamp(b)) - p) >= gap for b in bans.get(symbol, []))

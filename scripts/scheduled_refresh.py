"""Scheduled infra refresh — run by GitHub Actions (.github/workflows/refresh-*.yml).

    python scripts/scheduled_refresh.py daily    # weekdays 20:30 IST: events, deals refill, buybacks
    python scripts/scheduled_refresh.py weekly   # Sunday: company master + fundamentals

Runs each step as a subprocess so one failure doesn't stop the rest, streams output to the
console (the Actions log; add --log to also append to logs/refresh-<mode>-<date>.log) and exits
non-zero if any step failed — which makes GitHub email the repo owner.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEALS_LOOKBACK_DAYS = 10  # re-pull recent deals every day: heals paused/missed edge-fn runs


def steps(mode: str, today: date) -> list[list[str]]:
    if mode == "daily":
        return [["refresh_events.py", "actions"], ["refresh_events.py", "fo-ban"],
                ["refresh_events.py", "ipos"],
                ["refill_deals.py", "--from", (today - timedelta(days=DEALS_LOOKBACK_DAYS)).isoformat()],
                ["-m", "scanner.run", "buyback_arb", "--save"]]
    if mode == "weekly":  # fundamentals rows carry `history`, so no separate rebuild step
        return [["refresh_companies.py"], ["refresh_fundamentals.py"]]
    raise ValueError(f"unknown mode {mode!r}")


def command(step: list[str]) -> list[str]:
    """A step is a script under scripts/ or, when it starts with -m, a module."""
    if step[0] == "-m":
        return [sys.executable, "-u", *step]
    return [sys.executable, "-u", str(ROOT / "scripts" / step[0]), *step[1:]]


def main():
    args = sys.argv[1:]
    mode = next((a for a in args if not a.startswith("--")), "")
    plan = steps(mode, date.today())
    log = None
    if "--log" in args:
        (ROOT / "logs").mkdir(exist_ok=True)
        log = open(ROOT / "logs" / f"refresh-{mode}-{date.today().isoformat()}.log", "a", encoding="utf-8")
    failed = []
    for step in plan:
        header = f"\n=== {datetime.now():%H:%M:%S} {' '.join(step)}"
        print(header, flush=True)
        proc = subprocess.run(command(step), cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        print(proc.stdout, end="", flush=True)
        print(f"=== exit {proc.returncode}", flush=True)
        if log:
            log.write(f"{header}\n{proc.stdout}=== exit {proc.returncode}\n")
        if proc.returncode != 0:
            failed.append(" ".join(step))
    if log:
        log.close()
    if failed:
        print(f"\nFAILED steps: {failed}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

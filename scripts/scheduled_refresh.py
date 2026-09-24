"""Scheduled infra refresh — run by Windows Task Scheduler (see scripts/register_schedule.ps1).

    python scripts/scheduled_refresh.py daily    # weekdays ~20:30 IST: events + deals refill
    python scripts/scheduled_refresh.py weekly   # Sunday: company master + fundamentals

Runs each step as a subprocess so one failure doesn't stop the rest; logs to
logs/refresh-<mode>-<date>.log and exits non-zero if any step failed. These need the
residential IP (nselib, screener), which is why they run here and not in pg_cron.
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
                ["refill_deals.py", "--from", (today - timedelta(days=DEALS_LOOKBACK_DAYS)).isoformat()]]
    if mode == "weekly":
        return [["refresh_companies.py"], ["refresh_fundamentals.py"],
                ["rebuild_snapshot_history.py"]]
    raise ValueError(f"unknown mode {mode!r}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    plan = steps(mode, date.today())
    (ROOT / "logs").mkdir(exist_ok=True)
    log = ROOT / "logs" / f"refresh-{mode}-{date.today().isoformat()}.log"
    failed = 0
    with open(log, "a", encoding="utf-8") as fh:
        for step in plan:
            fh.write(f"\n=== {datetime.now():%H:%M:%S} {' '.join(step)}\n")
            fh.flush()
            rc = subprocess.run([sys.executable, "-u", str(ROOT / "scripts" / step[0]), *step[1:]],
                                cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT).returncode
            fh.write(f"=== exit {rc}\n")
            failed += rc != 0
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

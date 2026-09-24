"""Validation evidence in the cloud (DATA_INFRA_SPEC WP7).

Every CONCLUSIONS.md verdict rests on a result set. Sources drift (the 2026 chittorgarh format
change proved it), so a re-run may not reproduce a number — the artefacts behind it must be
stored, not left in a laptop's gitignored cache/. Each published run writes

    evidence/<signal>/<YYYY-MM-DDTHHMMSSZ>/{results.csv, report.txt, summary.json, meta.json}

to the private `evidence` bucket and one queryable `validation_runs` row (git SHA, script, args,
summary). The dashboard Signals view shows the latest path per signal.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime, timezone

BUCKET = "evidence"
REPORT_TAIL = 40      # last lines of the printed report kept in the index row


def evidence_paths(signal: str, stamp: str) -> dict:
    """stamp: the run's UTC time 'YYYY-MM-DDTHHMMSSZ' (unique per run, so a same-day rerun never
    overwrites evidence an earlier validation_runs row points at); the 2026-09-24 laptop
    baseline uses the bare date."""
    d = f"{signal}/{stamp}"
    return {"dir": d, **{k: f"{d}/{f}" for k, f in (("results", "results.csv"), ("report", "report.txt"),
                                                     ("summary", "summary.json"), ("meta", "meta.json"))}}


def meta(signal: str, script: str, args: dict, counts: dict, git_sha: str | None, run_at: str) -> dict:
    return {"signal": signal, "script": script, "args": args, "row_counts": counts,
            "git_sha": git_sha, "run_at": run_at}


def frame_summary(df) -> dict:
    """n rows + count/mean/median of every numeric (non-bool) column."""
    import pandas as pd
    cols = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s) or not pd.api.types.is_numeric_dtype(s):
            continue
        x = s.dropna()
        cols[c] = {"count": int(len(x)), "mean": None if x.empty else round(float(x.mean()), 6),
                   "median": None if x.empty else round(float(x.median()), 6)}
    return {"n": int(len(df)), "columns": cols}


def git_sha() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _put(path: str, data: bytes, ctype: str) -> None:
    from scanner import db
    db.storage_put(BUCKET, path, data, ctype)


def _index(row: dict) -> None:
    from scanner import db
    db.insert("validation_runs", row, return_rows=False)


def publish(signal: str, script: str, args: dict, frames: dict, report_text: str,
            run_date: date | None = None, git_sha: str | None = None) -> str:
    """Upload one run's artefacts + index row; returns the evidence directory path.
    frames: {name: DataFrame} — "results" becomes results.csv, others <name>.csv."""
    now = datetime.now(timezone.utc)
    run_at = now.isoformat()
    p = evidence_paths(signal, run_date.isoformat() if run_date else now.strftime("%Y-%m-%dT%H%M%SZ"))
    counts = {k: int(len(v)) for k, v in frames.items()}
    for name, df in frames.items():
        path = p["results"] if name == "results" else f"{p['dir']}/{name}.csv"
        _put(path, df.to_csv(index=False).encode("utf-8"), "text/csv")
    _put(p["report"], report_text.encode("utf-8"), "text/plain")
    summary = {**{k: frame_summary(v) for k, v in frames.items()},
               "report_tail": report_text.rstrip("\n").splitlines()[-REPORT_TAIL:]}
    _put(p["summary"], json.dumps(summary, indent=1, default=str).encode("utf-8"), "application/json")
    m = meta(signal, script, args, counts, git_sha, run_at)
    _put(p["meta"], json.dumps(m, indent=1, default=str).encode("utf-8"), "application/json")
    _index({"signal_name": signal, "run_at": run_at, "git_sha": git_sha, "script": script,
            "params": args, "summary": summary, "evidence_path": p["dir"]})
    return p["dir"]

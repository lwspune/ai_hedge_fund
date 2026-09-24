"""Validation evidence in the cloud (DATA_INFRA_SPEC WP7): pure path/meta/summary builders and
the validation runner's publish plumbing (network stubbed)."""
from datetime import date

import pandas as pd

from scanner import evidence
from scanner.evidence import evidence_paths, frame_summary, meta


def test_evidence_paths():
    p = evidence_paths("rights_re", "2026-09-24")
    assert p == {"dir": "rights_re/2026-09-24", "results": "rights_re/2026-09-24/results.csv",
                 "report": "rights_re/2026-09-24/report.txt", "summary": "rights_re/2026-09-24/summary.json",
                 "meta": "rights_re/2026-09-24/meta.json"}


def test_meta_records_provenance():
    m = meta("fno_ban", "scripts/validate_fno_ban.py", {"exclude_results_window": 2}, {"results": 920},
             git_sha="abc1234def", run_at="2026-09-24T10:00:00+00:00")
    assert m == {"signal": "fno_ban", "script": "scripts/validate_fno_ban.py",
                 "args": {"exclude_results_window": 2}, "row_counts": {"results": 920},
                 "git_sha": "abc1234def", "run_at": "2026-09-24T10:00:00+00:00"}


def test_frame_summary_numeric_columns_only():
    df = pd.DataFrame({"symbol": ["A", "B", "C"], "gap": [0.01, 0.03, None], "priced": [True, True, False]})
    s = frame_summary(df)
    assert s["n"] == 3
    assert s["columns"]["gap"] == {"count": 2, "mean": 0.02, "median": 0.02}
    assert "symbol" not in s["columns"] and "priced" not in s["columns"]


def test_publish_writes_bucket_files_and_index_row(monkeypatch):
    puts, inserts = [], []
    monkeypatch.setattr(evidence, "_put", lambda path, data, ctype: puts.append((path, ctype, len(data))))
    monkeypatch.setattr(evidence, "_index", lambda row: inserts.append(row))
    df = pd.DataFrame({"symbol": ["A"], "x": [1.0]})
    path = evidence.publish("rights_re", "scripts/validate_rights_re.py", {"publish": True},
                            {"results": df}, "REPORT TEXT", run_date=date(2026, 9, 24), git_sha="abc")
    assert path == "rights_re/2026-09-24"
    assert [p for p, _, _ in puts] == ["rights_re/2026-09-24/results.csv", "rights_re/2026-09-24/report.txt",
                                       "rights_re/2026-09-24/summary.json", "rights_re/2026-09-24/meta.json"]
    row = inserts[0]
    assert row["signal_name"] == "rights_re" and row["evidence_path"] == "rights_re/2026-09-24"
    assert row["git_sha"] == "abc" and row["summary"]["results"]["n"] == 1
    assert row["summary"]["report_tail"][-1] == "REPORT TEXT"


def test_validation_run_tees_report_and_publishes_only_when_asked(monkeypatch, capsys):
    from scanner import validation
    calls = []
    monkeypatch.setattr(evidence, "publish", lambda *a, **k: calls.append((a, k)) or "sig/2026-09-24")

    def body(args):
        print("hello report")
        return {"results": pd.DataFrame({"x": [1]})}

    validation.run("sig", body, argv=[])
    assert calls == [] and "hello report" in capsys.readouterr().out
    validation.run("sig", body, argv=["--publish", "--exclude-results-window", "2"])
    (signal, script, args, frames, text), _ = calls[0]
    assert signal == "sig" and args["exclude_results_window"] == 2 and "hello report" in text


def test_publish_default_path_is_unique_per_run(monkeypatch):
    """Same-day reruns must not overwrite earlier evidence (a validation_runs row points at it)."""
    import re
    monkeypatch.setattr(evidence, "_put", lambda *a: None)
    monkeypatch.setattr(evidence, "_index", lambda row: None)
    path = evidence.publish("fno_ban", "s.py", {}, {"results": pd.DataFrame({"x": [1]})}, "r")
    assert re.fullmatch(r"fno_ban/\d{4}-\d{2}-\d{2}T\d{6}Z", path)

"""Filings retention (DATA_INFRA_SPEC WP8): months older than 24 go to the bucket in full,
then their `subject` is nulled in the table — idempotently and never losing a subject."""
from datetime import date

import pandas as pd

from scripts.archive_filings import archive_months, merge_archive


def test_archive_months_are_whole_months_older_than_cutoff():
    got = archive_months(oldest=date(2024, 7, 15), today=date(2026, 9, 24), keep_months=24)
    assert got == [(date(2024, 7, 1), date(2024, 8, 1)), (date(2024, 8, 1), date(2024, 9, 1))]
    assert archive_months(date(2025, 1, 1), date(2026, 9, 24), 24) == []


def test_merge_archive_never_replaces_a_stored_subject_with_null():
    stored = pd.DataFrame({"seq_id": [1, 2], "subject": ["first text", "second text"], "category": ["a", "b"]})
    fresh = pd.DataFrame({"seq_id": [1, 2, 3], "subject": [None, "second text", "third"], "category": ["a", "b", "c"]})
    out = merge_archive(stored, fresh)
    assert list(out["seq_id"]) == [1, 2, 3]
    assert list(out["subject"]) == ["first text", "second text", "third"]


def test_merge_archive_without_existing_file():
    fresh = pd.DataFrame({"seq_id": [5], "subject": ["x"]})
    assert merge_archive(None, fresh).equals(fresh)

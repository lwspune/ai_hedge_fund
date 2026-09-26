"""The rating extractor's work list must page past PostgREST's 1000-row cap: the first
backfill asked for 15000 and silently got 1000."""
from scanner import db
from scripts import extract_ratings


def test_pending_pages_past_the_row_cap(monkeypatch):
    rows = [{"seq_id": i} for i in range(2500)]

    def fake_select(table, params=None):
        assert table == "filings" and params["category"] == "like.Credit Rating*"
        off = int(params.get("offset", 0))
        return rows[off:off + min(int(params["limit"]), 1000)]   # the server's cap

    monkeypatch.setattr(db, "select", fake_select)
    assert len(extract_ratings.pending(2200, "2020-01-01")) == 2200
    assert len(extract_ratings.pending(500, "2020-01-01")) == 500

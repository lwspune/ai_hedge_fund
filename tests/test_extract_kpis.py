"""The KPI extractor's work list must page past PostgREST's 1000-row cap: the daily
`--limit 1500` step silently read 1000."""
from scanner import db
from scripts import extract_kpis


def _fake(rows, seen):
    def fake_select(table, params=None):
        assert table == "filings"
        seen.append(params["or"])
        off = int(params.get("offset", 0))
        return rows[off:off + min(int(params["limit"]), 1000)]   # the server's cap
    return fake_select


def test_pending_pages_past_the_row_cap(monkeypatch):
    rows, seen = [{"seq_id": i} for i in range(2500)], []
    monkeypatch.setattr(db, "select", _fake(rows, seen))
    assert len(extract_kpis.pending(1500, "2024-01-01")) == 1500
    assert len(extract_kpis.pending(300, "2024-01-01")) == 300
    assert set(seen) == {extract_kpis.KPI_FILTER}


def test_orders_only_keeps_its_filter(monkeypatch):
    rows, seen = [{"seq_id": i} for i in range(1200)], []
    monkeypatch.setattr(db, "select", _fake(rows, seen))
    assert len(extract_kpis.pending(1100, "2024-01-01", orders_only=True)) == 1100
    assert set(seen) == {extract_kpis.ORDERS_FILTER}

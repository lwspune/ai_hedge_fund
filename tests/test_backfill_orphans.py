"""Orphan symbols (seen in filings/deals/events, absent from companies) -> delisted master rows (WP4)."""
from datetime import date

from scripts.backfill_orphans import orphan_rows


def test_orphan_rows_prefer_last_trade_date_then_last_seen():
    orphans = [{"symbol": "RELCAPITAL", "company": "Reliance Capital Limited", "last_seen": "2025-02-10"},
               {"symbol": "ODDONE", "company": None, "last_seen": "2021-03-01"}]
    rows = orphan_rows(orphans, {"RELCAPITAL": date(2024, 11, 29)})
    assert rows[0] == {"symbol": "RELCAPITAL", "name": "Reliance Capital Limited", "series": None,
                       "listing_date": None, "face_value": None, "isin": None, "industry": None,
                       "industry_source": None, "indices": [], "is_financial": None,
                       "status": "delisted", "delisted_on": "2024-11-29", "delist_source": "manual",
                       "last_seen_listed": None}
    assert rows[1]["delisted_on"] == "2021-03-01" and rows[1]["name"] is None

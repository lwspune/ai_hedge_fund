"""Test-first spec for the order-win event study (candidate signal #9)."""
from scanner.orderwins import cluster_orders, revenue_before, size_bucket


def _o(sym, ts, v):
    return {"symbol": sym, "disclosed_at": ts, "value_cr": v}


def test_cluster_orders_merges_within_gap_and_sums_known_values():
    rows = [_o("ABC", "2025-03-03T10:00:00+05:30", 100.0),
            _o("ABC", "2025-03-06T18:30:00+05:30", None),     # value undisclosed (band)
            _o("ABC", "2025-03-07T09:00:00+05:30", 50.0),
            _o("ABC", "2025-04-01T09:00:00+05:30", 20.0),     # > 5 days later: new event
            _o("XYZ", "2025-03-04T09:00:00+05:30", None)]
    ev = cluster_orders(rows, gap_days=5)
    assert [(e["symbol"], e["date"], e["n"], e["value_cr"]) for e in ev] == [
        ("ABC", "2025-03-03", 3, 150.0), ("XYZ", "2025-03-04", 1, None), ("ABC", "2025-04-01", 1, 20.0)]


def test_revenue_before_uses_last_full_fiscal_year_before_the_event():
    annual = [{"period": "Mar 2023", "revenue": 800.0}, {"period": "Mar 2024", "revenue": 1000.0},
              {"period": "Mar 2025", "revenue": 1200.0}, {"period": "TTM", "revenue": 1300.0}]
    assert revenue_before(annual, "2025-03-03") == 1000.0     # FY25 not yet reported: no look-ahead
    assert revenue_before(annual, "2025-06-10") == 1200.0
    assert revenue_before(annual, "2022-01-01") is None
    assert revenue_before([], "2025-01-01") is None
    assert revenue_before([{"period": "Mar 2024", "revenue": 0}], "2025-01-01") is None


def test_size_bucket():
    assert size_bucket(None) == "unknown"
    assert size_bucket(0.02) == "<5%"
    assert size_bucket(0.10) == "5-25%"
    assert size_bucket(0.25) == ">=25%"

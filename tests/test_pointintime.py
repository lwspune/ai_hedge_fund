"""Point-in-time data (DATA_INFRA_SPEC WP5): historical market cap, index-membership intervals,
as-of market-cap lookup. No lookahead: every value at date D uses only what was known by D."""
from datetime import date

import pandas as pd
import pytest

from scanner.fundamentals import historical_market_cap
from scanner.master import curated_intervals, membership_diff
from scanner.pointintime import mcap_at


def _statements():
    # Equity Capital (Rs cr) per annual balance sheet: a 1:1 bonus in Sep 2020 doubles it at Mar 2021
    return pd.DataFrame([
        {"section": "balance-sheet", "line_item": "Equity Capital", "period": "Mar 2020",
         "period_end": "2020-03-31", "value": 100.0},
        {"section": "balance-sheet", "line_item": "Equity Capital", "period": "Mar 2021",
         "period_end": "2021-03-31", "value": 200.0},
        {"section": "profit-loss", "line_item": "Sales", "period": "Mar 2021",
         "period_end": "2021-03-31", "value": 999.0},
    ])


ACTIONS = [
    {"event_type": "bonus", "event_date": "2020-09-01", "details": {"ratio": "1:1"}},
    {"event_type": "split", "event_date": "2021-06-01", "details": {"from_fv": 10.0, "to_fv": 5.0}},
]


def test_historical_market_cap_is_continuous_across_bonus_and_split():
    closes = pd.Series([1000.0, 1000.0, 500.0, 500.0, 500.0, 250.0],
                       index=pd.to_datetime(["2020-05-01", "2020-08-31", "2020-09-01",
                                             "2021-03-31", "2021-05-31", "2021-06-01"]))
    m = historical_market_cap(_statements(), closes, face_value_now=5.0, actions=ACTIONS)
    assert list(m.round(6)) == [10000.0] * 6    # Rs cr: no jump at the bonus, BS update or split


def test_historical_market_cap_nan_before_first_balance_sheet():
    closes = pd.Series([1000.0], index=pd.to_datetime(["2019-12-31"]))
    m = historical_market_cap(_statements(), closes, face_value_now=5.0, actions=ACTIONS)
    assert m.isna().all()


def test_membership_diff_opens_and_closes_intervals():
    current = [{"symbol": "A", "index_key": "nifty50", "from_date": "2026-01-01"},
               {"symbol": "B", "index_key": "nifty50", "from_date": "2026-01-01"}]
    close, open_ = membership_diff(current, {"nifty50": {"A", "C"}, "midcap150": {"B"}}, date(2026, 9, 27))
    assert close == [{"symbol": "B", "index_key": "nifty50", "from_date": "2026-01-01", "to_date": "2026-09-27"}]
    assert sorted((r["symbol"], r["index_key"]) for r in open_) == [("B", "midcap150"), ("C", "nifty50")]
    assert all(r["from_date"] == "2026-09-27" and r["to_date"] is None
               and r["source"] == "niftyindices_list" for r in open_)


def test_membership_diff_ignores_indices_missing_today():
    """A failed download of one index file must not close every membership in it."""
    current = [{"symbol": "A", "index_key": "smallcap250", "from_date": "2026-01-01"}]
    close, open_ = membership_diff(current, {"nifty50": {"X"}}, date(2026, 9, 27))
    assert close == [] and [r["symbol"] for r in open_] == ["X"]


def test_curated_intervals_pair_adds_and_drops():
    rows = [
        {"symbol": "AAA", "leg": "add", "effective": "2019-03-29"},
        {"symbol": "AAA", "leg": "drop", "effective": "2021-09-30"},
        {"symbol": "AAA", "leg": "add", "effective": "2023-03-31"},
        {"symbol": "OLD", "leg": "drop", "effective": "2019-09-27"},   # member before the record starts
    ]
    got = curated_intervals(rows, index_key="niftynext50", record_start="2018-02-21")
    assert got == [
        {"symbol": "AAA", "index_key": "niftynext50", "from_date": "2019-03-29", "to_date": "2021-09-30", "source": "curated"},
        {"symbol": "AAA", "index_key": "niftynext50", "from_date": "2023-03-31", "to_date": None, "source": "curated"},
        {"symbol": "OLD", "index_key": "niftynext50", "from_date": "2018-02-21", "to_date": "2019-09-27", "source": "curated"},
    ]


def test_mcap_at_prefers_snapshot_history_then_statements():
    hist = [{"as_of": "2026-09-20", "market_cap_cr": 500.0}, {"as_of": "2026-09-27", "market_cap_cr": 520.0}]
    assert mcap_at(date(2026, 9, 25), hist, lambda d: pytest.fail("history covers it")) == 500.0
    assert mcap_at(date(2026, 10, 30), hist, lambda d: 1.0) == 520.0
    assert mcap_at(date(2024, 1, 5), hist, lambda d: 123.0) == 123.0       # before history: derived
    assert mcap_at(date(2024, 1, 5), [], lambda d: None) is None


def test_history_row_keeps_point_in_time_fields_only():
    from scanner.fundamentals import history_row
    snap = {"symbol": "TCS", "consolidated": True, "market_cap_cr": 1.0, "price": 2.0, "pe": 3.0,
            "promoter_pct": 71.0, "fii_pct": 12.0, "dii_pct": 10.0, "public_pct": 6.0,
            "n_shareholders": 100, "shp_period": "2026-06-30", "history": {"annual": []}, "roe": 40}
    assert history_row(snap, date(2026, 9, 27)) == {
        "symbol": "TCS", "as_of": "2026-09-27", "market_cap_cr": 1.0, "price": 2.0, "pe": 3.0,
        "promoter_pct": 71.0, "fii_pct": 12.0, "dii_pct": 10.0, "public_pct": 6.0,
        "n_shareholders": 100, "shp_period": "2026-06-30"}


def test_freshness_covers_point_in_time_tables():
    from scripts.check_freshness import FLOORS, RULES
    assert "snapshot_history" in RULES and "nifty50_members" in FLOORS

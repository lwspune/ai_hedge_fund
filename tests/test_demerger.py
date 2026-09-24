"""Test-first spec for the demerger listing-flow study (candidate signal #10).

The pure logic beyond scanner.eventstudy: building one event per newly listed demerged
child from the curated data/demerger_listings.csv with guards, and the pre-specified windows.
"""
from datetime import date

import pandas as pd
import pytest

from scanner.demerger import (MAX_GAP_DAYS, MIN_GAP_DAYS, PLACEBO, WINDOWS, index_at,
                              load_listings, study_events)

COMPANIES = {"JIOFIN": {"symbol": "JIOFIN", "status": "listed"},
             "BIRLATYRE": {"symbol": "BIRLATYRE", "status": "delisted"},
             "RELIANCE": {"symbol": "RELIANCE", "status": "listed"}}


def _row(**kw):
    base = {"parent": "RELIANCE", "ex_date": "2023-07-20", "child": "JIOFIN",
            "listing_date": "2023-08-21", "parent_index": "nifty50", "note": ""}
    return {**base, **kw}


def test_study_event_carries_scheme_key_era_and_gap():
    ev = study_events([_row()], COMPANIES, today=date(2026, 9, 24))
    assert len(ev) == 1
    e = ev[0]
    assert e["child"] == "JIOFIN" and e["parent"] == "RELIANCE"
    assert e["scheme"] == "RELIANCE|2023-07-20"       # cluster key: children of one scheme share dates
    assert e["gap_days"] == 32
    assert e["era"] == "2022-23"
    assert e["parent_index"] == "nifty50"


def test_study_events_drop_children_missing_from_the_master_or_outside_the_gap_window():
    rows = [_row(child="GHOST"),                                   # not in the company master
            _row(listing_date="2023-07-25"),                        # 5 days: not a scheme listing
            _row(listing_date="2025-01-01"),                        # > MAX_GAP_DAYS: unrelated listing
            _row(parent="KESORAMIND", ex_date="2019-12-24", child="BIRLATYRE", listing_date="2020-02-10",
                 parent_index="")]                                  # delisted child still counts
    ev = study_events(rows, COMPANIES, today=date(2026, 9, 24))
    assert [e["child"] for e in ev] == ["BIRLATYRE"]
    assert MIN_GAP_DAYS == 10 and MAX_GAP_DAYS == 400


def test_study_events_drop_listings_too_recent_for_the_full_window():
    ev = study_events([_row(listing_date="2026-09-01", ex_date="2026-08-01")], COMPANIES,
                      today=date(2026, 9, 24))
    assert ev == []


def test_windows_are_prespecified_and_contiguous():
    # T = the child's first trading day. The forced-selling window is the first five sessions
    # (inside the 10-session trade-for-trade period); recovery starts where it ends.
    assert WINDOWS["sell"] == (0, 5)
    assert WINDOWS["recovery"] == (5, 20)
    assert WINDOWS["late"] == (10, 30)
    assert WINDOWS["full"] == (0, 30)
    assert all(b - a == 5 for a, b in PLACEBO.values())          # same length as the sell window
    assert min(a for a, _ in PLACEBO.values()) >= 60             # well clear of the event


def test_load_listings_reads_the_curated_csv_with_the_expected_columns():
    rows = load_listings()
    assert len(rows) >= 60
    assert {"parent", "ex_date", "child", "listing_date", "parent_index", "note"} <= set(rows[0])
    assert all(r["listing_date"] > r["ex_date"] for r in rows)
    assert len({r["child"] for r in rows}) == len(rows)          # one row per listed child


def test_index_at_reads_membership_intervals():
    rows = [{"symbol": "RELIANCE", "index_key": "nifty50", "from_date": "2010-01-01", "to_date": None},
            {"symbol": "PEL", "index_key": "next50", "from_date": "2021-03-31", "to_date": "2023-03-31"}]
    assert index_at("RELIANCE", date(2023, 7, 20), rows) == "nifty50"
    assert index_at("PEL", date(2022, 8, 30), rows) == "next50"
    assert index_at("PEL", date(2024, 1, 1), rows) is None
    assert index_at("ABC", date(2024, 1, 1), rows) is None

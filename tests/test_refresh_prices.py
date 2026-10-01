"""refresh_prices planning helpers (DATA_INFRA_SPEC WP3)."""
from datetime import date

from scripts.refresh_prices import calendar_from_presence, in_table_window, months_of


def test_calendar_from_presence_marks_past_weekdays_only():
    checked = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 5)]
    present = {date(2026, 10, 1), date(2026, 10, 5)}
    rows = calendar_from_presence(checked, present, today=date(2026, 10, 5))
    # Sat 3rd skipped (weekend); Mon 5th = today, not yet final -> skipped
    assert rows == [
        {"trade_date": "2026-10-01", "is_trading": True, "description": None, "source": "nse_bhavcopy"},
        {"trade_date": "2026-10-02", "is_trading": False, "description": None, "source": "nse_bhavcopy"},
    ]


def test_in_table_window():
    today = date(2026, 9, 24)
    assert in_table_window(date(2024, 9, 25), today, keep_days=730)
    assert not in_table_window(date(2024, 9, 23), today, keep_days=730)


def test_table_window_is_400_days():
    """Decision 2026-09-30: the table is a hot cache (older dates come from the bucket); 400 days
    keeps the DB ~70 MB under the 400 MB fail line. The default must follow the constant."""
    from scripts.refresh_prices import KEEP_DAYS
    assert KEEP_DAYS == 400
    today = date(2026, 9, 30)
    assert in_table_window(date(2025, 8, 27), today)
    assert not in_table_window(date(2025, 8, 25), today)


def test_months_of_groups_dates():
    ds = [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)]
    assert months_of(ds) == {"2026-08": [date(2026, 8, 31)], "2026-09": [date(2026, 9, 1), date(2026, 9, 2)]}


def test_holiday_copy_of_previous_day_is_not_a_trading_day():
    """NSE serves the previous session's file under a holiday's name (2026-09-14 -> 09-11 data)."""
    from scripts.refresh_prices import file_is_for
    rows = [{"symbol": "X", "trade_date": "2026-09-11"}]
    assert file_is_for(rows, date(2026, 9, 11))
    assert not file_is_for(rows, date(2026, 9, 14))


def test_indices_only_backfills_benchmarks_without_touching_bhavcopies(monkeypatch):
    """Market regime: index_prices 2020-01 -> 2022-07 from Yahoo, no bhavcopy fetch or bucket write."""
    import sys
    import scripts.refresh_prices as rp
    calls = []
    monkeypatch.setattr(rp, "run", lambda *a, **k: calls.append(("run", a)))
    monkeypatch.setattr(rp, "refresh_indices", lambda frm, to: calls.append(("indices", frm, to)) or 0)
    monkeypatch.setattr(sys, "argv", ["refresh_prices.py", "--indices-only", "--from", "2020-01-01", "--to", "2022-07-31"])
    rp.main()
    assert calls == [("indices", date(2020, 1, 1), date(2022, 7, 31))]


# --- index fallback: NSE's daily index file for sessions Yahoo misses ---------------------------------

D1, D2, D3 = date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)


def _file(d, n50, n500):
    return {"^NSEI": {"date": d, "close": n50[0], "change": n50[1]},
            "^CRSLDX": {"date": d, "close": n500[0], "change": n500[1]}}


def test_plan_fallback_fills_confirmed_closes_and_says_why_it_skips():
    from scripts.refresh_prices import plan_fallback
    known = {"^NSEI": {D1: 26129.6, D3: 26328.6}, "^CRSLDX": {D1: 23871.6, D3: 24099.0}}
    missing = {"^NSEI": [D2], "^CRSLDX": [D2]}
    rows, skipped = plan_fallback(missing, {D2: _file(D2, (26146.55, 16.95), (23909.55, 38.0))}, known)
    assert rows == [{"index_symbol": "^NSEI", "trade_date": "2026-01-01", "close": 26146.55},
                    {"index_symbol": "^CRSLDX", "trade_date": "2026-01-01", "close": 23909.55}]
    assert skipped == []
    # a holiday copy (the file is another day's), a missing file, a failed check: skipped, never stored
    rows, skipped = plan_fallback(missing, {D2: _file(D1, (26146.55, 16.95), (23909.55, 38.0))}, known)
    assert rows == [] and all("is for 2025-12-31" in why for _, _, why in skipped)
    rows, skipped = plan_fallback(missing, {D2: None}, known)
    assert rows == [] and all(why == "no NSE file" for _, _, why in skipped)
    rows, skipped = plan_fallback(missing, {D2: _file(D2, (26146.55, 16.95), (23000.0, 38.0))}, known)
    assert [r["index_symbol"] for r in rows] == ["^NSEI"] and skipped[0][:2] == ("^CRSLDX", D2)


def test_plan_fallback_chains_consecutive_missing_days():
    """Two missing sessions in a row: the second checks against the first one just filled."""
    from scripts.refresh_prices import plan_fallback
    known = {"^CRSLDX": {D1: 23871.6}}
    files = {D2: {"^CRSLDX": {"date": D2, "close": 23909.55, "change": 38.0}},
             D3: {"^CRSLDX": {"date": D3, "close": 24099.0, "change": 189.45}}}
    rows, skipped = plan_fallback({"^CRSLDX": [D3, D2]}, files, known)
    assert [r["trade_date"] for r in rows] == ["2026-01-01", "2026-01-02"] and skipped == []


def test_refresh_indices_falls_back_to_nse_for_sessions_yahoo_misses(monkeypatch):
    import scripts.refresh_prices as rp
    inserted, fetched = [], []
    monkeypatch.setattr(rp, "_yahoo_closes", lambda frm, to: {"^NSEI": {D1: 26129.6, D3: 26328.6},
                                                              "^CRSLDX": {D1: 23871.6, D3: 24099.0}})
    monkeypatch.setattr(rp, "_known_closes", lambda frm, to: {"^NSEI": {D1: 26129.6, D3: 26328.6},
                                                              "^CRSLDX": {D1: 23871.6, D3: 24099.0}})
    monkeypatch.setattr(rp, "_insert_index_rows", lambda rows: inserted.extend(rows))
    monkeypatch.setattr(rp, "fetch_index_closes", lambda d, s=None: fetched.append(d) or "file")
    monkeypatch.setattr(rp, "parse_index_closes", lambda text: _file(D2, (26146.55, 16.95), (23909.55, 38.0)))
    monkeypatch.setattr(rp, "POLITE", 0)
    n = rp.refresh_indices(D1, D3, sessions={D1, D2, D3})
    assert fetched == [D2]                                   # one NSE file per missing session, nothing else
    assert {(r["index_symbol"], r["trade_date"]) for r in inserted} >= {("^NSEI", "2026-01-01"), ("^CRSLDX", "2026-01-01")}
    assert n == 6


def test_plan_fallback_accepts_an_index_s_first_close_only_when_allowed():
    """A sector index's first-ever close has nothing before it to check against: stored on a date match."""
    from scripts.refresh_prices import plan_fallback
    files = {D2: {"Nifty Bank": {"date": D2, "close": 59711.55, "change": 129.7}},
             D3: {"Nifty Bank": {"date": D3, "close": 59800.0, "change": 88.45}}}
    rows, skipped = plan_fallback({"Nifty Bank": [D2, D3]}, files, {}, allow_first=True)
    assert [(r["trade_date"], r["close"]) for r in rows] == [("2026-01-01", 59711.55), ("2026-01-02", 59800.0)]
    rows, _ = plan_fallback({"Nifty Bank": [D2]}, files, {})                    # benchmarks: never unchecked
    assert rows == []
    holiday = {D2: {"Nifty Bank": {"date": D1, "close": 59711.55, "change": 129.7}}}
    assert plan_fallback({"Nifty Bank": [D2]}, holiday, {}, allow_first=True)[0] == []
    # a 2020 backfill after the daily run already stored later rows: the earliest day is still a first close
    later = {"Nifty Bank": {date(2026, 9, 30): 60000.0}}
    rows, _ = plan_fallback({"Nifty Bank": [D2, D3]}, files, later, allow_first=True)
    assert [r["trade_date"] for r in rows] == ["2026-01-01", "2026-01-02"]


def test_refresh_sectors_stores_checked_closes_for_every_session(monkeypatch):
    import scripts.refresh_prices as rp
    inserted, fetched = [], []
    monkeypatch.setattr(rp, "_last_closes_before", lambda syms, d: {"Nifty Bank": (D1, 59581.85)})
    monkeypatch.setattr(rp, "_known_closes_for", lambda syms, frm, to: {s: {} for s in syms})
    monkeypatch.setattr(rp, "_insert_index_rows", lambda rows: inserted.extend(rows))
    monkeypatch.setattr(rp, "_index_file", lambda d: fetched.append(d) or "file")
    monkeypatch.setattr(rp, "parse_index_closes", lambda text, names=None: {
        "Nifty Bank": {"date": D2, "close": 59711.55, "change": 129.7},
        "Nifty IT": {"date": D2, "close": 38171.5, "change": 287.45}})
    monkeypatch.setattr(rp, "sector_symbols", lambda: ["Nifty Bank", "Nifty IT"])
    monkeypatch.setattr(rp, "load_sector_indices", lambda: {"nifty bank": "Nifty Bank", "nifty it": "Nifty IT"})
    n = rp.refresh_sectors({D2})
    assert fetched == [D2] and n == 2
    assert {(r["index_symbol"], r["close"]) for r in inserted} == {("Nifty Bank", 59711.55), ("Nifty IT", 38171.5)}


def test_plan_fallback_bridges_a_special_session_the_stock_store_lacks():
    """Muhurat 2021-11-04: NSE's 11-08 change is from the 11-04 close, a session the bhavcopy store doesn't
    have. The check must find and store that session instead of failing every day after it."""
    from scripts.refresh_prices import plan_fallback
    d0, mu, d1, d2 = date(2021, 11, 3), date(2021, 11, 4), date(2021, 11, 8), date(2021, 11, 9)
    known = {"Nifty Bank": {d0: 39402.05}}
    files = {d1: {"Nifty Bank": {"date": d1, "close": 39438.25, "change": -135.45}},
             d2: {"Nifty Bank": {"date": d2, "close": 39368.8, "change": -69.45}}}
    extra = {mu: {"Nifty Bank": {"date": mu, "close": 39573.7, "change": 171.65}}}
    rows, skipped = plan_fallback({"Nifty Bank": [d1, d2]}, files, known, lookup=extra.get)
    assert [(r["trade_date"], r["close"]) for r in rows] == [
        ("2021-11-04", 39573.7), ("2021-11-08", 39438.25), ("2021-11-09", 39368.8)]
    assert skipped == []
    rows, skipped = plan_fallback({"Nifty Bank": [d1, d2]}, files, known)          # no lookup: as before
    assert rows == [] and len(skipped) == 2
    bad = {mu: {"Nifty Bank": {"date": mu, "close": 40000.0, "change": 171.65}}}   # a bridge that doesn't chain
    assert plan_fallback({"Nifty Bank": [d1]}, files, known, lookup=bad.get)[0] == []

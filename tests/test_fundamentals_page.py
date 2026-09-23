"""Test-first spec for the full screener.in company-page parser (infra I4)."""
from bs4 import BeautifulSoup

from scanner.fundamentals import (
    parse_number, period_end, parse_statements, parse_company_page, snapshot_row, has_financials,
)


def _table(sid, header, rows, div_id=None):
    th = "".join(f"<th>{h}</th>" for h in [""] + header)
    body = "".join("<tr><td class='text'>" + name + "</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
                   for name, vals in rows)
    t = f"<table class='data-table'><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"
    return f"<section id='{sid}'>{f'<div id={div_id!r}>{t}</div>' if div_id else t}</section>"


PAGE = (
    "<html><body>"
    "<ul id='top-ratios'>"
    "<li><span class='name'>Market Cap</span><span class='value'>₹ 7,55,677 Cr.</span></li>"
    "<li><span class='name'>Current Price</span><span class='value'>₹ 2,090</span></li>"
    "<li><span class='name'>High / Low</span><span class='value'>₹ 3,350 / 1,976</span></li>"
    "<li><span class='name'>Stock P/E</span><span class='value'>14.1</span></li>"
    "<li><span class='name'>Book Value</span><span class='value'>₹ 296</span></li>"
    "<li><span class='name'>Dividend Yield</span><span class='value'>3.06 %</span></li>"
    "<li><span class='name'>ROCE</span><span class='value'>63.0 %</span></li>"
    "<li><span class='name'>ROE</span><span class='value'>51.8 %</span></li>"
    "<li><span class='name'>Face Value</span><span class='value'>₹ 1.00</span></li>"
    "</ul>"
    "<section id='peers'><a href='/market/IN08/'>Information Technology</a>"
    "<a href='/market/IN08/IN0801/'>Information Technology</a>"
    "<a href='/market/IN08/IN0801/IN080101/'>IT - Software</a>"
    "<a href='/market/IN08/IN0801/IN080101/IN080101001/'>Computers - Software &amp; Consulting</a></section>"
    + _table("quarters", ["Mar 2026", "Jun 2026"],
             [("Sales&nbsp;+", ["60,000", "62,000"]), ("OPM %", ["26%", "25%"]),
              ("Net Profit&nbsp;+", ["12,000", ""]), ("Raw PDF", ["", ""])])
    + _table("profit-loss", ["Mar 2025", "Mar 2026", "TTM"],
             [("Sales&nbsp;+", ["2,40,000", "2,50,000", "2,55,000"]),
              ("Net Profit&nbsp;+", ["48,000", "50,000", "51,000"])])
    + _table("balance-sheet", ["Mar 2025", "Mar 2026"],
             [("Equity Capital", ["362", "362"]), ("Reserves", ["90,000", "99,638"]),
              ("Borrowings&nbsp;+", ["8,000", "10,000"])])
    + _table("cash-flow", ["Mar 2026"], [("Cash from Operating Activity&nbsp;+", ["45,000"])])
    + _table("ratios", ["Mar 2026"], [("ROCE %", ["63%"])])
    + _table("shareholding", ["Mar 2026", "Jun 2026"],
             [("Promoters&nbsp;+", ["71.77%", "71.77%"]), ("FIIs&nbsp;+", ["11.5%", "11.2%"]),
              ("DIIs&nbsp;+", ["10.0%", "10.4%"]), ("Government&nbsp;+", ["0.05%", "0.05%"]),
              ("Public&nbsp;+", ["6.68%", "6.58%"]), ("No. of Shareholders", ["25,00,000", "24,80,000"])],
             div_id="quarterly-shp")
    + "</body></html>"
)


def test_parse_number():
    assert parse_number("₹ 7,55,677 Cr.") == 755677.0
    assert parse_number("3.06 %") == 3.06
    assert parse_number("-1,234") == -1234.0
    assert parse_number("") is None and parse_number(None) is None and parse_number("—") is None


def test_period_end():
    assert period_end("Mar 2026") == "2026-03-31"
    assert period_end("Jun 2026") == "2026-06-30"
    assert period_end("Feb 2024") == "2024-02-29"
    assert period_end("TTM") is None


def test_parse_statements_long_format_strips_plus_and_skips_blanks():
    soup = BeautifulSoup(PAGE, "lxml")
    rows = parse_statements(soup)
    q = [r for r in rows if r["section"] == "quarters"]
    assert {"section": "quarters", "line_item": "Sales", "period": "Jun 2026",
            "period_end": "2026-06-30", "value": 62000.0} in q
    assert not any(r["line_item"] == "Raw PDF" for r in rows)
    assert not any(r["line_item"] == "Net Profit" and r["period"] == "Jun 2026" for r in q)  # blank cell
    ttm = [r for r in rows if r["section"] == "profit-loss" and r["period"] == "TTM"]
    assert {r["line_item"]: r["value"] for r in ttm} == {"Sales": 255000.0, "Net Profit": 51000.0}
    shp = [r for r in rows if r["section"] == "shareholding" and r["period"] == "Jun 2026"]
    assert {r["line_item"]: r["value"] for r in shp}["Public"] == 6.58


def test_parse_company_page_top_ratios_and_sector():
    page = parse_company_page(PAGE)
    assert page["ratios"]["market_cap_cr"] == 755677.0
    assert page["ratios"]["pe"] == 14.1 and page["ratios"]["roe"] == 51.8
    assert page["ratios"]["dividend_yield"] == 3.06 and page["ratios"]["face_value"] == 1.0
    assert page["sector"] == "Information Technology"
    assert page["industry"] == "IT - Software"
    assert page["basic_industry"] == "Computers - Software & Consulting"
    assert has_financials(page)
    assert not has_financials(parse_company_page("<html><section id='quarters'></section></html>"))


def test_snapshot_row_latest_values_and_debt_to_equity():
    row = snapshot_row("TCS", parse_company_page(PAGE), consolidated=True)
    assert row["symbol"] == "TCS" and row["consolidated"] is True
    assert row["market_cap_cr"] == 755677.0 and row["price"] == 2090.0
    assert row["revenue_ttm"] == 255000.0 and row["net_profit_ttm"] == 51000.0
    assert row["debt_to_equity"] == round(10000 / (362 + 99638), 3)
    assert row["promoter_pct"] == 71.77 and row["public_pct"] == 6.58
    assert row["n_shareholders"] == 2480000
    assert row["shp_period"] == "2026-06-30"
    assert row["sector"] == "Information Technology"


def test_snapshot_row_guards_out_of_range_percentages():
    bad = PAGE.replace("71.77%", "171.77%")
    assert snapshot_row("TCS", parse_company_page(bad), consolidated=True)["promoter_pct"] is None


def test_history_compact_series_for_dashboard():
    from scanner.fundamentals import history_json
    h = history_json(parse_company_page(PAGE))
    assert h["annual"] == [
        {"period": "Mar 2025", "revenue": 240000.0, "net_profit": 48000.0},
        {"period": "Mar 2026", "revenue": 250000.0, "net_profit": 50000.0},
        {"period": "TTM", "revenue": 255000.0, "net_profit": 51000.0},
    ]
    assert h["quarterly"][-1] == {"period": "Jun 2026", "revenue": 62000.0, "opm": 25.0}
    assert h["shareholding"][-1] == {"period": "Jun 2026", "promoter": 71.77, "fii": 11.2,
                                     "dii": 10.4, "public": 6.58, "holders": 2480000.0}


def test_snapshot_row_includes_history():
    row = snapshot_row("TCS", parse_company_page(PAGE), consolidated=True)
    assert row["history"]["annual"][-1]["period"] == "TTM"


def test_pick_view_prefers_the_fresher_statements():
    """3M India: the consolidated view stopped at Jun 2024 while standalone is current."""
    from scanner.fundamentals import latest_quarter, pick_view
    stale = parse_company_page(PAGE.replace("Mar 2026", "Mar 2024").replace("Jun 2026", "Jun 2024"))
    fresh = parse_company_page(PAGE)
    assert latest_quarter(fresh) == "2026-06-30"
    assert pick_view(stale, fresh) == (fresh, False)
    assert pick_view(fresh, stale) == (fresh, True)
    assert pick_view(fresh, fresh) == (fresh, True)      # tie -> consolidated
    assert pick_view(None, fresh) == (fresh, False)
    assert pick_view(fresh, None) == (fresh, True)
    assert pick_view(None, None) is None

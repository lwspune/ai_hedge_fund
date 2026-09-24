"""Probe every data source from the current machine (run in CI to test datacenter reach).

    python scripts/probe_sources.py      # exits 0 always; prints OK/FAIL per source
"""
from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def probe(name, fn):
    try:
        detail = fn()
        print(f"OK    {name:<32} {detail}", flush=True)
    except Exception as e:  # report, don't stop: we want the whole matrix
        print(f"FAIL  {name:<32} {e!r}"[:220], flush=True)
        traceback.print_exc(limit=1, file=sys.stdout)


def main():
    from scanner import master, events, deals, fundamentals
    from scanner.pricestore import _fetch_nse, _fetch_yf
    probe("nse archive EQUITY_L.csv", lambda: len(master.parse_equity_list(master._get(master.EQUITY_URL))))
    probe("niftyindices nifty50 list", lambda: len(master.parse_index_list(master._get(master.INDEX_URLS["nifty50"]))))
    probe("nse archive F&O ban", lambda: len(events.fetch_fo_ban(date.today() - timedelta(days=1))) >= 0)
    probe("nse archive bulk.csv", lambda: len(deals.fetch_deals()))
    probe("chittorgarh IPO page", lambda: events.fetch_ipo(2400)[1]["symbol"])
    probe("nselib corporate actions", lambda: len(events.fetch_corp_actions(date.today() - timedelta(days=30), date.today())))
    probe("nselib bulk deal history", lambda: len(__import__("nselib").capital_market.bulk_deal_data(
        from_date=(date.today() - timedelta(days=10)).strftime("%d-%m-%Y"), to_date=date.today().strftime("%d-%m-%Y"))))
    probe("nselib prices (RELIANCE)", lambda: len(_fetch_nse("RELIANCE", start=(date.today() - timedelta(days=30)).isoformat())))
    probe("yfinance ^CRSLDX", lambda: len(_fetch_yf("^CRSLDX", raw=True)))
    probe("NSE SAST reg29 JSON", lambda: len(__import__("scanner.insider", fromlist=["x"]).fetch_reg29(
        date.today() - timedelta(days=14), date.today())))
    probe("chittorgarh rights page", lambda: events.fetch_rights(454)[1]["symbol"])
    probe("screener.in TCS", lambda: fundamentals.fetch_company_page("TCS")[0]["ratios"].get("market_cap_cr"))


if __name__ == "__main__":
    main()

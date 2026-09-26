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


def _investorgain_gmp() -> str:
    """chittorgarh id -> investorgain GMP page (redirect), which must carry the gmpData payload."""
    import requests
    ua = {"User-Agent": "Mozilla/5.0"}
    r = requests.get("https://www.investorgain.com/chr-gmp/x/2020/", headers=ua, timeout=20, allow_redirects=False)
    loc = r.headers.get("location")
    if not loc:
        raise RuntimeError(f"no redirect ({r.status_code})")
    page = requests.get(loc, headers=ua, timeout=20)
    if page.status_code != 200 or "gmpData" not in page.text:
        raise RuntimeError(f"{page.status_code}, gmpData {'present' if 'gmpData' in page.text else 'absent'}")
    return f"{loc.rstrip('/').split('/')[-1]} ok, {len(page.text)} bytes"


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
    probe("NSE corporate announcements", lambda: len(__import__("scanner.filings", fromlist=["x"]).fetch_announcements(
        date.today() - timedelta(days=2), date.today())))
    probe("chittorgarh rights page", lambda: events.fetch_rights(454)[1]["symbol"])
    probe("investorgain IPO GMP page", _investorgain_gmp)
    probe("screener.in TCS", lambda: fundamentals.fetch_company_page("TCS")[0]["ratios"].get("market_cap_cr"))
    # DATA_INFRA_SPEC WP6 (calendar) + WP3 (bhavcopy)
    probe("NSE holiday master JSON", lambda: len(events.holiday_descriptions(events.fetch_holidays())))
    probe("NSE board meetings JSON", lambda: len(events.fetch_board_meetings(
        date.today() - timedelta(days=30), date.today())))
    probe("nse archive band changes", lambda: len(events.fetch_band_changes()) >= 0)
    probe("nse archive bhavcopy", lambda: _bhav_rows())
    # 2026-09-24 GitHub review unlocks (docs/GITHUB_PROJECT_REVIEW.md section 3)
    from scanner import shareholding, surveillance, prefissues, insider
    probe("NSE PIT pit-gg JSON", lambda: len(insider.fetch_pit_filings(
        date.today() - timedelta(days=7), date.today())))
    probe("NSE ASM JSON", lambda: len(surveillance.parse_asm(surveillance.fetch_asm(), date.today())))
    probe("NSE GSM JSON", lambda: len(surveillance.parse_gsm(surveillance.fetch_gsm(), date.today())))
    probe("NSE shareholding master", lambda: shareholding.fetch_shp_master("INDUSINDBK")[0]["quarter_end"])
    probe("NSE SHP XBRL small-holder %", lambda: shareholding.parse_shp_xbrl(shareholding.fetch_xbrl(
        shareholding.fetch_shp_master("INDUSINDBK")[0]["xbrl_url"]))["small_holder_pct"])
    probe("NSE pref issues listing", lambda: len(prefissues.fetch_pref(
        "listing", date.today() - timedelta(days=60), date.today())))
    probe("NSE pref listing XBRL lock-in", lambda: prefissues.parse_pref_ls_xbrl(prefissues.fetch_xbrl(
        prefissues.fetch_pref("listing", date.today() - timedelta(days=60), date.today())[0]["xml_url"]))["lockins"])
    probe("BSE announcements JSON", lambda: _bse_announcements())


def _bhav_rows():
    """Rows in the latest available sec_bhavdata_full file (walks back over holidays)."""
    import requests
    for k in range(1, 8):
        d = date.today() - timedelta(days=k)
        r = requests.get(f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code == 200:
            return f"{d}: {len(r.text.splitlines())} lines"
    raise RuntimeError("no bhavcopy in the last 7 days")


def _bse_announcements():
    """BSE announcements need Referer + Origin (no cookie handshake); AnnGetData/w is dead, this
    endpoint answers one day per call. Not ingested yet — probed for the delisting-RBB backlog."""
    import requests
    d = date.today() - timedelta(days=1)
    r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
                     params={"pageno": 1, "strCat": -1, "strPrevDate": d.strftime("%Y%m%d"), "strScrip": "",
                             "strSearch": "P", "strToDate": d.strftime("%Y%m%d"), "strType": "C", "subcategory": -1},
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/",
                              "Origin": "https://www.bseindia.com"}, timeout=30)
    r.raise_for_status()
    return f"{len(r.json().get('Table', []))} rows on {d}"


if __name__ == "__main__":
    main()

"""IPO grey-market premium (GMP) from investorgain (chittorgarh's sister site): one quote per day
per IPO, the unofficial price over the issue price that grey-market dealers post while the issue
is open. `chr-gmp/x/<chittorgarh id>/` redirects to investorgain's own page, whose Next.js payload
carries `gmpData` — the daily series. Unofficial, thin and manipulable: a signal to test, not a
price. Loader: scripts/refresh_gmp.py; study: scripts/validate_ipo.py.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

import requests

REDIRECT_URL = "https://www.investorgain.com/chr-gmp/x/{id}/"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36"}
_ROW = re.compile(r'"Seq":\d+,"id":\d+,"ipo_id":(\d+),"gmp_date":"(\d{2})-(\d{2})-(\d{4})","gmp":"([^"]*)"')
WINDOW_DAYS = 60     # a quote more than this before listing belongs to another issue


def parse_gmp_page(html: str) -> tuple[int | None, list[dict]]:
    """investorgain GMP page -> (investorgain ipo id, [{gmp_date, gmp}] oldest first). Blank / '-'
    quotes are skipped; a date seen twice (the payload repeats) keeps its first value."""
    found = _ROW.findall((html or "").replace("\\", ""))
    if not found:
        return None, []
    ig_id = int(Counter(r[0] for r in found).most_common(1)[0][0])
    series: dict = {}
    for ipo, dd, mm, yyyy, g in found:
        try:
            v = float(g)
        except ValueError:
            continue
        if int(ipo) == ig_id:
            series.setdefault(date(int(yyyy), int(mm), int(dd)), v)
    return ig_id, [{"gmp_date": d, "gmp": series[d]} for d in sorted(series)]


def gmp_rows(chittorgarh_id: int, investorgain_id: int, listing_date: date, parsed: list[dict]) -> list[dict]:
    """`ipo_gmp` rows, keeping only quotes from the issue's own window: none after listing
    (placeholders added years later) and none long before it (a redirect to another issue)."""
    lo = listing_date - timedelta(days=WINDOW_DAYS)
    return [{"chittorgarh_id": chittorgarh_id, "investorgain_id": investorgain_id,
             "gmp_date": r["gmp_date"].isoformat(), "gmp": r["gmp"]}
            for r in parsed if lo <= r["gmp_date"] <= listing_date]


def gmp_targets(ipos: list[dict], today: date, days: int = 10, since: date | None = None) -> list[int]:
    """chittorgarh ids to (re)read: listed on/after `since` (backfill), else listed in the last
    `days` or not yet listed (the daily run: the series is only quoted while an issue is live)."""
    lo = (since or today - timedelta(days=days)).isoformat()
    return sorted(r["chittorgarh_id"] for r in ipos if r["listing_date"] >= lo)


def decision_gmp(series: list[dict], issue_close: date) -> float | None:
    """The GMP an applicant could see when deciding: the last quote on or before the issue close."""
    seen = [r for r in series if r["gmp_date"] <= issue_close]
    return max(seen, key=lambda r: r["gmp_date"])["gmp"] if seen else None


def fetch_gmp(chittorgarh_id: int, session=None) -> tuple[int | None, list[dict]]:
    """(investorgain id, daily series) for a chittorgarh IPO id; (None, []) when there is no page."""
    s = session or requests.Session()
    r = s.get(REDIRECT_URL.format(id=chittorgarh_id), headers=_UA, timeout=20, allow_redirects=False)
    loc = r.headers.get("location")
    if r.status_code not in (301, 302, 307, 308) or not loc:
        return None, []
    page = s.get(loc if loc.startswith("http") else "https://www.investorgain.com" + loc, headers=_UA, timeout=20)
    return parse_gmp_page(page.text) if page.status_code == 200 else (None, [])

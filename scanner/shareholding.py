"""Quarterly shareholding pattern + promoter pledge per company (infra: `shareholding` table).

Source: NSE `api/corporate-share-holdings-master?index=equities&symbol=X` — one row per filing
(quarter ends + event-triggered interim filings) with the headline promoter/public split and a
link to the SHP XBRL. The XBRL carries what the master lacks:
  * the resident-individual <= Rs 2 lakh nominal category — the small-shareholder float that is
    the denominator of the buyback 15% reservation (`buyback.estimate_entitlement`);
  * MF / DII / FPI shares; the number of shareholders;
  * promoter pledge, both as a share of the promoter holding (the figure screener quotes) and
    as a share of all shares.
Percentages are stored in 0-100 units (the XBRL carries fractions). Contexts are resolved by
their dimension member, not their id, so a renamed context id degrades to None, never garbage.
Verified 2026-09-24 against IndusInd Bank (pledge 42.78% of promoter holding, 6.45% of total).
"""
from __future__ import annotations

import re
from datetime import datetime

import requests

MASTER_URL = "https://www.nseindia.com/api/corporate-share-holdings-master"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}
_QUARTER_ENDS = ("-03-31", "-06-30", "-09-30", "-12-31")

# category member -> stored field; ShareholdingAsAPercentageOfTotalNumberOfShares under each
_PCT_MEMBERS = {
    "ShareholdingOfPromoterAndPromoterGroupMember": "promoter_pct",
    "PublicShareholdingMember": "public_pct",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakhMember": "small_holder_pct",
    "MutualFundsOrUTIMember": "mf_pct",
    "InstitutionsDomesticMember": "dii_pct",
    "InstitutionsForeignMember": "fpi_pct",
}
_COUNT_MEMBERS = {
    "ShareholdingPatternMember": "n_shareholders",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakhMember": "n_small_holders",
}
_PLEDGE_TAG = "EncumberedSharesHeldAsPercentageOfTotalNumberOfShares"
_PLEDGE_FLAG = "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged"
FIELDS = ("promoter_pct", "public_pct", "small_holder_pct", "mf_pct", "dii_pct", "fpi_pct",
          "pledge_pct_of_promoter", "pledge_pct_of_total", "n_shareholders", "n_small_holders")


def _date(s) -> str | None:
    """'30-JUN-2026' -> '2026-06-30'."""
    try:
        return datetime.strptime(str(s).strip()[:11].title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _ts(s) -> str | None:
    """'17-JUL-2026 16:55:08' -> '2026-07-17T16:55:08'."""
    try:
        return datetime.strptime(str(s).strip().title(), "%d-%b-%Y %H:%M:%S").isoformat()
    except ValueError:
        return None


def _num(v) -> float | None:
    try:
        return float(str(v).strip()) if v not in (None, "", "-") else None
    except ValueError:
        return None


def parse_shp_master(raw: list[dict]) -> list[dict]:
    """Quarter-end filings that link an XBRL, newest first, one per quarter (latest broadcast
    wins, so a revised filing supersedes the original)."""
    best: dict[str, dict] = {}
    for r in raw or []:
        q, url = _date(r.get("date")), r.get("xbrl")
        if not q or not q.endswith(_QUARTER_ENDS) or not url:
            continue
        row = {"symbol": (r.get("symbol") or "").strip().upper(), "quarter_end": q,
               "broadcast_at": _ts(r.get("broadcastDate")), "promoter_pct": _num(r.get("pr_and_prgrp")),
               "public_pct": _num(r.get("public_val")), "revised": r.get("revisedData") == "Y", "xbrl_url": url}
        if q not in best or (row["broadcast_at"] or "") > (best[q]["broadcast_at"] or ""):
            best[q] = row
    return [best[q] for q in sorted(best, reverse=True)]


def _member_contexts(xml: str) -> dict[str, list[str]]:
    """{CategoryOfShareholders member -> [context ids]} from the context declarations."""
    out: dict[str, list[str]] = {}
    for cid, body in re.findall(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', xml, re.S):
        m = re.search(r'CategoryOfShareholdersAxis">in-bse-shp:(\w+)<', body)
        if m:
            out.setdefault(m.group(1), []).append(cid)
    return out


def _fact(xml: str, tag: str, ctx_ids: list[str]) -> str | None:
    for cid in ctx_ids:
        m = re.search(rf'<in-bse-shp:{tag}\s[^>]*contextRef="{re.escape(cid)}"[^>]*>([^<]*)<', xml)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _pct(s) -> float | None:
    v = _num(s)
    return None if v is None else round(v * 100, 2)


def parse_shp_xbrl(xml: str) -> dict:
    """The FIELDS above from an SHP XBRL; every field None when the taxonomy isn't recognised.
    Pledge: the promoter-context value; 0.0 when the filing flags 'no pledge'; None when it
    flags a pledge but the value can't be read (unknown, not zero)."""
    ctx = _member_contexts(xml)
    out: dict = {f: None for f in FIELDS}
    for member, field in _PCT_MEMBERS.items():
        out[field] = _pct(_fact(xml, "ShareholdingAsAPercentageOfTotalNumberOfShares", ctx.get(member, [])))
    for member, field in _COUNT_MEMBERS.items():
        v = _num(_fact(xml, "NumberOfShareholders", ctx.get(member, [])))
        out[field] = int(v) if v is not None else None
    promo = ctx.get("ShareholdingOfPromoterAndPromoterGroupMember", [])
    out["pledge_pct_of_promoter"] = _pct(_fact(xml, _PLEDGE_TAG, promo))
    out["pledge_pct_of_total"] = _pct(_fact(xml, _PLEDGE_TAG, ctx.get("ShareholdingPatternMember", [])))
    if out["pledge_pct_of_promoter"] is None:
        flag = re.search(rf"<in-bse-shp:{_PLEDGE_FLAG}[^>]*>([^<]*)<", xml)
        if flag and flag.group(1).strip().lower() == "false":
            out["pledge_pct_of_promoter"] = 0.0
            if out["pledge_pct_of_total"] is None:
                out["pledge_pct_of_total"] = 0.0
    return out


def shareholding_row(master: dict, xbrl: dict) -> dict:
    """One `shareholding` row: the XBRL categories, the master's headline split as fallback."""
    row = {"symbol": master["symbol"], "quarter_end": master["quarter_end"],
           "broadcast_at": master.get("broadcast_at"), "revised": bool(master.get("revised")),
           "xbrl_url": master.get("xbrl_url"), "source": "nse_shp"}
    for f in FIELDS:
        row[f] = xbrl.get(f)
    if row["promoter_pct"] is None:
        row["promoter_pct"] = master.get("promoter_pct")
    if row["public_pct"] is None:
        row["public_pct"] = master.get("public_pct")
    return row


def quarters_to_fetch(rows: list[dict], stored: set, limit: int | None = None,
                      floor: str | None = None) -> list[dict]:
    """Master rows whose quarter isn't stored yet (and is on/after `floor`), newest first."""
    out = [r for r in rows if r["quarter_end"] not in stored and (not floor or r["quarter_end"] >= floor)]
    out.sort(key=lambda r: r["quarter_end"], reverse=True)
    return out[:limit] if limit else out


# --- thin I/O -----------------------------------------------------------------

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def fetch_shp_master(symbol: str, s: requests.Session | None = None) -> list[dict]:
    r = (s or session()).get(MASTER_URL, params={"index": "equities", "symbol": symbol}, timeout=60)
    r.raise_for_status()
    data = r.json()
    return parse_shp_master(data if isinstance(data, list) else data.get("data", []))


def fetch_xbrl(url: str, s: requests.Session | None = None) -> str:
    r = (s or session()).get(url, timeout=120)
    r.raise_for_status()
    return r.text

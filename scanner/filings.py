"""NSE filings index (F1): corporate announcements — metadata + attachment link — for the
material business categories. Source: NSE `api/corporate-announcements` (JSON; answers a plain
session with a Referer, like the Reg 29 endpoint). Attachments live on nsearchives (static).

Pure parsing/filtering (tested) + a thin fetcher. Loader: scripts/refresh_filings.py.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests

API = "https://www.nseindia.com/api/corporate-announcements"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Referer": "https://www.nseindia.com/"}

# Material business categories (NSE `desc`). Routine noise (AGMs, newspaper copies, trading
# window, KMP changes, ESOPs, certificates) is not stored.
KEEP = {
    "Investor Presentation", "Analysts/Institutional Investor Meet/Con. Call Updates",
    "Press Release", "Press Release (Revised)", "Outcome of Board Meeting", "Monthly Business Updates",
    "Bagging/Receiving of orders/contracts", "Awarding of order(s)/contract(s)",
    "Acquisition", "Amalgamation/Merger", "Demerger", "Scheme of Arrangement", "Sale or disposal",
    "Other Restructuring", "Capacity addition", "Commencement of commercial production/operations",
    "Product launch", "Arrangements for strategic, technical, manufacturing, or marketing tie up",
    "Agreements", "Disclosure of material issue", "Disruption of Operations",
    "Strikes/Lockouts/Disturbances",
    "Granting/withdrawal/surrender/cancellation/suspension of key licenses/ regulatory approvals",
    "Pendency of Litigation(s)/dispute(s) or the outcome impacting the Company",
    "Action(s) taken or orders passed", "Action(s) initiated or orders passed",
    "Corporate Insolvency Resolution Process", "Disclosure under SEBI Takeover Regulations",
    "Credit Rating", "Credit Rating- Revision", "Credit Rating- New", "Credit Rating- Others",
    "Qualified Institutional Placement", "Issue of Securities",
    "Reply to Clarification- Financial results", "Clarification - Financial Results",
    # the buyback lifecycle (2026-09-24): public announcement -> letter of offer -> post-buyback
    # announcement (the realized acceptance table, scanner/buyback_results.py) -> closure
    "Buyback", "Public Announcement - Buyback of Shares", "Post Buyback Public Announcement",
    "Closure of Buy Back",
}
SUBJECT_MAX = 300   # the table's biggest column (free-tier size); the full text is in the PDF

# Catch-alls kept only when the subject is about the business.
CATCH_ALL = {"General Updates", "Updates", "Others"}
_BUSINESS = re.compile(r"order|contract|letter of (award|intent)|\bLOA\b|\bLOI\b|capacity|plant|"
                       r"commission|acqui|merger|expansion|capex|guidance|business update",
                       re.I)
# Generic categories that carry buyback steps only when the subject says so (record dates are
# mostly dividends; newspaper copies are mostly AGM notices).
BUYBACK_CATCH_ALL = {"Record Date", "Copy of Newspaper Publication", "Updates", "General Updates"}
_BUYBACK = re.compile(r"buy[\s-]*back", re.I)


def is_rating(category: str) -> bool:
    """NSE's credit-rating categories: one `Credit Rating` until Sep-2024, then split into
    `- New / - Revision / - Others` (scanner/ratings.py reads their PDFs)."""
    return (category or "").startswith("Credit Rating")


def keep(row: dict) -> bool:
    cat, subject = row.get("category") or "", row.get("subject") or ""
    if cat in KEEP:
        return True
    if cat in BUYBACK_CATCH_ALL and _BUYBACK.search(subject):
        return True
    return cat in CATCH_ALL and bool(_BUSINESS.search(subject))


def _size_kb(s) -> float | None:
    m = re.match(r"\s*([\d.]+)\s*(KB|MB)", str(s or ""), re.I)
    if not m:
        return None
    v = float(m[1])
    return round(v * 1024 if m[2].upper() == "MB" else v, 2)


def parse_announcements(raw: list[dict]) -> list[dict]:
    """NSE announcement rows -> `filings` rows; rows without id / symbol / timestamp dropped."""
    out = []
    for r in raw:
        sid, sym = str(r.get("seq_id") or ""), (r.get("symbol") or "").strip()
        try:
            ts = datetime.strptime(str(r.get("an_dt") or "").strip(), "%d-%b-%Y %H:%M:%S")
        except ValueError:
            continue
        if not sid.isdigit() or not sym:
            continue
        url = (r.get("attchmntFile") or "").strip()
        out.append({
            "seq_id": int(sid), "symbol": sym, "isin": (r.get("sm_isin") or None),
            "company": (r.get("sm_name") or None), "category": (r.get("desc") or "").strip(),
            "subject": ((r.get("attchmntText") or "").strip()[:SUBJECT_MAX] or None),
            "disclosed_at": ts.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30",
            "attachment_url": url if url.startswith("http") else None,
            "size_kb": _size_kb(r.get("attFileSize") or r.get("fileSize")),
            "has_xbrl": str(r.get("hasXbrl")) == "True",
        })
    return out


def fetch_announcements(frm: date, to: date, session=None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(API, params={"index": "equities", "from_date": frm.strftime("%d-%m-%Y"),
                           "to_date": to.strftime("%d-%m-%Y")}, headers=_HEADERS, timeout=120)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else d.get("data", [])


def fetch_range(frm: date, to: date, step_days: int = 14):
    """Yield (window_start, window_end, rows) in `step_days` windows (keeps responses small)."""
    s, cur = requests.Session(), frm
    while cur <= to:
        end = min(cur + timedelta(days=step_days - 1), to)
        yield cur, end, fetch_announcements(cur, end, s)
        cur = end + timedelta(days=1)

"""Corporate-events calendar (infra I3): one `corporate_events` table fed by

  nse_ca       — nselib `corporate_actions_for_equity` (bonus / split / consolidation /
                 rights / dividend / buyback / demerger; EQ+BE series). Residential IP only.
  nse_fo       — NSE static F&O ban archive, one CSV per trade date (fo_secban_DDMMYYYY.csv).
  chittorgarh  — IPO detail pages by id (`/ipo/x/<id>/`): listing + anchor lock-in expiries
                 (30-day / 90-day), also stored in full in the `ipos` table.

ASM/GSM surveillance lists are NOT here: NSE only serves them via JS-gated JSON APIs.
Pure parsers (tested) + thin fetchers.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import requests

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

EVENT_TYPES = ("bonus", "split", "consolidation", "rights", "dividend", "buyback", "demerger",
               "fo_ban", "ipo_listing", "anchor_lockin_30", "anchor_lockin_90")
_SERIES = {"EQ", "BE"}
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _dmy(s: str | None) -> str | None:
    """'02-Jan-2024' -> '2024-01-02'; '-' / junk -> None."""
    try:
        return datetime.strptime((s or "").strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _long_date(s: str | None) -> str | None:
    """'Wednesday, September 10, 2025' | 'September 4, 2025' -> '2025-09-10'."""
    m = re.search(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()


# --- NSE corporate actions ---------------------------------------------------

_RS = r"r[se]\.?\s*"  # 'Rs' / 'Re'


def classify_action(subject: str) -> tuple[str, dict] | None:
    """Map an NSE corporate-action subject to (event_type, details); None = not tracked."""
    s = re.sub(r"\s+", " ", (subject or "").lower()).strip()
    if "ncrps" in s or "preference" in s:
        return None
    if m := re.search(r"bonus\s*(\d+)\s*:\s*(\d+)", s):
        return "bonus", {"ratio": f"{m[1]}:{m[2]}"}
    if m := re.search(rf"(split|consolidation).*?from\s*{_RS}([\d.]+).*?to\s*{_RS}([\d.]+)", s):
        return ("split" if m[1] == "split" else "consolidation"), \
            {"from_fv": float(m[2]), "to_fv": float(m[3])}
    if m := re.search(r"rights\s*(\d+)\s*:\s*(\d+)\s*@\s*premium\s*" + _RS + r"([\d.]+)", s):
        return "rights", {"ratio": f"{m[1]}:{m[2]}", "premium": float(m[3])}
    if "dividend" in s:
        amounts = [float(a) for a in re.findall(rf"dividend[^0-9]*?(?:{_RS})?(\d+(?:\.\d+)?)", s)]
        if not amounts:
            return None
        return "dividend", {"amount": round(sum(amounts), 4), "interim": "interim" in s,
                            "special": "special" in s}
    if "buy back" in s or "buyback" in s:
        return "buyback", {}
    if "demerger" in s:
        return "demerger", {}
    return None


def corp_action_events(records: list[dict]) -> list[dict]:
    """nselib corporate-action records -> corporate_events rows (EQ/BE, tracked types, dated)."""
    out = []
    for r in records:
        if str(r.get("series", "")).strip() not in _SERIES:
            continue
        c = classify_action(r.get("subject", ""))
        ex = _dmy(r.get("exDate"))
        if c is None or ex is None:
            continue
        out.append({"symbol": str(r["symbol"]).strip(), "event_type": c[0], "event_date": ex,
                    "record_date": _dmy(r.get("recDate")), "details": c[1], "source": "nse_ca"})
    return out


def dedupe_events(events: list[dict]) -> list[dict]:
    """One row per (symbol, event_type, event_date, source) — required for a single upsert
    batch. Same-day dividends (e.g. final + special) are summed; otherwise the last wins."""
    out: dict[tuple, dict] = {}
    for e in events:
        k = (e["symbol"], e["event_type"], e["event_date"], e["source"])
        if k in out and e["event_type"] == "dividend":
            a, b = out[k]["details"], e["details"]
            e = {**e, "details": {"amount": round(a["amount"] + b["amount"], 4),
                                  "interim": a["interim"] or b["interim"],
                                  "special": a["special"] or b["special"]}}
        out[k] = e
    return list(out.values())


def fetch_corp_actions(from_date: date, to_date: date) -> list[dict]:
    from nselib import capital_market as cm
    df = cm.corporate_actions_for_equity(from_date=from_date.strftime("%d-%m-%Y"),
                                         to_date=to_date.strftime("%d-%m-%Y"))
    return corp_action_events(df.to_dict("records")) if df is not None and len(df) else []


# --- F&O ban -------------------------------------------------------------------

FO_BAN_URL = "https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban_{d:%d%m%Y}.csv"


def parse_fo_ban(text: str) -> tuple[date | None, list[str]]:
    m = re.search(r"Trade Date (\d{2}-[A-Za-z]{3}-\d{4})", text or "")
    if not m:
        return None, []
    d = datetime.strptime(m[1], "%d-%b-%Y").date()
    syms = [ln.split(",", 1)[1].strip() for ln in text.splitlines()[1:]
            if re.match(r"^\s*\d+\s*,\s*\S", ln)]
    return d, syms


def fo_ban_events(d: date, symbols: list[str]) -> list[dict]:
    return [{"symbol": s, "event_type": "fo_ban", "event_date": d.isoformat(), "record_date": None,
             "details": {}, "source": "nse_fo"} for s in symbols]


def fetch_fo_ban(d: date) -> list[dict]:
    r = requests.get(FO_BAN_URL.format(d=d), headers=_UA, timeout=20)
    if r.status_code != 200:
        return []
    got, syms = parse_fo_ban(r.text)
    return fo_ban_events(got, syms) if got == d else []


# --- chittorgarh IPOs ------------------------------------------------------------

IPO_URL = "https://www.chittorgarh.com/ipo/x/{id}/"


def _field(h: str, key: str):
    m = re.search(rf'"{key}":(?:"([^"]*)"|(-?[0-9.]+)|null)', h)
    if not m:
        return None
    return m[1] if m[1] is not None else (float(m[2]) if m[2] else None)


def parse_ipo_page(html: str, ipo_id: int) -> dict | None:
    """chittorgarh IPO detail page -> `ipos` row. None unless it has an NSE symbol, a positive
    issue price and a listing date (unlisted / BSE-only / withdrawn issues are skipped)."""
    h = (html or "").replace("\\", "")
    sym = (_field(h, "nse_symbol") or _field(h, "il_nse_script_symbol") or "").strip()
    price = _field(h, "issue_price_final")
    listing = _long_date(_field(h, "timetable_listing_dt") or _field(h, "il_ipo_listing_date"))
    if not sym or not isinstance(price, float) or price <= 0 or not listing:
        return None
    t = re.search(r"<title>([^<]*)", h)
    company = t[1].split(" IPO")[0].strip() if t else None
    listing_at = _field(h, "ipo_listing_at") or None
    anchor = _field(h, "shares_offered_anchor_investor")
    allotted = _field(h, "no_of_shares_allotted")
    close = _field(h, "listing_day_closing_price")
    return {
        "chittorgarh_id": ipo_id, "symbol": sym, "company": company,
        "board": "sme" if listing_at and "SME" in listing_at.upper() else "mainboard",
        "listing_at": listing_at,
        "issue_open": _long_date(_field(h, "issue_open_date")),
        "issue_close": _long_date(_field(h, "issue_close_date")),
        "boa_date": _long_date(_field(h, "timetable_boa_dt")),
        "listing_date": listing, "issue_price": price,
        "listing_close": close if isinstance(close, float) and close > 0 else None,
        "anchor_shares": int(anchor) if isinstance(anchor, float) else None,
        "shares_allotted": int(allotted) if isinstance(allotted, float) else None,
        "anchor_lockin_30": _long_date(_field(h, "timetable_anchor_lockin_end_dt_1")),
        "anchor_lockin_90": _long_date(_field(h, "timetable_anchor_lockin_end_dt_2")),
    }


def ipo_events(ipo: dict) -> list[dict]:
    det = {"chittorgarh_id": ipo["chittorgarh_id"], "anchor_shares": ipo["anchor_shares"],
           "board": ipo["board"]}
    out = [{"symbol": ipo["symbol"], "event_type": "ipo_listing", "event_date": ipo["listing_date"],
            "record_date": None, "details": {**det, "issue_price": ipo["issue_price"]},
            "source": "chittorgarh"}]
    for et, key in (("anchor_lockin_30", "anchor_lockin_30"), ("anchor_lockin_90", "anchor_lockin_90")):
        if ipo[key]:
            out.append({"symbol": ipo["symbol"], "event_type": et, "event_date": ipo[key],
                        "record_date": None, "details": det, "source": "chittorgarh"})
    return out


def fetch_ipo(ipo_id: int, session=None) -> tuple[bool, dict | None]:
    """(page_exists, parsed_row). A 200 page that isn't a listed NSE IPO -> (True, None)."""
    # unknown ids 307-redirect to a listing page (which also says "IPO") -> never follow
    r = (session or requests).get(IPO_URL.format(id=ipo_id), headers=_UA, timeout=20,
                                  allow_redirects=False)
    if r.status_code != 200 or "IPO" not in r.text:
        return False, None
    return True, parse_ipo_page(r.text, ipo_id)

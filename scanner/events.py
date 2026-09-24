"""Corporate-events calendar (infra I3): one `corporate_events` table fed by

  nse_ca       — nselib `corporate_actions_for_equity` (bonus / split / consolidation /
                 rights / dividend / buyback / demerger; EQ+BE series). Residential IP only.
  nse_fo       — NSE static F&O ban archive, one CSV per trade date (fo_secban_DDMMYYYY.csv).
  chittorgarh  — IPO detail pages by id (`/ipo/x/<id>/`): listing + anchor lock-in expiries
                 (30-day / 90-day), also stored in full in the `ipos` table.
  nse_bm       — NSE `api/corporate-board-meetings`: board meetings, 'results' when the purpose
                 mentions results (for results-window contamination control in validations).
  nse_band     — NSE static `eq_band_changes.csv`: price-band changes.
Trading holidays (NSE `api/holiday-master`) go to the `trading_calendar` table.

ASM/GSM surveillance lists are NOT here: NSE only serves them via JS-gated JSON APIs.
Pure parsers (tested) + thin fetchers.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

EVENT_TYPES = ("bonus", "split", "consolidation", "rights", "dividend", "buyback", "demerger",
               "fo_ban", "ipo_listing", "anchor_lockin_30", "anchor_lockin_90",
               "board_meeting", "results", "band_change")
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


def recheck_ids(ipos: list[dict], today: date, days: int = 120) -> list[int]:
    """chittorgarh ids to re-read: listed within `days` (or not yet listed) and still missing
    a lock-in date — those fields get filled in after the page is first seen."""
    cutoff = (today - timedelta(days=days)).isoformat()
    return sorted(r["chittorgarh_id"] for r in ipos
                  if r["listing_date"] >= cutoff
                  and not (r.get("anchor_lockin_30") and r.get("anchor_lockin_90")))


def fetch_ipo(ipo_id: int, session=None) -> tuple[bool, dict | None]:
    """(page_exists, parsed_row). A 200 page that isn't a listed NSE IPO -> (True, None)."""
    # unknown ids 307-redirect to a listing page (which also says "IPO") -> never follow
    r = (session or requests).get(IPO_URL.format(id=ipo_id), headers=_UA, timeout=20,
                                  allow_redirects=False)
    if r.status_code != 200 or "IPO" not in r.text:
        return False, None
    return True, parse_ipo_page(r.text, ipo_id)


RIGHTS_URL = "https://www.chittorgarh.com/rights-issue/x/{id}/"


def _text_field(h: str, key: str) -> str | None:
    """A string field with Next.js escapes undone ('u0026#8377;' -> '₹')."""
    import html as _html
    v = _field(h, key)
    if not isinstance(v, str):
        return None
    v = _html.unescape(v.replace("u0026", "&")).strip()
    return v or None


def _rupees(s: str | None) -> float | None:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", s or "")
    return float(m[1].replace(",", "")) if m else None


def parse_rights_page(html: str, ri_id: int) -> dict | None:
    """chittorgarh rights-issue page -> `rights_issues` row. None unless it has an NSE symbol and
    a positive issue price (BSE-only / incomplete pages are skipped)."""
    h = (html or "").replace("\\", "")
    sym = (_field(h, "nse_symbol") or "").strip() if isinstance(_field(h, "nse_symbol"), str) else ""
    price = _rupees(_text_field(h, "issue_price"))
    if not sym or not price or price <= 0:
        return None
    re_sym = _text_field(h, "re_nse_symbol")
    if sym.endswith("-RE"):  # older pages put the RE symbol in the stock-symbol field
        re_sym, sym = re_sym or sym, sym[:-3]
    terms = _text_field(h, "amount_of_payment")
    # a bare number = amount payable on application; below the issue price -> partly paid
    app = float(terms.replace(",", "")) if terms and re.fullmatch(r"[\d,]+(?:\.\d+)?", terms) else None
    partly = (app is not None and app < price) or bool(terms and re.search(r"call|partly|balance", terms, re.I))
    num = lambda k: int(v) if isinstance(v := _field(h, k), float) else None  # noqa: E731
    return {
        "chittorgarh_id": ri_id, "symbol": sym, "company": _text_field(h, "company_name"),
        "isin": _text_field(h, "isin"), "face_value": _rupees(_text_field(h, "face_value")),
        "issue_price": price,
        "ratio_rights": num("entitlement_rights_equity_share"),
        "ratio_held": num("entitlement_fully_paid_equity_share"),
        "issue_size_shares": num("issue_size_in_shares_number"),
        "record_date": _long_date(_field(h, "record_dt")),
        "re_credit_date": _long_date(_field(h, "rights_entitlements_credit_dt")),
        "issue_open": _long_date(_field(h, "issue_open_date")),
        "renunciation_date": _long_date(_field(h, "timetable_renunciation_dt")),
        "issue_close": _long_date(_field(h, "issue_close_date")),
        "allotment_date": _long_date(_field(h, "timetable_allotment_dt")),
        "listing_date": _long_date(_field(h, "timetable_listing_dt")),
        "re_symbol": re_sym,
        "payment_terms": terms, "application_amount": app,
        "partly_paid": partly,
        "withdrawn": _field(h, "issue_withdraw_status") == 1.0,
    }


def fetch_rights(ri_id: int, session=None) -> tuple[bool, dict | None]:
    """(page_exists, parsed_row). Unknown ids 307-redirect to a list page -> never follow."""
    r = (session or requests).get(RIGHTS_URL.format(id=ri_id), headers=_UA, timeout=20,
                                  allow_redirects=False)
    if r.status_code != 200 or "Rights Issue" not in r.text:
        return False, None
    return True, parse_rights_page(r.text, ri_id)


def rights_recheck_ids(rows: list[dict], today: date, days: int = 45) -> list[int]:
    """Rights pages to re-read: closing within `days` of today (or later) or still undated —
    timetable dates and RE symbols are filled in after the page first appears."""
    cutoff = (today - timedelta(days=days)).isoformat()
    return sorted(r["chittorgarh_id"] for r in rows
                  if r.get("issue_close") is None or r["issue_close"] >= cutoff)


# --- WP6: trading holidays, board meetings / results, price-band changes -------------------
# NSE JSON APIs that answer a plain session with a Referer (like corporate-announcements), and
# the static band-changes CSV on nsearchives.

NSE_API_HEADERS = {**_UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
BOARD_MEETINGS_URL = "https://www.nseindia.com/api/corporate-board-meetings"
BAND_CHANGES_URL = "https://nsearchives.nseindia.com/content/equities/eq_band_changes.csv"
_RESULTS = re.compile(r"results", re.I)


def parse_holiday_master(raw: dict) -> list[date]:
    """Cash-market (CM segment) trading holidays from NSE's holiday master."""
    return list(holiday_descriptions(raw))


def holiday_descriptions(raw: dict) -> dict:
    """{date: description} for the CM segment."""
    out = {}
    for h in (raw or {}).get("CM", []):
        d = _dmy(h.get("tradingDate"))
        if d:
            out[date.fromisoformat(d)] = (h.get("description") or "").strip() or None
    return out


def calendar_rows(holidays: dict, year: int) -> list[dict]:
    """One trading_calendar row per weekday of `year`; is_trading=false on holidays."""
    out, d = [], date(year, 1, 1)
    while d.year == year:
        if d.weekday() < 5:
            out.append({"trade_date": d.isoformat(), "is_trading": d not in holidays,
                        "description": holidays.get(d), "source": "nse_holiday_master"})
        d += timedelta(days=1)
    return out


def parse_board_meetings(raw: list[dict]) -> list[dict]:
    """One event per (symbol, meeting date). NSE lists a meeting twice (the intimation + its
    purpose); it is 'results' when any row's purpose/description mentions results."""
    grouped: dict[tuple, dict] = {}
    for r in raw or []:
        sym, d = (r.get("bm_symbol") or "").strip(), _dmy(r.get("bm_date"))
        if not sym or not d:
            continue
        g = grouped.setdefault((sym, d), {"purposes": [], "results": False})
        purpose = (r.get("bm_purpose") or "").strip()
        if purpose and purpose not in g["purposes"]:
            g["purposes"].append(purpose)
        g["results"] |= bool(_RESULTS.search(purpose) or _RESULTS.search(r.get("bm_desc") or ""))
    return [{"symbol": sym, "event_type": "results" if g["results"] else "board_meeting",
             "event_date": d, "record_date": None,
             "details": {"purpose": " | ".join(g["purposes"])}, "source": "nse_bm"}
            for (sym, d), g in grouped.items()]


def parse_band_changes(text: str, as_of: date) -> list[dict]:
    """eq_band_changes.csv (`Sr. No.,Symbol,Series,Security,From,To`) -> band_change events
    dated `as_of` (the file carries no date; the loader passes its Last-Modified day)."""
    import csv
    import io
    out = []
    for row in csv.DictReader(io.StringIO(text or "")):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        try:
            frm, to = float(row["From"]), float(row["To"])
        except (KeyError, ValueError):
            continue
        if row.get("Symbol"):
            out.append({"symbol": row["Symbol"], "event_type": "band_change",
                        "event_date": as_of.isoformat(), "record_date": None,
                        "details": {"from": frm, "to": to, "series": row.get("Series")},
                        "source": "nse_band"})
    return out


def _nse_session():
    s = requests.Session()
    s.headers.update(NSE_API_HEADERS)
    return s


def fetch_holidays(session=None) -> dict:
    r = (session or _nse_session()).get(HOLIDAY_URL, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_board_meetings(frm: date, to: date, session=None) -> list[dict]:
    r = (session or _nse_session()).get(BOARD_MEETINGS_URL, timeout=60, params={
        "index": "equities", "from_date": frm.strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")})
    r.raise_for_status()
    return parse_board_meetings(r.json())


def fetch_band_changes(session=None) -> list[dict]:
    from email.utils import parsedate_to_datetime
    r = (session or _nse_session()).get(BAND_CHANGES_URL, timeout=30)
    r.raise_for_status()
    lm = r.headers.get("Last-Modified")
    as_of = parsedate_to_datetime(lm).date() if lm else date.today()
    return parse_band_changes(r.text, as_of)

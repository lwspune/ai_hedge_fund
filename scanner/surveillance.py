"""Daily ASM / GSM surveillance snapshot (backlog signal #5; `surveillance_daily` table).

Source: NSE `api/reportASM` ({longterm|shortterm: {data: [...]}}) and `api/reportGSM` (flat
list), JSON behind the reports pages' Referer. They are *snapshots*: `asmTime` is the list-run
date, not the day the stock entered, so history exists only from the day capture starts —
entries, exits and stage changes come from consecutive snapshots (`transitions`).
Send `Accept-Encoding: gzip, deflate` (no `br`): reportASM answers Brotli when offered, which
`requests` can't decode without an extra package.
"""
from __future__ import annotations

from datetime import date

import requests

ASM_URL = "https://www.nseindia.com/api/reportASM"
GSM_URL = "https://www.nseindia.com/api/reportGSM"
LISTS = ("asm_lt", "asm_st", "gsm")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}


def _rows(items, as_of: date, list_name: str, stage_key: str) -> list[dict]:
    out = []
    for r in items or []:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append({"as_of": as_of.isoformat(), "symbol": sym, "list_name": list_name,
                    "stage": (r.get(stage_key) or "").strip() or None,
                    "surv_code": (r.get("survCode") or "").strip() or None})
    return out


def parse_asm(raw: dict, as_of: date) -> list[dict]:
    """Long-term then short-term ASM rows."""
    lt = (raw.get("longterm") or {}).get("data", [])
    st = (raw.get("shortterm") or {}).get("data", [])
    return _rows(lt, as_of, "asm_lt", "asmSurvIndicator") + _rows(st, as_of, "asm_st", "asmSurvIndicator")


def parse_gsm(raw, as_of: date) -> list[dict]:
    items = raw.get("data", []) if isinstance(raw, dict) else raw
    return _rows(items, as_of, "gsm", "gsmStage")


def transitions(prev: list[dict], cur: list[dict]) -> dict:
    """Entries / exits / stage changes between two snapshots, keyed by (symbol, list).
    An empty previous snapshot yields nothing (no baseline to compare against)."""
    if not prev:
        return {"entries": [], "exits": [], "stage_changes": []}
    p = {(r["symbol"], r["list_name"]): r.get("stage") for r in prev}
    c = {(r["symbol"], r["list_name"]): r.get("stage") for r in cur}
    return {
        "entries": sorted(k for k in c if k not in p),
        "exits": sorted(k for k in p if k not in c),
        "stage_changes": sorted((k[0], k[1], p[k], c[k]) for k in c if k in p and p[k] != c[k]),
    }


# --- thin I/O -----------------------------------------------------------------

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def fetch_asm(s: requests.Session | None = None) -> dict:
    r = (s or session()).get(ASM_URL, headers={"Referer": "https://www.nseindia.com/reports/asm"}, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_gsm(s: requests.Session | None = None):
    r = (s or session()).get(GSM_URL, headers={"Referer": "https://www.nseindia.com/reports/gsm"}, timeout=60)
    r.raise_for_status()
    return r.json()

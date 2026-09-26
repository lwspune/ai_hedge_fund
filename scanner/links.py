"""Buyer -> seller links from order-win filings (customer-momentum pilot, drift type).

SEBI's Reg 30 order-win format (2024-09 ->) names the customer in a fixed field, "Name of the
entity awarding the order(s)/contract(s)". `awarding_entity` reads it; `match_listed` maps it to a
listed symbol by exact normalised name or a curated alias only (data/company_aliases.csv) -
precision over recall: fuzzy/substring and abbreviation matching produced false links in Phase 0
(GETCO -> GUJENERGY; NSIL is Nalwa Sons on NSE, NewSpace India in filings).

Pure logic (tested); runner scripts/validate_customer_momentum.py.
"""
from __future__ import annotations

import csv
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ALIASES = Path(__file__).resolve().parent.parent / "data" / "company_aliases.csv"

_HEAD = r"name(?:\s*\(\s*s\s*\)|s)?\s+of\s+(?:the\s+)?entity\s+award(?:ing|\s+in)\s+(?:the\s+)?"
_LABEL = re.compile(
    _HEAD + r"(?:order|contract)s?(?:\s*\(\s*s\s*\))?"
    r"(?:\s*/\s*(?:contract|contact|order)s?(?:\s*\(\s*s\s*\))?)?"
    r"(?:\s*/\s*letter\s+of\s+award\s*\(\s*LOA\s*\))?\s*[;:\-]?\s*(?:reply\s*:\s*)?", re.I)
# table layouts wrap the label around the value: "awarding the | <name> order(s)/contract(s)"
_INLINE = re.compile(_HEAD + r"\|?\s*(.{3,150}?)\s*\|?\s*order\s*\(\s*s\s*\)\s*/\s*contract", re.I)
# the next label of the SEBI table ends the value
_STOP = re.compile(r"\s*(?:\b[a-e1-5][.)]?\s+)?(?:significant\s+terms|nature\s+of\s+the\s+order|whether\s)"
                   r"|\s+[a-e1-5][.)]\s|\s+2\s", re.I)
_WITHHELD = re.compile(r"not\s+disclosed|cannot\s+disclose|confidential|non.?disclosure|\bNDA\b|\bleading\b|"
                       r"\bone\s+of\b|reputed|renowned|prestigious|tier.?\d|\bclient\b|\bcustomer\b|undisclosed|"
                       r"\ban?\s+(?:large|major|global|domestic)\b", re.I)
_DROP = {"limited", "ltd", "pvt", "private", "the", "m", "s", "ms", "company", "co", "inc", "plc"}
_CANON = {"corpn": "corporation", "corp": "corporation"}
_SUFFIX = re.compile(r"\b(?:limited|ltd)\b\.?", re.I)


def awarding_entity(text: str) -> str | None:
    """The customer named in a SEBI order-win filing, or None (field absent or blank)."""
    flat = " ".join((text or "").split())
    m = _LABEL.search(flat)
    if m:
        val = _STOP.split(flat[m.end():m.end() + 250], maxsplit=1)[0]
    elif (m := _INLINE.search(flat)):
        val = m.group(1)
    else:
        return None
    val = re.sub(r"^\s*(?:M/s\.?|Ms\.)\s*", "", val.strip(" |"), flags=re.I).strip(" .;,:-?\"'|")
    return val if len(val) >= 3 else None


def is_withheld(name: str) -> bool:
    return bool(_WITHHELD.search(name or ""))


def name_key(name: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", (name or "").lower()).replace("&", " and ")
    return " ".join(_CANON.get(t, t) for t in re.sub(r"[^a-z0-9]+", " ", s).split() if t not in _DROP)


def load_aliases(path: Path = ALIASES) -> list[dict]:
    """Curated customer-name aliases (name variants, short forms, subsidiaries -> listed parent)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def name_index(companies: list[dict], aliases: list[dict]) -> dict[str, str | None]:
    """Normalised name -> symbol. Listed rows win over delisted ones (a renamed symbol keeps its
    old delisted row); a key two symbols share maps to None (ambiguous: never guessed). Aliases win."""
    idx: dict[str, str | None] = {}
    for listed in (True, False):
        taken = set(idx)
        for c in companies:
            if (c.get("status", "listed") == "listed") != listed or not c.get("name"):
                continue
            k = name_key(c["name"])
            if not k or k in taken:
                continue
            idx[k] = c["symbol"] if idx.get(k, c["symbol"]) == c["symbol"] else None
    for a in aliases:
        idx[name_key(a["alias"])] = a["symbol"]
    return idx


def match_listed(name: str, index: dict[str, str | None]) -> str | None:
    """Exact normalised name (whole text, else the text through its first Limited/Ltd) or alias."""
    if not name:
        return None
    cands = [name]
    m = _SUFFIX.search(name)
    if m:
        cands.append(name[:m.end()])
    for c in cands:
        sym = index.get(name_key(c))
        if sym:
            return sym
    return None


def linked_suppliers(links: list[dict], customer: str, day: pd.Timestamp, window_days: int = 365) -> set[str]:
    """Suppliers whose order from `customer` was public before `day` and at most `window_days` old."""
    d = day.date()
    out = set()
    for ln in links:
        if ln["customer"] != customer:
            continue
        pub = date.fromisoformat(ln["disclosed_at"][:10])
        if pub < d <= pub + timedelta(days=window_days):
            out.add(ln["supplier"])
    return out


def shock_days(ar: pd.Series, threshold: float = 0.05) -> list[tuple[pd.Timestamp, int]]:
    """Days a customer's abnormal return moved >= threshold either way, signed by direction."""
    return [(t, 1 if v > 0 else -1) for t, v in ar.dropna().items() if abs(v) >= threshold]

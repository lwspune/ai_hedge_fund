"""Named holders from the quarterly SHP filings (the India 13F): storage, identity, entries, and
the walk-forward investor ranking of the `investor_skill` study.

SEBI's shareholding pattern names every public holder >= 1% of a company (and every promoter-group
holder). `scanner.shareholding.parse_shp_holders` reads them from the XBRL NSE links per quarter;
`scripts/refresh_holders.py` keeps one parquet per symbol in the private bucket `holders`
(`<SYMBOL>.parquet`), each filing marked by a `_filing` row so "read, nobody new" is distinguishable
from "not read". NSE's master reaches back 20 quarters (Sep-2021 on).

An ENTRY is an investor's first appearance in a company's list after a filed prior quarter, absent
from the previous four filed quarters under any name variant or axis — i.e. it crossed 1% during the
quarter. The follower's entry date is the filing's broadcast date (point-in-time; SHP is due 21 days
after the quarter). Which axes are investors is decided here, not at parse time, so the call can
change without a re-scrape.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

BUCKET = "holders"
FILING = "_filing"
LOOKBACK_QUARTERS = 4
MAX_FILING_LAG_DAYS = 100  # a revision broadcast later than this is too late to be the entry signal

# lower-cased axis (typed-member dimension minus 'DetailsOf…SharesHeldBy' / 'Axis') -> investor kind.
# Everything else is excluded: promoter group (IndividualsOrHUF, OthersIndianShareholders), directors,
# KMP, employee trusts, IEPF, custodians / DR banks, government, pension funds, FDI / foreign companies
# (strategic), and NonResidentIndividualsOrForeignIndividuals (used for promoters and public alike).
_KINDS = {
    "individualshareholdersholdingnominalsharecapitalinexcessofrstwolakh": "individual",
    "residentindividualshareholdersholdingnominalsharecapitalinexcessofrstwolakh": "individual",
    "nonresidentindians": "individual",
    "alternativeinvestmentfunds": "aif",
    "mutualfundsoruti": "mf",
    "institutionsforeignportfolioinvestor": "fpi",
    "institutionsforeignportfolioinvestorone": "fpi",
    "institutionsforeignportfolioinvestortwo": "fpi",
    "insurancecompanies": "insurance",
    "bodiescorporate": "corporate",
    "othernoninstitutions": "corporate",
}
_PASSIVE = re.compile(r"\b(ETF|INDEX|NIFTY|SENSEX|BEES|VANGUARD|ISHARES)\b")
_NOT_INVESTOR = re.compile(r"\b(IEPF|INVESTOR EDUCATION|CLEARING MEMBERS?|UNCLAIMED|SUSPENSE)\b")
_HONORIFICS = {"MR", "MRS", "MS", "DR", "SMT", "SHRI", "SH", "KUM", "MISS", "M/S", "MS/"}
_LEGAL = {"LIMITED", "LTD", "PRIVATE", "PVT", "LLP", "THE", "CO", "COMPANY", "INC", "PLC"}


def filing_rows(master: dict, parsed: list[dict]) -> list[dict]:
    """Storage rows for one filing: a `_filing` marker, then one row per parsed holder."""
    base = {"symbol": master["symbol"], "quarter_end": master["quarter_end"], "broadcast_at": master.get("broadcast_at")}
    rows = [{**base, "axis": FILING, "name": "", "shares": None, "pct": None, "n_holders": None}]
    rows += [{**base, "axis": h["axis"], "name": h["name"], "shares": h["shares"], "pct": h["pct"],
              "n_holders": h.get("n_holders")} for h in parsed]
    return rows


CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "holders"
COLUMNS = ["symbol", "quarter_end", "broadcast_at", "axis", "name", "shares", "pct", "n_holders"]


def _file(symbol: str) -> str:
    return f"{symbol.replace('&', '_and_')}.parquet"


def load_symbol(symbol: str, directory: Path = CACHE_DIR, refresh: bool = False) -> pd.DataFrame | None:
    """A symbol's holder rows: the local cache, else the bucket (cached after download). None if
    never fetched. refresh=True skips the cache (the refresher must see the bucket's copy)."""
    fp = Path(directory) / _file(symbol)
    if refresh or not fp.exists():
        from scanner import db
        data = db.storage_get(BUCKET, _file(symbol))
        if data is None:
            return None
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    return pd.read_parquet(fp)


def save_symbol(symbol: str, df: pd.DataFrame, directory: Path = CACHE_DIR) -> None:
    """Write a symbol's rows locally and to the bucket (the durable copy)."""
    from scanner import db
    fp = Path(directory) / _file(symbol)
    fp.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_parquet(fp, index=False)
    db.storage_put(BUCKET, _file(symbol), fp.read_bytes())


def _tokens(name: str) -> list[str]:
    s = html.unescape(str(name)).upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return [t for t in s.split() if t not in _HONORIFICS]


def holder_kind(axis: str, name: str) -> str | None:
    """The investor kind of a named holder, or None when it isn't a public, active investor."""
    kind = _KINDS.get(str(axis).lower())
    if kind is None:
        return None
    words = " ".join(_tokens(name))
    if _PASSIVE.search(words) or _NOT_INVESTOR.search(words):
        return None
    return kind


def investor_key(kind: str, name: str) -> str:
    """Stable identity across filings. Individuals: sorted name tokens without honorifics and
    initials (filers reorder names and drop middle names). Mutual funds: the fund house (first
    word — schemes and AMC trustees file under many names). Entities: tokens without legal suffixes."""
    toks = _tokens(name)
    if kind == "individual":
        return "individual:" + " ".join(sorted(t for t in toks if len(t) > 1))
    if kind == "mf":
        return "mf:" + (toks[0] if toks else "")
    return f"{kind}:" + " ".join(t for t in toks if t not in _LEGAL)


def _same_holder(a: frozenset, b: frozenset) -> bool:
    """Loose match for 'was already there': one name's tokens contain the other's (>= 2 shared),
    so 'Rekha Jhunjhunwala' matches 'Rekha Rakesh Jhunjhunwala'."""
    if a == b:
        return bool(a)
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= big


def _loose(name: str) -> frozenset:
    return frozenset(t for t in _tokens(name) if len(t) > 1 and t not in _LEGAL)


def _quarter_index(q: str) -> int:
    d = pd.Timestamp(q)
    return d.year * 4 + (d.month - 1) // 3


def entry_events(holders: pd.DataFrame) -> pd.DataFrame:
    """One row per investor entry: symbol, quarter_end, entry_date (broadcast date), investor, kind,
    name, pct. Needs the filing immediately before (no gap) and no match in the previous
    LOOKBACK_QUARTERS filed quarters under any axis or name variant."""
    cols = ["symbol", "quarter_end", "entry_date", "investor", "kind", "name", "pct"]
    if holders.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for sym, g in holders.groupby("symbol"):
        filings = g[g["axis"] == FILING].drop_duplicates("quarter_end").sort_values("quarter_end")
        seen: dict[int, list[frozenset]] = {}
        for q, rows in g[g["axis"] != FILING].groupby("quarter_end"):
            seen[_quarter_index(q)] = [_loose(n) for n in rows["name"]]
        filed = {_quarter_index(q) for q in filings["quarter_end"]}
        for _, f in filings.iterrows():
            qi = _quarter_index(f["quarter_end"])
            if qi - 1 not in filed or not f["broadcast_at"]:
                continue
            broadcast = pd.Timestamp(f["broadcast_at"]).normalize()
            if (broadcast - pd.Timestamp(f["quarter_end"])).days > MAX_FILING_LAG_DAYS:
                continue
            prior = [n for k in range(qi - LOOKBACK_QUARTERS, qi) if k in filed for n in seen.get(k, [])]
            now = g[(g["quarter_end"] == f["quarter_end"]) & (g["axis"] != FILING)]
            for _, h in now.iterrows():
                kind = holder_kind(h["axis"], h["name"])
                if kind is None:
                    continue
                me = _loose(h["name"])
                if any(_same_holder(me, p) for p in prior):
                    continue
                out.append({"symbol": sym, "quarter_end": f["quarter_end"], "entry_date": broadcast,
                            "investor": investor_key(kind, h["name"]), "kind": kind, "name": h["name"],
                            "pct": h["pct"]})
    df = pd.DataFrame(out, columns=cols)
    # one investor may appear under two axes in the same filing (director + >2 lakh individual)
    return df.drop_duplicates(["symbol", "quarter_end", "investor"]).reset_index(drop=True)


# --- the walk-forward ranking -------------------------------------------------------------------

def rank_investors(events: pd.DataFrame, col: str, min_n: int = 3) -> pd.DataFrame:
    """Per investor with >= min_n scored events: n and score = median of `col` (fat tails: one
    multibagger must not make a 'skilled' investor). Sorted best first."""
    d = events.dropna(subset=[col])
    g = d.groupby("investor")[col].agg(n="count", score="median")
    return g[g["n"] >= min_n].sort_values(["score", "n"], ascending=[False, False])


def split_by_rank(ranks: pd.DataFrame, frac: float = 0.2) -> tuple[set, set]:
    """(top, bottom) investor sets: the best / worst `frac` of the ranked investors, >= 1 each."""
    k = max(1, int(len(ranks) * frac))
    order = ranks.sort_values("score", ascending=False).index
    return set(order[:k]), set(order[-k:])


def persistence(a: pd.Series, b: pd.Series) -> tuple[float | None, int]:
    """Spearman rank correlation of per-investor scores in two periods, over investors in both."""
    common = a.index.intersection(b.index)
    if len(common) < 3:
        return None, len(common)
    return float(a[common].rank().corr(b[common].rank())), len(common)

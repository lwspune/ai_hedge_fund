"""Customer-momentum PILOT (drift type): does a listed customer's big move predict its supplier's
return over the next days (Cohen-Frazzini "economic links", limited attention)?

Links: SEBI Reg 30 order-win filings ('Bagging/Receiving of orders/contracts', 2024-09 ->, the
standard format that names the customer); customer = scanner.links.awarding_entity matched to a
listed symbol (exact name or data/company_aliases.csv). A link is live for 365 days after its filing.
Event: a customer's abnormal return vs NIFTY 500 moves >= 5% on day t while a link is live. Supplier
returns are SIGNED by the shock (following the customer = positive); entry at the close of t+1 (the
shock is known after the close of t). Measured: supplier reaction on t (not tradable), +1/+5/+20.
Controls: INDUSTRY-ADJUSTED = supplier minus the median of its same-industry peers over the same
dates (sector momentum out); PLACEBO CUSTOMER = for each link, the same-industry peer of the customer
with the closest turnover and no link to the supplier - the supplier's return after ITS shocks.
Pre-specified cuts: link weight (order value / supplier revenue), shock direction, supplier size
(point-in-time market cap at the link). t clustered by shock date (one customer move hits every
linked supplier). Two years of links: no era cut (the pilot's pass unlocks the 2020 backfill).
PASS (fixed before the run): industry-adjusted mean at +5 or +20 >= +0.5% with clustered t >= 2 AND
>= 0.5% above the placebo's. Prices: cloud bhavcopy (unadjusted) + corporate-action guard.

    python scripts/validate_customer_momentum.py [--publish]
"""
from __future__ import annotations

import csv
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.eventstudy import summarize  # noqa: E402
from scanner.kpis import pdf_text  # noqa: E402
from scanner.links import (awarding_entity, is_withheld, linked_suppliers, load_aliases, match_listed,  # noqa: E402
                           name_index, shock_days)
from scanner.lockin import BLOCKING, blocking_action  # noqa: E402
from scanner.orderwins import revenue_before, size_bucket  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402
from scanner.pricestore import bar_panel, get_closes  # noqa: E402
from scanner.validation import exclude_results, run  # noqa: E402

START = "2024-09-01"
ORDER_CAT = "Bagging/Receiving of orders/contracts"
BENCH = "^CRSLDX"
SHOCK = 0.05
HORIZONS = (1, 5, 20)
LIVE_DAYS = 365
COST = 0.003
PASS_MEAN, PASS_T = 0.005, 2.0
CACHE = Path(__file__).resolve().parent.parent / "cache" / "links" / "awarding.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
      "Referer": "https://www.nseindia.com/"}


def extract(filings: list[dict]) -> dict[int, str]:
    """seq_id -> awarding entity ('' when absent); PDFs downloaded once per machine (cached)."""
    got: dict[int, str] = {}
    if CACHE.exists():
        with CACHE.open(encoding="utf-8", newline="") as fh:
            got = {int(r["seq_id"]): r["name"] for r in csv.DictReader(fh)}
    todo = [f for f in filings if f["seq_id"] not in got]
    print(f"{len(filings)} order filings, {len(todo)} PDFs to read", flush=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    new = not CACHE.exists()
    s = requests.Session()
    with CACHE.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["seq_id", "name"])
        if new:
            w.writeheader()
        for k, f in enumerate(todo, 1):
            name = ""
            try:
                r = s.get(f["attachment_url"], headers=UA, timeout=60)
                text, _ = pdf_text(r.content, max_pages=6) if r.ok else (None, 0)
                name = awarding_entity(text or "") or ""
            except requests.RequestException:
                pass
            got[f["seq_id"]] = name
            w.writerow({"seq_id": f["seq_id"], "name": name})
            if k % 250 == 0:
                fh.flush()
                print(f"  read {k}/{len(todo)}", flush=True)
            time.sleep(0.3)
    return got


def build_links(filings, names, index, values, hist) -> tuple[list[dict], pd.DataFrame]:
    links, audit = [], []
    for f in filings:
        n = names.get(f["seq_id"], "")
        sym = None
        if not n:
            status = "no_field"
        elif is_withheld(n):
            status = "withheld"
        else:
            sym = match_listed(n, index)
            status = "unmatched" if not sym else "self" if sym == f["symbol"] else "listed"
        audit.append({"seq_id": f["seq_id"], "supplier": f["symbol"], "disclosed_at": f["disclosed_at"],
                      "name": n, "status": status, "customer": sym if status == "listed" else None})
        if status == "listed":
            rev = revenue_before(hist.get(f["symbol"], []), f["disclosed_at"][:10])
            v = values.get(f["seq_id"])
            links.append({"supplier": f["symbol"], "customer": sym, "disclosed_at": f["disclosed_at"],
                          "seq_id": f["seq_id"], "name": n, "value_cr": v,
                          "weight": size_bucket(v / rev if v is not None and rev else None)})
    return links, pd.DataFrame(audit)


def returns(panel: dict, bench: pd.Series) -> tuple[pd.DataFrame, dict[int, pd.DataFrame], pd.DataFrame]:
    """Wide abnormal returns vs the benchmark: day-t reaction, and forward h from the close of t+1."""
    close = pd.DataFrame({s: df["close"] for s, df in panel.items()}).sort_index()
    turn = pd.DataFrame({s: df["turnover_lakh"] for s, df in panel.items()}).reindex(close.index)
    b = bench.reindex(close.index).ffill()
    react = close.pct_change(fill_method=None).sub(b.pct_change(), axis=0)
    fwd = {h: (close.shift(-(1 + h)) / close.shift(-1) - 1).sub(b.shift(-(1 + h)) / b.shift(-1) - 1, axis=0)
           for h in HORIZONS}
    return react, fwd, turn


def placebo_for(customer, supplier, cust_links, industry, ind_of, turn, at) -> str | None:
    """Same-industry peer of the customer with the closest 60-session turnover, unlinked to the supplier."""
    ind = ind_of.get(customer)
    if not ind:
        return None
    excluded = {customer, supplier} | cust_links.get(supplier, set())
    peers = [p for p in industry.get(ind, []) if p not in excluded and p in turn.columns]
    if not peers:
        return None
    hist = turn.loc[:at].tail(60)
    if customer not in hist.columns:
        return None
    med = hist[peers].median()
    target = hist[customer].median()
    if pd.isna(target) or med.dropna().empty:
        return None
    return (med.dropna() - target).abs().idxmin()


def _rows(kind, customer, supplier, t, sgn, react, fwd, industry, ind_of, meta) -> dict | None:
    if supplier not in react.columns or t not in react.index:
        return None
    row = {"kind": kind, "customer": customer, "symbol": supplier, "date": t.date().isoformat(),
           "sign": sgn, "reaction": sgn * react.at[t, supplier], **meta}
    peers = [p for p in industry.get(ind_of.get(supplier), []) if p != supplier and p in react.columns]
    for h in HORIZONS:
        v = fwd[h].at[t, supplier]
        row[f"h{h}"] = sgn * v if pd.notna(v) else None
        pm = fwd[h].loc[t, peers].median() if peers else float("nan")
        row[f"ind{h}"] = sgn * (v - pm) if pd.notna(v) and pd.notna(pm) else None
    return row


def build() -> dict[str, pd.DataFrame]:
    filings = db.select_all("filings", {"select": "seq_id,symbol,disclosed_at,attachment_url",
                                        "category": f"eq.{ORDER_CAT}", "disclosed_at": f"gte.{START}",
                                        "attachment_url": "not.is.null", "order": "disclosed_at"})
    names = extract(filings)
    cos = db.select_all("companies", {"select": "symbol,name,status,industry"})
    values = {k["seq_id"]: k["value_cr"] for k in db.select_all(
        "company_kpis", {"select": "seq_id,value_cr", "kpi": "eq.order_win_value"})}
    hist = {r["symbol"]: (r.get("history") or {}).get("annual") or []
            for r in db.select_all("company_snapshot", {"select": "symbol,history"})}
    links, audit = build_links(filings, names, name_index(cos, load_aliases()), values, hist)
    print("extraction:", dict(Counter(audit["status"])), flush=True)
    print(f"links {len(links)}: {len({l['supplier'] for l in links})} suppliers -> "
          f"{len({l['customer'] for l in links})} customers", flush=True)
    top = Counter(l["customer"] for l in links).most_common(12)
    print("top customers:", ", ".join(f"{c} {n}" for c, n in top), flush=True)
    print("\nAUDIT SAMPLE (hand-check): supplier -> customer | name as filed")
    for l in pd.DataFrame(links).sample(min(50, len(links)), random_state=1).to_dict("records"):
        print(f"  {l['supplier']:<12} -> {l['customer']:<12} | {l['name'][:80]}")

    ind_of = {c["symbol"]: c["industry"] for c in cos if c.get("industry") and c.get("status") == "listed"}
    industry: dict[str, list[str]] = {}
    for s, i in ind_of.items():
        industry.setdefault(i, []).append(s)
    today = date.today()
    panel = bar_panel("2024-06-01", today)
    panel = {s: df for s, df in panel.items() if s in ind_of}          # company universe (no ETFs)
    bench = get_closes(BENCH, "2024-06-01", today, source="db")
    react, fwd, turn = returns(panel, bench)
    acts = db.select_all("corporate_events", {"select": "symbol,event_type,event_date",
                                              "event_type": f"in.({','.join(sorted(BLOCKING))})",
                                              "event_date": "gte.2024-06-01"})
    by_sym: dict[str, list[dict]] = {}
    for a in acts:
        by_sym.setdefault(a["symbol"], []).append(a)
    blocked = lambda s, t, a, b: blocking_action(by_sym.get(s, []), s, t + pd.Timedelta(days=a),  # noqa: E731
                                                 t + pd.Timedelta(days=b))
    last_ok = react.index[-(HORIZONS[-1] + 3)]
    size = {s: mcap_bucket_at(s, date.fromisoformat(min(l["disclosed_at"][:10] for l in links if l["supplier"] == s)))
            for s in {l["supplier"] for l in links}}
    cust_links: dict[str, set] = {}
    by_cust: dict[str, list[dict]] = {}
    for l in links:
        cust_links.setdefault(l["supplier"], set()).add(l["customer"])
        by_cust.setdefault(l["customer"], []).append(l)

    def weight(sup, cust, t):
        live = [l for l in by_cust.get(cust, []) if l["supplier"] == sup and l["disclosed_at"][:10] < str(t.date())]
        return max(live, key=lambda l: l["disclosed_at"])["weight"] if live else "unknown"

    def shocks(sym):
        if sym not in react.columns:
            return []
        return [(t, g) for t, g in shock_days(react[sym], SHOCK)
                if pd.Timestamp(START) <= t <= last_ok and not blocked(sym, t, -5, 5)]

    out = []
    for cust, cl in by_cust.items():                                   # REAL links
        for t, g in shocks(cust):
            for sup in linked_suppliers(cl, cust, t, LIVE_DAYS):
                if blocked(sup, t, -5, 45):
                    continue
                r = _rows("real", cust, sup, t, g, react, fwd, industry, ind_of,
                          {"weight": weight(sup, cust, t), "size": size.get(sup, "unknown")})
                if r:
                    out.append(r)
    # first link per pair (later duplicates overwrite, so iterate newest -> oldest)
    pairs = {(l["supplier"], l["customer"]): l for l in sorted(links, key=lambda l: l["disclosed_at"], reverse=True)}
    for (sup, cust), first in pairs.items():                            # PLACEBO customers
        at = pd.Timestamp(first["disclosed_at"][:10])
        fake = placebo_for(cust, sup, cust_links, industry, ind_of, turn, at)
        if not fake:
            continue
        for t, g in shocks(fake):
            if sup in linked_suppliers(by_cust[cust], cust, t, LIVE_DAYS) and not blocked(sup, t, -5, 45):
                r = _rows("placebo", fake, sup, t, g, react, fwd, industry, ind_of,
                          {"weight": "n/a", "size": size.get(sup, "unknown"), "true_customer": cust})
                if r:
                    out.append(r)
    return {"results": pd.DataFrame(out), "links": pd.DataFrame(links), "extraction": audit}


def fmt(label: str, df: pd.DataFrame, col: str) -> str:
    d = df[[col, "date"]].dropna()
    s = summarize(d[col].tolist(), clusters=d["date"].tolist())
    if not s["n"]:
        return f"  {label:<34} n=    0"
    tc = f"{s['t_cluster']:+5.1f}" if s.get("t_cluster") is not None else "  n/a"
    return (f"  {label:<34} n={s['n']:>5} ({s['n_clusters']:>4} days)  mean={s['mean']*100:+6.2f}%  "
            f"median={s['median']*100:+6.2f}%  up={s['pct_positive']*100:4.0f}%  t_cl={tc}")


def report(df: pd.DataFrame) -> None:
    if df.empty:
        print("\nno events")
        return
    real, plac = df[df["kind"] == "real"], df[df["kind"] == "placebo"]
    print(f"\nevents: real {len(real)} ({real['customer'].nunique()} customers, {real['symbol'].nunique()} "
          f"suppliers, {real['date'].nunique()} shock days) | placebo {len(plac)}")
    print("\n=== SIGNED supplier return after its customer's >=5% move (following = +) ===")
    print(fmt("REAL reaction day t (not tradable)", real, "reaction"))
    for h in HORIZONS:
        print(fmt(f"REAL +{h}d vs NIFTY 500", real, f"h{h}"))
        print(fmt(f"REAL +{h}d industry-adjusted", real, f"ind{h}"))
        print(fmt(f"PLACEBO +{h}d industry-adjusted", plac, f"ind{h}"))
    print("\n=== SEGMENTS (pre-specified), industry-adjusted +5d | +20d ===")
    cuts = {**{f"weight {b}": real["weight"] == b for b in (">=25%", "5-25%", "<5%", "unknown")},
            "shock up": real["sign"] == 1, "shock down": real["sign"] == -1,
            "supplier small / small_mid": real["size"].isin(["small", "small_mid"]),
            "supplier mid / large": real["size"].isin(["mid", "large"])}
    for label, m in cuts.items():
        print(fmt(f"{label} [+5d]", real[m], "ind5"))
        print(fmt(f"{label} [+20d]", real[m], "ind20"))
    print(f"\nNet of costs: subtract ~{COST*100:.1f}% per round trip.")
    verdicts = []
    for h in (5, 20):
        r = real[[f"ind{h}", "date"]].dropna()
        s = summarize(r[f"ind{h}"].tolist(), clusters=r["date"].tolist())
        p = plac[f"ind{h}"].dropna()
        pm = float(p.mean()) if len(p) else 0.0
        ok = (s["n"] and s["mean"] >= PASS_MEAN and (s.get("t_cluster") or 0) >= PASS_T
              and s["mean"] - pm >= PASS_MEAN)
        verdicts.append(ok)
        print(f"PASS RULE +{h}d: mean {0 if not s['n'] else s['mean']*100:+.2f}% (>= +0.50), "
              f"t_cl {s.get('t_cluster') or 0:+.1f} (>= 2), vs placebo {pm*100:+.2f}% -> {'PASS' if ok else 'fail'}")
    print(f"PILOT: {'PASS -> backfill 2020' if any(verdicts) else 'FAIL -> null, stop'}")


def _study(args) -> dict:
    frames = build()
    frames["results"] = exclude_results(frames["results"], "date", args.exclude_results_window)
    report(frames["results"])
    return frames


if __name__ == "__main__":
    run("customer_momentum", _study)

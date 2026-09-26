"""Signal registry — every validated signal in one place, with its verdict.

The verdict metadata is the platform's honesty layer: the scanner never lets you
forget which signals carry real edge (buyback_arb) and which were falsified and
are kept only as informational lenses (mean_reversion, smart_money_deals).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

TYPES = {"structural", "drift", "spread"}
VERDICTS = {"edge", "conditional", "thin", "null"}
ROLES = {"primary", "lens", "watch", "documented"}


@dataclass(frozen=True)
class SignalMeta:
    name: str
    type: str
    verdict: str
    role: str
    summary: str


@dataclass(frozen=True)
class Signal:
    meta: SignalMeta
    run: Callable[..., str]


# --- run adapters (lazy imports: heavy/network deps only load when invoked) --

def _run_buyback(**kw) -> str:
    from scanner.buyback import scan_current_buybacks, format_buyback_table
    return format_buyback_table(scan_current_buybacks(start_id=kw.get("start_id")))


def _run_mean_reversion(**kw) -> str:
    from scanner.scan import DEFAULT_CFG, scan, format_table
    from scanner.universe import load_symbols, select_universe
    syms = select_universe(load_symbols(), include_financials=False)
    return format_table(scan(syms, DEFAULT_CFG))


def _run_deals(**kw) -> str:
    from scanner.deals import fetch_deals, aggregate_by_symbol
    from scanner.scan_deals import format_table
    ranked = aggregate_by_symbol(fetch_deals(), value_min=1e7)
    return format_table(ranked)


def _run_merger(**kw) -> str:
    return ("merger_arb is WATCH-only: stock-swap spreads on clean Indian large-cap "
            "deals are thin (~4-5% annualised gross) and efficiently priced; the real "
            "risk is the deal-break tail (Zee-Sony). Run scripts/validate_merger_arb.py "
            "to recompute on the verified deal set. No live screen.")


def _run_open_offer(**kw) -> str:
    return ("open_offer_arb is DOCUMENTED-null: SEBI open offers have no small-shareholder "
            "reservation (unlike buybacks), so acceptance is proportionate for everyone and "
            "the structural retail edge is absent. Not built; kept as the control that "
            "explains why buyback_arb works.")


def _run_index_rebalance(**kw) -> str:
    return ("index_rebalance is NULL: front-running NIFTY 50 / Next 50 reconstitution forced "
            "flows earns ~0 abnormal return (n=149 Next 50; tight effective-window flat). The "
            "change is publicly pre-announced ~4 weeks out, so the flow is arbitraged before a "
            "follower can act -- no barrier keeps competitors out (contrast the buyback quota). "
            "The lone deletion-rebound flicker was a 2021-22 regime artifact (gone by 2023-25). "
            "Run scripts/validate_index_rebalance.py + scripts/segment_index_rebalance.py.")


def _run_lockin(**kw) -> str:
    from datetime import date, timedelta
    from scanner import db
    from scanner.lockin import format_unlocks
    today, days = date.today(), int(kw.get("days") or 30)
    rows = db.select("corporate_events", {
        "select": "symbol,event_type,event_date,details",
        "event_type": "in.(anchor_lockin_30,anchor_lockin_90)",
        "and": f"(event_date.gte.{today},event_date.lte.{today + timedelta(days=days)})",
        "order": "event_date"})
    return ("Upcoming anchor unlocks (next %d days). Avoid buying into / consider exiting before "
            "T-1; the dip is T-1 -> T+2 (90d strongest). Not shortable (new IPOs are not in F&O).\n\n"
            % days) + format_unlocks(rows)


def _run_fno_ban(**kw) -> str:
    return ("fno_ban is NULL: stocks entering the NSE F&O ban (OI > 95% of MWPL) do not reverse "
            "their pre-ban move -- entry, during, exit and post windows are all ~0 and no better "
            "than same-stock control dates (n=920 episodes, 96 stocks, 2020-26). The ban only "
            "blocks new derivative positions; the cash market is open to all, so there is no "
            "barrier. The one clean effect (stocks sold into the ban keep falling during it) is "
            "unshortable. Run scripts/validate_fno_ban.py.")


def _run_rights_re(**kw) -> str:
    from scanner.rights import HURDLE, MIN_TURNOVER, format_open_res, open_res
    return (f"Rights entitlements trading now. gap = (S - issue - RE)/S; BUY RE when gap > "
            f"{HURDLE*100:.1f}% and RE turnover >= Rs {MIN_TURNOVER/1e5:.0f} L -- only if you want the "
            "stock anyway (then subscribe before the issue closes), or hold it and switch shares -> REs.\n\n"
            + format_open_res(open_res()))


def _run_promoter_buying(**kw) -> str:
    return ("promoter_buying is NULL (decayed): following promoter open-market buys from NSE SAST "
            "Reg 29 disclosures earned ~+5% median over 60d in 2020-23, but in 2024-26 big-stake and "
            "clustered buys return -1.0% / -1.6% median with fewer than half up. The pooled +8% mean "
            "is a small-cap fat tail. Recent promoter SELLS look negative (-5.8% median) but flip sign "
            "across eras -- a hypothesis to pre-register, not a finding. Run "
            "scripts/validate_promoter_buys.py.")


def _run_pref_lockin(**kw) -> str:
    return ("pref_lockin is NULL: preferential-allotment lock-in expiries (NSE listing XBRL, "
            "n=1,394 tranches 2023-26) do not dent the price. 6-month tranches: event T-1->T+2 "
            "-0.24% (t=-1.2) vs same-stock placebo -0.1/-0.2%; 18-month promoter tranches -0.63% "
            "(t=-2.1, inside costs) with no rebound (recovery T+2->T+20 ~0 or negative everywhere). "
            "Unlike anchor investors, pref allottees are strategic holders who are not forced to "
            "sell when the lock ends -- no forced flow, no effect. Run scripts/validate_pref_lockin.py.")


def _run_promoter_sells(**kw) -> str:
    return ("promoter_sells is NULL (era-unstable): after a promoter open-market sale cluster "
            "(NSE Reg 29, n=1,131, 2020-26) the +60d abnormal return is +0.0% pooled (t=0.0); "
            "2024-26 reads -4.0% (t=-4.6, 37% up) but 2022-23 read +4.7% (t=+3.1) -- the sign has "
            "flipped in every era, and same-stock placebo windows carry the same negative medians. "
            "No barrier, public disclosure. Run scripts/validate_promoter_sells.py.")


def _run_turn_of_month(**kw) -> str:
    return ("turn_of_month is NULL (control): the last-1 + first-3 trading-day window earned "
            "+0.34%/day on NIFTY 500 in 2022-23 (t=3.9) and +0.00%/day in 2024-26 (t=0.0); pooled "
            "+0.46%/month (t=1.8) is inside the era cut and an ETF round trip. Calendar effect, no "
            "barrier. Run scripts/validate_turn_of_month.py [--yf for 2007->].")


def _run_order_wins(**kw) -> str:
    return ("order_wins is NULL: disclosed order wins (NSE 'Bagging/Receiving of orders/contracts', "
            "2024-26, n=1,638 events) are priced on announcement day (+0.9% abnormal; +2.0% when the "
            "order is >=25% of the prior year's revenue). Entering the next day earns ~0 to slightly "
            "negative over 1/5/20 days, below same-stock controls. Public news, no barrier. Run "
            "scripts/validate_order_wins.py.")


def _run_ofs_retail(**kw) -> str:
    from datetime import date, timedelta
    from scanner import db
    from scanner.ofs import format_ofs_rows
    today = date.today()
    rows = db.select("ofs_events", {
        "select": "symbol,company,seller,floor_price,non_retail_date,retail_date,retail_shares,total_shares,pct_equity",
        "retail_date": f"gte.{today - timedelta(days=3)}", "order": "retail_date"})
    return ("OFS retail day (10% quota, bids <= Rs 2 lakh at or above the floor; shares land T+1). "
            "Measured 2025-26 (n=26 floors within 15% of the pre-close): T+1 close vs floor +1.9% median, "
            "69% up net of costs -- THIN, one era, and a cut-off above the floor is unrecorded. A watch, "
            "not a trade: bid at the floor only in a name you would hold anyway.\n\n" + format_ofs_rows(rows))


def _run_rating_change(**kw) -> str:
    """Informational: domestic long-term downgrades and negative watches of the last N days."""
    from datetime import date, timedelta
    from scanner import db
    days = int(kw.get("days") or 30)
    rows = db.select_all("credit_ratings", {
        "select": "symbol,agency,rating,prev_rating,watch,action,disclosed_at", "scale": "eq.domestic",
        "term": "eq.long", "or": "(action.eq.downgraded,and(action.eq.watch,watch.eq.negative))",
        "disclosed_at": f"gte.{date.today() - timedelta(days=days)}", "order": "disclosed_at.desc"})
    lines = [f"  {r['disclosed_at'][:10]}  {r['symbol']:<12} {r['agency']:<14} "
             f"{(r['prev_rating'] or '?') + ' -> ' if r['action'] == 'downgraded' else 'watch negative: '}"
             f"{r['rating']}" for r in rows]
    return ("rating_change is NULL: a credit-rating change is not tradeable. Downgrades (n=456, 2020-26) "
            "move -0.3% on announcement (t=-0.9) and drift nowhere after; the stock had already fallen "
            "(T-21->T-1 median -4.6%, same-stock placebo -3.2%) -- agencies follow the price. Upgrades' "
            "+0.6% reaction is ~+0.3% above reaffirmation / placebo controls, inside costs and shrinking. "
            "Run scripts/validate_rating_change.py.\n"
            f"Downgrades / negative watches, last {days} days:\n" + ("\n".join(lines) if lines else "  none"))


def _run_ipo_listing(**kw) -> str:
    """Live lens: IPOs not yet listed — issue price, latest GMP, retail subscription where published,
    estimated allotment odds, and the study's flags (<= 2x retail, GMP <= 0)."""
    from datetime import date
    from scanner import db
    from scanner.ipostudy import allot_prob, is_unit_trust
    rows = db.select_all("ipos", {"select": "chittorgarh_id,symbol,company,board,issue_close,listing_date,issue_price,"
                                            "sub_retail,retail_shares_offered,lot_size,applications",
                                  "listing_date": f"gte.{date.today()}", "order": "listing_date"})
    gmp: dict = {}
    for g in db.select_all("ipo_gmp", {"select": "chittorgarh_id,gmp_date,gmp",
                                        "chittorgarh_id": f"in.({','.join(str(r['chittorgarh_id']) for r in rows) or '0'})",
                                        "order": "gmp_date"}):
        gmp[g["chittorgarh_id"]] = float(g["gmp"])          # ascending: the last one wins
    lines = []
    for r in rows:
        if is_unit_trust(r.get("company")):
            continue
        issue, sub = float(r["issue_price"]), float(r["sub_retail"]) if r.get("sub_retail") else None
        g = gmp.get(r["chittorgarh_id"])
        p = allot_prob(r["board"], r.get("retail_shares_offered"), r.get("lot_size"), r.get("applications"), sub)
        flags = [f for f, on in (("<=2x retail", sub is not None and sub <= 2), ("GMP<=0", g is not None and g <= 0)) if on]
        lines.append(f"  {r['listing_date']}  {r['symbol']:<12} {r['board']:<9} issue {issue:>8.2f}  "
                     f"GMP {'   n/a' if g is None else f'{g / issue * 100:+5.1f}%'}  retail "
                     f"{'  n/a' if sub is None else f'{sub:5.1f}x'}  odds {'  n/a' if p is None else f'{p * 100:4.1f}%'}"
                     f"{'  [' + ', '.join(flags) + ']' if flags else ''}")
    return ("ipo_listing is THIN (watch): applying is a small positive lottery, not an edge worth capital. "
            "Mainboard (n=416, 2020-26): one application = P(allot) x listing gain = +1.6% (~Rs 237) pooled, "
            "but +0.2-0.3% (~Rs 34) in 2025-26. Skip <= 2x retail (55% list below issue); GMP before listing "
            "predicts the open (rho 0.87); don't buy after listing (median -10% vs NIFTY 500 at 1 year). "
            "Run scripts/validate_ipo.py.\nIPOs not yet listed:\n" + ("\n".join(lines) if lines else "  none"))


def _run_ipo_unlock(**kw) -> str:
    return ("ipo_unlock is NULL: buying a new listing at its 6-month pre-IPO lock-in expiry is not an entry. "
            "Mainboard (n~280 / 240): enter T+2, +125 sessions median -5.3% vs NIFTY 500 (43% up), +250 median "
            "-13.3% (34% up) -- the same as entering at month 3 (-13.7%) or month 9 (-14.0%): post-IPO drift runs "
            "~1.5 years. The unlock itself: -0.35% (t=-1.3). 'Buy after the fall' (below issue at T-1) is worse: "
            "+250 median -15.2% (29% up). SME medians -8.7% / -16.3%, -27% below issue. Lens: don't buy a new "
            "listing on weakness in its first 1.5 years. Run scripts/validate_ipo_unlock.py.")


def _run_demerger(**kw) -> str:
    """Informational: recent demerger record dates whose child may list soon, and children listed
    in the last 10 sessions (from the curated data/demerger_listings.csv)."""
    from datetime import date, timedelta
    from scanner import db
    from scanner.demerger import load_listings
    today, days = date.today(), int(kw.get("days") or 120)
    recent = db.select("corporate_events", {
        "select": "symbol,event_date", "event_type": "eq.demerger",
        "event_date": f"gte.{today - timedelta(days=days)}", "order": "event_date.desc"})
    mapped = {(r["parent"], r["ex_date"]): r for r in load_listings()}
    lines = [f"{r['event_date']}  {r['symbol']:<12} " + (
        f"child {mapped[(r['symbol'], r['event_date'])]['child']} listed {mapped[(r['symbol'], r['event_date'])]['listing_date']}"
        if (r["symbol"], r["event_date"]) in mapped else "child not yet in data/demerger_listings.csv")
        for r in recent]
    return ("Demerger listing flow: a newly listed demerged child falls a median ~6% vs NIFTY 500 over "
            "its first 5 sessions (n=64, 2019-26; t=-2.8 clustered; placebo windows flat) -- but the dip "
            "sits in small / non-index parents, not index-parent children, so it is not index-fund "
            "selling; it is unshortable (trade-for-trade, no F&O) and the buy-after-T+5 leg has a "
            "negative median (fat-tail mean). LENS: do not buy a demerged child in its first week; "
            f"no trade on the recovery.\n\nDemerger record dates, last {days} days:\n"
            + ("\n".join(lines) if lines else "  none"))


SIGNALS: dict[str, Signal] = {
    "buyback_arb": Signal(
        SignalMeta("buyback_arb", "structural", "conditional", "primary",
                   "Small-shareholder tender arb, entered at the last cum-entitlement close "
                   "(the record date is ex). Blind tendering loses ~2%; selected high-acceptance "
                   "tenders earn ~+3% gross = -3% after tax at a 30% slab, ~+1% at 20%, +8-9% "
                   "at a <=5% slab. Actionable only from a nil/5%-slab account, on selected "
                   "tenders. The one structural edge, narrow."),
        _run_buyback),
    "mean_reversion": Signal(
        SignalMeta("mean_reversion", "drift", "null", "lens",
                   "RSI + 20% below 200-DMA + quality. No edge vs buy-and-hold after "
                   "costs; informational lens only."),
        _run_mean_reversion),
    "smart_money_deals": Signal(
        SignalMeta("smart_money_deals", "drift", "null", "lens",
                   "Follow institutional bulk/block buys. Post-disclosure return ~0 "
                   "(front-run pre-event); informational lens only."),
        _run_deals),
    "merger_arb": Signal(
        SignalMeta("merger_arb", "spread", "thin", "watch",
                   "Stock-swap long-target/short-acquirer. Thin, efficiently priced; "
                   "deal-break tail risk."),
        _run_merger),
    "open_offer_arb": Signal(
        SignalMeta("open_offer_arb", "spread", "null", "documented",
                   "No small-shareholder reservation -> no structural edge. Control "
                   "that proves the buyback thesis."),
        _run_open_offer),
    "index_rebalance": Signal(
        SignalMeta("index_rebalance", "structural", "null", "lens",
                   "Front-run NIFTY 50/Next 50 reconstitution forced flows. Null: the "
                   "change is publicly pre-announced ~4wks out, so the flow is arbitraged "
                   "before a follower can act (n=149 Next 50; tight window flat; the lone "
                   "deletion-rebound was a 2021-22 regime artifact). Pre-announced forced "
                   "flow has no barrier keeping competitors out -- contrast the buyback quota."),
        _run_index_rebalance),
    "lockin_expiry": Signal(
        SignalMeta("lockin_expiry", "structural", "conditional", "lens",
                   "Anchor lock-in unlock dip: T-1->T+2 vs NIFTY 500 = -1.25% at the 90-day "
                   "unlock (t=-4.6, n=573), -0.7% at 30d; same-stock placebo windows ~0; holds "
                   "2022-26. Not shortable by retail (new IPOs aren't in F&O) -> use as an "
                   "avoid / exit-timing rule for recent IPOs, not a trade."),
        _run_lockin),
    "fno_ban": Signal(
        SignalMeta("fno_ban", "structural", "null", "lens",
                   "F&O ban (95% MWPL) reversal. Null: n=920 episodes 2020-26 -- the pre-ban move "
                   "does not reverse at entry, during, exit or after (all |t|<1, no better than "
                   "same-stock controls). The ban blocks fresh derivatives but the cash market stays "
                   "open to everyone, so nothing is fenced off. Real-looking effects (sold-into-ban "
                   "names keep falling during the ban) sit where retail can't short."),
        _run_fno_ban),
    "rights_re": Signal(
        SignalMeta("rights_re", "spread", "conditional", "watch",
                   "Rights entitlements trade below fair value S - issue price: median +3.5% of the "
                   "share price on liquid days (55 non-penny, fully-paid issues 2020-26, 291 days; "
                   "48/55 above cost). Capturable without shorting only if you want the stock (buy RE "
                   "+ subscribe instead) or hold it (switch shares -> REs). Small capacity."),
        _run_rights_re),
    "promoter_buying": Signal(
        SignalMeta("promoter_buying", "drift", "null", "lens",
                   "Follow promoter open-market buys (SAST Reg 29). Worked 2020-23 (+60d median "
                   "~+5%) but gone in 2024-26 (big stakes -1.0%, clusters -1.6%, <50% up); the "
                   "pooled +8% mean is a small-cap fat tail (median +0.9%). Decayed drift signal "
                   "-- informational lens only."),
        _run_promoter_buying),
    "order_wins": Signal(
        SignalMeta("order_wins", "drift", "null", "lens",
                   "Follow disclosed order wins (Reg 30). The market prices them on the day (+0.9%, "
                   "+2.0% for orders >=25% of revenue) and a follower gets nothing: +1/+5/+20d "
                   "abnormal ~0 to slightly negative, below same-stock controls (n=1,638, 2024-26). "
                   "Informational lens only."),
        _run_order_wins),
    "pref_lockin": Signal(
        SignalMeta("pref_lockin", "structural", "null", "documented",
                   "Preferential-allotment lock-in expiry (6m non-promoter / 18m promoter). "
                   "n=1,394: 6m event -0.24% (t=-1.2) = placebo; 18m -0.63% (t=-2.1, inside costs), "
                   "no recovery leg. Strategic allottees aren't forced sellers -- the anchor-unlock "
                   "mechanism needs a holder who must exit. Control for lockin_expiry."),
        _run_pref_lockin),
    "promoter_sells": Signal(
        SignalMeta("promoter_sells", "drift", "null", "lens",
                   "Exit/avoid after promoter open-market sales (Reg 29). Pre-registered, n=1,131: "
                   "+60d +0.0% pooled; -4.0% in 2024-26 (t=-4.6) but +4.7% in 2022-23 (t=+3.1) -- "
                   "sign flips every era, placebo medians match. Null; informational lens only."),
        _run_promoter_sells),
    "turn_of_month": Signal(
        SignalMeta("turn_of_month", "drift", "null", "documented",
                   "Turn-of-month seasonality (last 1 + first 3 trading days) on NIFTY 50 / 500. "
                   "A 2022-23 flicker (+0.34%/day, t=3.9) that is ~0 in 2024-26; pooled +0.46%/month "
                   "(t=1.8). Calendar control, documented not traded."),
        _run_turn_of_month),
    "ofs_retail": Signal(
        SignalMeta("ofs_retail", "structural", "thin", "watch",
                   "Offer-for-sale retail quota (10% reserved, bids <= Rs 2 lakh at/above the floor). "
                   "2025-26, n=26 floors within 15% of the pre-close: T+1 close vs floor +1.9% median "
                   "(+1.6% net, 69% up, t=2.3), PSU sellers +1.1%. Thin: one era, one-day capital, and "
                   "an oversubscribed book clears above the floor (cut-off unrecorded). Watch, not a trade."),
        _run_ofs_retail),
    "demerger_listing": Signal(
        SignalMeta("demerger_listing", "structural", "conditional", "lens",
                   "Newly listed demerged child: -5.9% median vs NIFTY 500 over its first 5 sessions "
                   "(n=64 children of 61 demergers, 2019-26; t=-2.8 clustered by scheme; same-child "
                   "placebo windows flat; -10% in 2022-23, -5.6% in 2024-26). The mechanism cut fails: "
                   "index-parent children -1.6% (n=13, n.s.), small/non-index parents carry it -- "
                   "holders dumping small allotments in trade-for-trade, not index funds. Unshortable "
                   "(T2T, no F&O); buy-after-T+5 median -0.9% (mean +8% is a fat tail). Lens: don't buy "
                   "a child in its first week; no recovery trade."),
        _run_demerger),
    "rating_change": Signal(
        SignalMeta("rating_change", "drift", "null", "lens",
                   "Credit-rating change (NSE Reg 30 rating filings, 2020-26). Downgrades n=456: "
                   "announcement -0.3% (t=-0.9), no drift after; the fall came before (T-21->T-1 median "
                   "-4.6% vs same-stock placebo -3.2%) -- agencies follow the price. Out-of-IG (58) and "
                   "defaults (31) n.s. Upgrades n=1,258: +0.6% reaction, ~+0.3% over reaffirmation / "
                   "placebo controls, inside costs, shrinking (2020-22 +0.9%, 2023-26 +0.4%). Informational "
                   "lens only."),
        _run_rating_change),
    "ipo_listing": Signal(
        SignalMeta("ipo_listing", "structural", "thin", "watch",
                   "Apply to IPOs via the retail quota (lottery of one minimum lot when oversubscribed). "
                   "Mainboard n=416 (2020-26): if allotted +9.8% median at the open (28% below issue); per "
                   "application P(allot) x gain = +1.6% (~Rs 237) pooled, +3.1% in 2023-24, +0.2-0.3% (~Rs 34) in "
                   "2025-26. Best at 2-10x retail (+3.5%); <= 2x loses (55% below issue); hot issues pay "
                   "+39% at ~2% odds. Pre-listing GMP predicts the open (rho 0.87 mainboard, 0.82 SME; GMP <= 0 -> "
                   "61% below issue); GMP at application time untestable before 2026 (forward capture on). "
                   "Buying after listing: mainboard null (median -10% at 1y), SME mean from fat tails (median -14%)."),
        _run_ipo_listing),
    "ipo_unlock": Signal(
        SignalMeta("ipo_unlock", "structural", "null", "lens",
                   "Enter a new listing after its 6-month pre-IPO lock-in expiry, hold 6-12 months (n=900 "
                   "unlocks, 2020-26). Mainboard: +125 median -5.3%, +250 median -13.3% vs NIFTY 500 (34% up) "
                   "-- no better than entering at month 3 or 9; the unlock day itself -0.35% (n.s.); stocks "
                   "below issue do worst (+250 median -15%). SME medians -9% / -16% (means are fat tails). "
                   "Lens: post-IPO underperformance runs ~1.5 years -- don't buy a new listing on weakness."),
        _run_ipo_unlock),
}


def get_signal(name: str) -> Signal:
    return SIGNALS[name]


def list_signals() -> list[SignalMeta]:
    return [s.meta for s in SIGNALS.values()]

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
            "flows earns ~0 abnormal return (n=151 Next 50; tight effective-window flat). The "
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


def _run_order_wins(**kw) -> str:
    return ("order_wins is NULL: disclosed order wins (NSE 'Bagging/Receiving of orders/contracts', "
            "2024-26, n=1,638 events) are priced on announcement day (+0.9% abnormal; +2.0% when the "
            "order is >=25% of the prior year's revenue). Entering the next day earns ~0 to slightly "
            "negative over 1/5/20 days, below same-stock controls. Public news, no barrier. Run "
            "scripts/validate_order_wins.py.")


SIGNALS: dict[str, Signal] = {
    "buyback_arb": Signal(
        SignalMeta("buyback_arb", "structural", "conditional", "primary",
                   "Small-shareholder tender arb; edge on selected high-acceptance, "
                   "high-premium small-caps. Post-Oct-2024 it needs a <=20% tax slab "
                   "(~0 after tax at 30%). The one validated edge."),
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
                   "before a follower can act (n=151 Next 50; tight window flat; the lone "
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
}


def get_signal(name: str) -> Signal:
    return SIGNALS[name]


def list_signals() -> list[SignalMeta]:
    return [s.meta for s in SIGNALS.values()]

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


SIGNALS: dict[str, Signal] = {
    "buyback_arb": Signal(
        SignalMeta("buyback_arb", "structural", "conditional", "primary",
                   "Small-shareholder tender arb; edge on selected high-acceptance, "
                   "high-premium small-caps. The one validated edge."),
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
}


def get_signal(name: str) -> Signal:
    return SIGNALS[name]


def list_signals() -> list[SignalMeta]:
    return [s.meta for s in SIGNALS.values()]

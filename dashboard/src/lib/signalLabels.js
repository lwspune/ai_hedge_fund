// Display copy for signals. signals.json (generated from scanner/catalog.py) stays the source of
// truth for verdict/type/role/summary; this only adds a human label and a one-line headline.
// When a signal is added to catalog.py, add its entry here too (signalLabels.test.js enforces it).

const SIGNALS = {
  buyback_arb: ['Buyback tender arbitrage', 'Small-shareholder quota; works at ≤ 20% tax slab, ~0 at 30%'],
  rights_re: ['Rights entitlement discount', 'REs trade ~3.5% below stock − issue price on liquid days'],
  lockin_expiry: ['Anchor lock-in unlock', '−1.25% dip T−1→T+2 at the 90-day unlock; not shortable'],
  merger_arb: ['Merger arbitrage', 'Thin (~4–5% annualised), efficiently priced, deal-break tail'],
  mean_reversion: ['Mean reversion', 'No edge vs buy-and-hold after costs'],
  smart_money_deals: ['Bulk/block deal following', 'Post-disclosure return ~0; front-run before disclosure'],
  open_offer_arb: ['Open offer arbitrage', 'No retail reservation → no structural edge (control case)'],
  index_rebalance: ['Index rebalance front-run', 'Pre-announced flow is arbitraged before you can act (n=151)'],
  fno_ban: ['F&O ban reversal', 'n=920 episodes, no reversal at any window'],
  promoter_buying: ['Promoter open-market buying', 'Worked 2020–23, gone 2024–26'],
  order_wins: ['Order wins', 'Priced on announcement day (+0.9%); follower +20d ≈ control'],
  turn_of_month: ['Turn-of-month seasonality', '2022–23 flicker (t=3.9), ~0 in 2024–26; calendar control'],
}

const ROLES = { primary: 'Trade', watch: 'Watch', lens: 'Lens', documented: 'Control' }
const TYPES = { structural: 'Structural', drift: 'Drift', spread: 'Spread' }

export const ROLE_ORDER = { primary: 0, watch: 1, lens: 2, documented: 3 }

export const signalLabel = (name) => SIGNALS[name]?.[0] ?? name
export const signalHeadline = (name) => SIGNALS[name]?.[1] ?? ''
export const roleLabel = (role) => ROLES[role] ?? role
export const typeLabel = (type) => TYPES[type] ?? type

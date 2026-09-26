// Display copy for signals. signals.json (generated from scanner/catalog.py) stays the source of
// truth for verdict/type/role/summary; this only adds a human label and a one-line headline.
// When a signal is added to catalog.py, add its entry here too (signalLabels.test.js enforces it).

const SIGNALS = {
  buyback_arb: ['Buyback tender arbitrage', 'Quota edge only at a ≤ 5% tax slab (thin at 20%); buy by the day before the record date'],
  rights_re: ['Rights entitlement discount', 'REs trade ~3.5% below stock − issue price on liquid days'],
  lockin_expiry: ['Anchor lock-in unlock', '−1.25% dip T−1→T+2 at the 90-day unlock; not shortable'],
  merger_arb: ['Merger arbitrage', 'Thin (~4–5% annualised), efficiently priced, deal-break tail'],
  mean_reversion: ['Mean reversion', 'No edge vs buy-and-hold after costs'],
  smart_money_deals: ['Bulk/block deal following', 'Post-disclosure return ~0; front-run before disclosure'],
  open_offer_arb: ['Open offer arbitrage', 'No retail reservation → no structural edge (control case)'],
  index_rebalance: ['Index rebalance front-run', 'Pre-announced flow is arbitraged before you can act (n=149)'],
  fno_ban: ['F&O ban reversal', 'n=920 episodes, no reversal at any window'],
  promoter_buying: ['Promoter open-market buying', 'Worked 2020–23, gone 2024–26'],
  order_wins: ['Order wins', 'Priced on announcement day (+0.9%); follower +20d ≈ control'],
  pref_lockin: ['Preferential lock-in expiry', '6m tranche = placebo; 18m −0.6% (t=−2.1), no rebound — allottees aren\'t forced sellers'],
  promoter_sells: ['Promoter open-market selling', '+60d ≈ 0 pooled; −4% in 2024–26 but +5% in 2022–23 (flips every era)'],
  ofs_retail: ['OFS retail quota', 'Floor bids +1.9% median by T+1 (n=26, 2025–26); thin, cut-off above floor unrecorded'],
  turn_of_month: ['Turn-of-month seasonality', '2022–23 flicker (t=3.9), ~0 in 2024–26; calendar control'],
  demerger_listing: ['Demerger listing flow', 'Child −5.9% median in its first 5 sessions (n=64); unshortable, no recovery trade'],
  ipo_listing: ['IPO retail application', 'Small positive lottery: +1.6% per application, ~₹34 in 2025–26; skip ≤ 2× subscribed'],
  consolidation: ['Consolidation breakout', 'Tight 40-day range breakouts: +60d median −1.7% (n=938); scan only'],
  ipo_unlock: ['IPO 6-month unlock entry', 'Buy after the pre-IPO unlock: −13% median over 12 months; month 6 is not a bottom'],
  rating_change: ['Credit rating change', 'Downgrades −0.3% on the day (n=456), fall came before; agencies follow the price'],
}

const ROLES = { primary: 'Trade', watch: 'Watch', lens: 'Lens', documented: 'Control' }
const TYPES = { structural: 'Structural', spread: 'Spread', drift: 'Drift', premium: 'Premium' }

export const ROLE_ORDER = { primary: 0, watch: 1, lens: 2, documented: 3 }

export const signalLabel = (name) => SIGNALS[name]?.[0] ?? name
export const signalHeadline = (name) => SIGNALS[name]?.[1] ?? ''
export const roleLabel = (role) => ROLES[role] ?? role
export const typeLabel = (type) => TYPES[type] ?? type

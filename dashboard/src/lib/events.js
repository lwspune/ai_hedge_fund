import { fmtInr, fmtQty } from './format'

export const EVENT_LABEL = {
  bonus: 'Bonus', split: 'Split', consolidation: 'Consolidation', rights: 'Rights',
  dividend: 'Dividend', buyback: 'Buyback', demerger: 'Demerger', fo_ban: 'F&O ban',
  ipo_listing: 'IPO listing', anchor_lockin_30: 'Anchor lock-in ends (50%)',
  anchor_lockin_90: 'Anchor lock-in ends (rest)',
}

export const eventLabel = (type) => EVENT_LABEL[type] || type

export function eventDetail(e) {
  const d = e.details || {}
  switch (e.event_type) {
    case 'bonus': return d.ratio || ''
    case 'split':
    case 'consolidation': return `Face value ${fmtInr(d.from_fv, 0)} → ${fmtInr(d.to_fv, 0)}`
    case 'rights': return [d.ratio, d.premium != null ? `${fmtInr(d.premium)} premium` : null].filter(Boolean).join(' at ')
    case 'dividend': return `${fmtInr(d.amount)} a share${d.special ? ' (incl. special)' : ''}${d.interim ? ' · interim' : ''}`
    case 'ipo_listing': return `Issue ${fmtInr(d.issue_price)} · ${d.board === 'sme' ? 'SME' : 'Mainboard'}`
    case 'anchor_lockin_30':
    case 'anchor_lockin_90': return d.anchor_shares ? `${fmtQty(d.anchor_shares)} anchor shares` : ''
    default: return ''
  }
}

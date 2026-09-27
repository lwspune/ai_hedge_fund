// Sections of the Learnings page, in display order. Entries live in src/learnings.json.
export const SECTIONS = [
  { key: 'thesis', title: 'Thesis', lede: 'Where edge survives in Indian equities, and the bar each kind of idea must clear.' },
  { key: 'method', title: 'Method', lede: 'How a signal earns trust. Most of these rules were paid for by a result that turned out wrong.' },
  { key: 'concepts', title: 'Concepts', lede: 'Quant ideas in plain language, with what each means for this platform.' },
  { key: 'data', title: 'Data', lede: 'What the free data stack taught us about bad data and silent failures.' },
  { key: 'declined', title: 'Declined, and why', lede: 'Ideas looked at and turned down, so they are not re-litigated without a new reason.' },
]

// Entries grouped by section (in SECTIONS order). Within a section the file order is kept — it is
// curated, most fundamental first. Unknown sections are dropped.
export function groupLearnings(rows) {
  return SECTIONS.map((s) => ({ ...s, items: rows.filter((r) => r.section === s.key) }))
}

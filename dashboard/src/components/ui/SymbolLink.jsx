import { companyHref } from '../../useHashRoute'

export default function SymbolLink({ symbol, name }) {
  if (!symbol) return name ? <span className="sym-name">{name}</span> : '—'
  return (
    <span className="sym-cell">
      <a className="sym" href={companyHref(symbol)}>{symbol}</a>
      {name && <span className="sym-name">{name}</span>}
    </span>
  )
}

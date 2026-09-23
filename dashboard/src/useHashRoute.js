import { useEffect, useState } from 'react'

// Minimal hash router (no dependency): '#/company/TCS' -> { page: 'company', symbol: 'TCS' }.
// Hash routes need no server rewrites, so the static Vercel deploy keeps working.
const SYMBOL = /^[A-Z0-9&.-]{1,20}$/

export function parseHash(hash) {
  const m = /^#\/company\/([^/?#]+)$/.exec(hash || '')
  if (m) {
    const symbol = decodeURIComponent(m[1]).toUpperCase()
    if (SYMBOL.test(symbol)) return { page: 'company', symbol }
  }
  return { page: 'home' }
}

export const companyHref = (symbol) => `#/company/${encodeURIComponent(symbol)}`

export default function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

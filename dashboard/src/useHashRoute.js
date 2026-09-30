import { useEffect, useRef, useState } from 'react'

// Minimal hash router (no dependency). Hash routes need no server rewrites, so the static
// Vercel deploy keeps working.
//   #/                       -> { page: 'desk' }
//   #/signals                -> { page: 'signals' }
//   #/market                 -> { page: 'market' }   (market regime)
//   #/learnings              -> { page: 'learnings' }
//   #/courses[/:course[/:module]] -> { page: 'courses', course, module } (bad slugs are dropped)
//   #/data[/tab]             -> { page: 'data', tab }
//   #/company/:symbol[/tab]  -> { page: 'company', symbol, tab }
const SYMBOL = /^[A-Z0-9&.-]{1,20}$/
const SLUG = /^[a-z0-9-]{1,60}$/

export const DATA_TABS = ['deals', 'buybacks', 'positions', 'scans']
export const COMPANY_TABS = ['overview', 'financials', 'events', 'risk', 'filings', 'deals']

const pickTab = (tab, tabs) => (tabs.includes(tab) ? tab : tabs[0])

function decode(s) {
  try {
    return decodeURIComponent(s)
  } catch {
    return null
  }
}

export function parseHash(hash) {
  const parts = (hash || '').replace(/^#\/?/, '').split('/').filter(Boolean)
  const [page, a, b] = parts
  if (page === 'signals' && parts.length === 1) return { page: 'signals' }
  if (page === 'market' && parts.length === 1) return { page: 'market' }
  if (page === 'learnings' && parts.length === 1) return { page: 'learnings' }
  if (page === 'courses' && parts.length <= 3) {
    if (!SLUG.test(a || '')) return { page: 'courses' }
    return SLUG.test(b || '') ? { page: 'courses', course: a, module: b } : { page: 'courses', course: a }
  }
  if (page === 'data' && parts.length <= 2) return { page: 'data', tab: pickTab(a, DATA_TABS) }
  if (page === 'company' && a && parts.length <= 3) {
    const symbol = decode(a)?.toUpperCase()
    if (symbol && SYMBOL.test(symbol)) return { page: 'company', symbol, tab: pickTab(b, COMPANY_TABS) }
  }
  return { page: 'desk' }
}

export const companyHref = (symbol, tab) =>
  `#/company/${encodeURIComponent(symbol)}${tab && tab !== COMPANY_TABS[0] ? `/${tab}` : ''}`

export const dataHref = (tab) => `#/data/${tab}`

export const courseHref = (course, module) => `#/courses/${course}${module ? `/${module}` : ''}`

export default function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  const prev = useRef(route)
  useEffect(() => {
    const onChange = () => {
      const next = parseHash(window.location.hash)
      const moved = next.page !== prev.current.page || next.symbol !== prev.current.symbol
        || next.course !== prev.current.course || next.module !== prev.current.module
      prev.current = next
      setRoute(next)
      if (moved) window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

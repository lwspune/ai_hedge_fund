// Tab bar as hash links (each tab is a route). Arrow keys / Home / End move focus between tabs;
// Enter follows the link as usual.
export default function Tabs({ label, tabs, active }) {
  function onKeyDown(e) {
    const links = [...e.currentTarget.querySelectorAll('a')]
    const i = links.indexOf(document.activeElement)
    if (i < 0) return
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: links.length - 1 }[e.key]
    if (next == null) return
    e.preventDefault()
    links[(next + links.length) % links.length].focus()
  }

  return (
    <nav className="tabs" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((t) => (
        <a key={t.id} href={t.href} aria-current={t.id === active ? 'page' : undefined}>
          {t.label}
          {t.count != null && <span className="tab-count">{t.count}</span>}
        </a>
      ))}
    </nav>
  )
}

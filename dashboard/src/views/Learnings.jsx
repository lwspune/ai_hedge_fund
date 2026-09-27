import learnings from '../learnings.json'
import signals from '../signals.json'
import { fmtDate } from '../lib/format'
import { groupLearnings } from '../lib/learnings'
import { signalLabel } from '../lib/signalLabels'
import Section from '../components/ui/Section'
import { VerdictBadge } from '../components/ui/Badge'

const GROUPS = groupLearnings(learnings)
const VERDICT = Object.fromEntries(signals.map((s) => [s.name, s.verdict]))

function Entry({ item }) {
  const hid = `learn-${item.id}`
  return (
    <article className="learn-card" aria-labelledby={hid}>
      <h3 id={hid} className="learn-title">{item.title}</h3>
      <p className="learn-body">{item.body}</p>
      <p className="learn-why"><span className="learn-why-label">Why it matters</span> {item.why}</p>
      {item.signals?.length > 0 && (
        <ul className="learn-signals" aria-label="Related signals">
          {item.signals.map((name) => (
            <li key={name}>
              <a href="#/signals">{signalLabel(name)}</a> <VerdictBadge verdict={VERDICT[name]} />
            </li>
          ))}
        </ul>
      )}
      <p className="learn-meta">Learned {fmtDate(item.learned)} · {item.source}</p>
    </article>
  )
}

export default function Learnings() {
  return (
    <>
      <h1 className="page-title">Learnings</h1>
      <p className="page-lede">
        What testing {signals.length} signals has taught, in one place. Per-signal verdicts and evidence live on
        the <a href="#/signals">Signals</a> page.
      </p>
      <nav className="learn-toc" aria-label="Learnings sections">
        {GROUPS.map((g) => (
          <a key={g.key} href="#/learnings" onClick={(e) => {
            e.preventDefault()
            const el = document.getElementById(`learn-sec-${g.key}`)
            el?.focus({ preventScroll: true })
            el?.scrollIntoView({ block: 'start' })
          }}>
            {g.title} <span className="learn-count">{g.items.length}</span>
          </a>
        ))}
      </nav>
      {GROUPS.map((g) => (
        <div key={g.key} id={`learn-sec-${g.key}`} className="learn-section" tabIndex={-1}>
          <Section id={`learn-sec-${g.key}`} title={g.title}>
            <p className="learn-lede">{g.lede}</p>
            <div className="learn-grid">
              {g.items.map((item) => <Entry key={item.id} item={item} />)}
            </div>
          </Section>
        </div>
      ))}
    </>
  )
}

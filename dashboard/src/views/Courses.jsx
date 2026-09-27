import { useState } from 'react'
import courses from '../courses.json'
import learnings from '../learnings.json'
import { fmtDate } from '../lib/format'
import { findCourse, moduleNav, progressPct, readyModules, reviewDue, toggleDone } from '../lib/courses'
import { signalLabel } from '../lib/signalLabels'
import { courseHref } from '../useHashRoute'
import { Badge } from '../components/ui/Badge'
import Button from '../components/ui/Button'

const LEARNING = Object.fromEntries(learnings.map((l) => [l.id, l]))

// "Done" ticks are a per-browser convenience; storage can be missing or throw (private mode).
const storeKey = (courseId) => `course-done:${courseId}`
function readDone(courseId) {
  try {
    const v = JSON.parse(window.localStorage.getItem(storeKey(courseId)) || '[]')
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}
function useDone(courseId) {
  const [done, setDone] = useState(() => readDone(courseId))
  const toggle = (id) => setDone((d) => {
    const next = toggleDone(d, id)
    try {
      window.localStorage.setItem(storeKey(courseId), JSON.stringify(next))
    } catch {
      // storage unavailable: the tick lasts for this visit only
    }
    return next
  })
  return [done, toggle]
}

function Progress({ pct, label }) {
  return (
    <div className="course-progress">
      <div className="course-bar" role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="t2">{pct}% done</span>
    </div>
  )
}

function ReviewNote({ course }) {
  const due = reviewDue(course)
  return (
    <p className={`course-review${due ? ' tone-warn' : ''}`}>
      Facts last checked {fmtDate(course.reviewed)}{due ? ' — due for a re-check: rules and rates may have changed.' : '.'}
    </p>
  )
}

function CourseList() {
  return (
    <>
      <h1 className="page-title">Courses</h1>
      <p className="page-lede">Practical paths through the ideas behind this platform. Every module ends with something you build or measure.</p>
      <div className="learn-grid stack-top">
        {courses.map((c) => (
          <article key={c.id} className="learn-card">
            <h2 className="learn-title"><a href={courseHref(c.id)}>{c.title}</a></h2>
            <p className="learn-body">{c.summary}</p>
            <p className="learn-meta">{readyModules(c).length} of {c.modules.length} modules ready · checked {fmtDate(c.reviewed)}</p>
          </article>
        ))}
      </div>
    </>
  )
}

function CourseOverview({ course }) {
  const [done, toggle] = useDone(course.id)
  const pct = progressPct(course, done)
  return (
    <>
      <p className="crumbs"><a href="#/courses">Courses</a></p>
      <h1 className="page-title">{course.title}</h1>
      <p className="page-lede">{course.summary}</p>
      <Progress pct={pct} label={`${course.title} progress`} />
      <ReviewNote course={course} />
      {course.levels.map((lvl) => {
        const mods = course.modules.filter((m) => m.level === lvl.key)
        if (!mods.length) return null
        return (
          <section key={lvl.key} className="section" aria-labelledby={`lvl-${lvl.key}`}>
            <h2 id={`lvl-${lvl.key}`} className="section-title">{lvl.title}</h2>
            <p className="learn-lede">{lvl.lede}</p>
            <ol className="course-modules">
              {mods.map((m) => {
                const n = course.modules.indexOf(m) + 1
                const isDone = done.includes(m.id)
                return (
                  <li key={m.id} className={`course-mod${m.status === 'planned' ? ' is-planned' : ''}`}>
                    <span className="course-num mono" aria-hidden="true">{String(n).padStart(2, '0')}</span>
                    <span className="course-mod-main">
                      {m.status === 'ready'
                        ? <a href={courseHref(course.id, m.id)}>{m.title}</a>
                        : <span className="t2">{m.title}</span>}
                      <span className="cell-sub">
                        {m.status === 'ready' ? `${m.minutes} min + exercise` : 'Coming next'}
                      </span>
                    </span>
                    {m.status === 'ready' && (
                      <Button size="sm" variant={isDone ? 'primary' : 'ghost'} aria-pressed={isDone}
                              aria-label={`Mark "${m.title}" as ${isDone ? 'not done' : 'done'}`} onClick={() => toggle(m.id)}>
                        {isDone ? 'Done ✓' : 'Mark done'}
                      </Button>
                    )}
                  </li>
                )
              })}
            </ol>
          </section>
        )
      })}
    </>
  )
}

function Lesson({ course, mod }) {
  const [done, toggle] = useDone(course.id)
  const { prev, next } = moduleNav(course, mod.id)
  const title = (id) => course.modules.find((m) => m.id === id)?.title
  const level = course.levels.find((l) => l.key === mod.level)
  const isDone = done.includes(mod.id)
  return (
    <article className="lesson">
      <p className="crumbs">
        <a href="#/courses">Courses</a> / <a href={courseHref(course.id)}>{course.title}</a>
      </p>
      <h1 className="page-title">{mod.title}</h1>
      <p className="lesson-meta"><Badge>{level?.title}</Badge> <span className="t2">{mod.minutes} min read + exercise</span></p>

      <h2 className="subhead">What you'll learn</h2>
      <ul className="lesson-list">{mod.goals.map((g) => <li key={g}>{g}</li>)}</ul>

      <h2 className="subhead">The lesson</h2>
      {mod.lesson.map((p) => <p key={p.slice(0, 40)} className="lesson-p">{p}</p>)}

      {mod.india?.length > 0 && (
        <>
          <h2 className="subhead">India specifics</h2>
          <ul className="lesson-facts">
            {mod.india.map((f) => (
              <li key={f.text}>
                {f.text}{' '}
                <span className="cell-sub">
                  As of {fmtDate(f.asOf)} · {f.url
                    ? <a href={f.url} target="_blank" rel="noopener noreferrer">{f.source}</a>
                    : f.source}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <section className="lesson-try" aria-labelledby="try-h">
        <h2 id="try-h" className="subhead">Try it</h2>
        <ol className="lesson-list">{mod.tryIt.steps.map((s) => <li key={s}>{s}</li>)}</ol>
        {mod.tryIt.code && <pre className="lesson-code"><code>{mod.tryIt.code.join('\n')}</code></pre>}
        <p className="lesson-deliverable"><strong>Deliverable:</strong> {mod.tryIt.deliverable}</p>
      </section>

      <h2 className="subhead">Check yourself</h2>
      {mod.check.map((c) => (
        <details key={c.q} className="lesson-check">
          <summary>{c.q}</summary>
          <p>{c.a}</p>
        </details>
      ))}

      {(mod.deeper?.length > 0 || mod.learnings?.length > 0 || mod.signals?.length > 0) && (
        <>
          <h2 className="subhead">Go deeper</h2>
          <ul className="lesson-list">
            {(mod.deeper || []).map((d) => (
              <li key={d.title}>{d.url ? <a href={d.url} target="_blank" rel="noopener noreferrer">{d.title}</a> : d.title}</li>
            ))}
            {(mod.learnings || []).map((id) => <li key={id}>Learning: <a href="#/learnings">{LEARNING[id].title}</a></li>)}
            {(mod.signals || []).map((s) => <li key={s}>Signal: <a href="#/signals">{signalLabel(s)}</a></li>)}
          </ul>
        </>
      )}

      <div className="lesson-foot">
        <Button variant={isDone ? 'primary' : 'ghost'} aria-pressed={isDone} onClick={() => toggle(mod.id)}>
          {isDone ? 'Done ✓' : 'Mark done'}
        </Button>
        <nav className="lesson-nav" aria-label="Lesson navigation">
          {prev && <a href={courseHref(course.id, prev)}>← {title(prev)}</a>}
          {next && <a href={courseHref(course.id, next)}>{title(next)} →</a>}
        </nav>
      </div>
    </article>
  )
}

export default function Courses({ course: courseId, module: moduleId }) {
  const course = courseId && findCourse(courses, courseId)
  if (!course) return <CourseList />
  const mod = moduleId && course.modules.find((m) => m.id === moduleId && m.status === 'ready')
  return mod ? <Lesson key={mod.id} course={course} mod={mod} /> : <CourseOverview course={course} />
}

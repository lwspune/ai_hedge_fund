// Pure helpers for the Courses page. Content lives in src/courses.json; a module is either
// 'ready' (written) or 'planned' (outline only — listed, not openable).
const DAY = 86_400_000

export const findCourse = (courses, id) => courses.find((c) => c.id === id)

export const readyModules = (course) => course.modules.filter((m) => m.status === 'ready')

export function moduleNav(course, id) {
  const ids = readyModules(course).map((m) => m.id)
  const i = ids.indexOf(id)
  return { prev: i > 0 ? ids[i - 1] : null, next: i >= 0 && i < ids.length - 1 ? ids[i + 1] : null }
}

// A course states when its facts were last checked; after reviewEveryDays it asks for a re-check.
export function reviewDue(course, today = new Date()) {
  const due = new Date(`${course.reviewed}T00:00:00Z`).getTime() + course.reviewEveryDays * DAY
  return today.getTime() >= due
}

export function progressPct(course, done) {
  const ready = readyModules(course)
  if (!ready.length) return 0
  const doneSet = new Set(done)
  return Math.round((100 * ready.filter((m) => doneSet.has(m.id)).length) / ready.length)
}

export const toggleDone = (done, id) => (done.includes(id) ? done.filter((d) => d !== id) : [...done, id])

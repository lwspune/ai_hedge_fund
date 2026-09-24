import InfoPopover from './InfoPopover'

// A section = heading row (title, optional meta caption, ⓘ note and right-aligned action) and
// content. No panel box. `status` is the one-line result of the last action (role="status").
export default function Section({ id, title, meta, info, infoHref, action, status, children }) {
  const hid = `${id}-h`
  return (
    <section className="section" aria-labelledby={hid}>
      <div className="section-head">
        <h2 id={hid} className="section-title">{title}</h2>
        {info && (
          <InfoPopover label={`About ${title}`}>
            {info}
            {infoHref && <> <a href={infoHref}>See evidence</a></>}
          </InfoPopover>
        )}
        {meta && <span className="section-meta">{meta}</span>}
        {action && <div className="section-action">{action}</div>}
      </div>
      <p className="section-status" role="status">{status || ''}</p>
      {children}
    </section>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {hint && <p className="empty-hint">{hint}</p>}
    </div>
  )
}

export function ErrorNote({ what, message }) {
  return (
    <div className="error-note" role="alert">
      Couldn’t load {what}.
      {message && <span className="error-raw">{message}</span>}
    </div>
  )
}

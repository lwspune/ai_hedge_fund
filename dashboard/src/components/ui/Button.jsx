export default function Button({ variant = 'ghost', size, busy = false, children, ...rest }) {
  return (
    <button type="button" className={`btn btn-${variant}${size === 'sm' ? ' btn-sm' : ''}`}
            disabled={busy || rest.disabled} aria-busy={busy || undefined} {...rest}>
      {busy && <span className="spin" aria-hidden="true">◌</span>}
      {children}
    </button>
  )
}

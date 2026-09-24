import { useEffect, useId, useRef, useState } from 'react'

// ⓘ button that toggles a one-sentence methodology note. Escape or a click outside closes it;
// Escape returns focus to the button.
export default function InfoPopover({ label, icon, align = 'left', children }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const btn = useRef(null)
  const wrap = useRef(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setOpen(false)
        btn.current?.focus()
      }
    }
    const onDown = (e) => { if (!wrap.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  return (
    <span className="info" ref={wrap}>
      <button ref={btn} type="button" className="info-btn" aria-label={label}
              aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        {icon || (
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
            <path d="M8 7v4.2M8 4.8v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        )}
      </button>
      <span id={id} className={`info-pop info-pop-${align}`} role="note" hidden={!open}>{children}</span>
    </span>
  )
}

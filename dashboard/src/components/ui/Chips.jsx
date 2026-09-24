// Toggle chips for client-side filters. None pressed = no filter.
export default function Chips({ label, options, selected, onToggle }) {
  return (
    <span className="chip-group" role="group" aria-label={label}>
      {options.map(([value, text]) => (
        <button key={value} type="button" className="chip" aria-pressed={selected.has(value)}
                onClick={() => onToggle(value)}>
          {text}
        </button>
      ))}
    </span>
  )
}

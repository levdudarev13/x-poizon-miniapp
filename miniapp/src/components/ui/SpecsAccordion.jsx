function getRowKey(row, index) {
  if (row?.id != null) return row.id
  if (row?.key) return `${row.key}-${index}`
  if (row?.label) return `${row.label}-${index}`
  return index
}

function resolveRow(row) {
  return {
    label: row?.label ?? row?.key ?? '',
    value: row?.value ?? '',
  }
}

export default function SpecsAccordion({
  title = 'О товаре',
  open,
  onToggle,
  rows = [],
  icon = null,
}) {
  return (
    <section className="ui-specs ui-surface-panel">
      <button type="button" className="ui-specs__toggle pressable" aria-expanded={open} onClick={onToggle}>
        <span className="ui-specs__toggle-left">
          {icon}
          <span>{title}</span>
        </span>

        <svg
          className={`ui-specs__arrow${open ? ' open' : ''}`}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M6 9l6 6 6-6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open ? (
        <div className="ui-specs__rows">
          {rows.map((row, index) => {
            const resolved = resolveRow(row)

            return (
              <div key={getRowKey(row, index)} className="ui-specs__row">
                <span className="ui-specs__key">{resolved.label}</span>
                <span className="ui-specs__value">{resolved.value}</span>
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

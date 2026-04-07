import { repairMojibakeText } from '../../utils/text.js'

function getRowKey(row, index) {
  if (row?.id != null) return row.id
  if (row?.label) return `${row.label}-${index}`
  return index
}

export default function PriceBreakdown({
  title = 'Состав цены',
  rows = [],
  totalLabel = 'Итого',
  totalAmount,
}) {
  return (
    <section className="ui-breakdown ui-surface-panel">
      <h3 className="ui-breakdown__title">{repairMojibakeText(title)}</h3>

      {rows.map((row, index) => (
        <div key={getRowKey(row, index)} className="ui-breakdown__row">
          <div className="ui-breakdown__left">
            <span className="ui-breakdown__label">{repairMojibakeText(row.label)}</span>
            {row.note && (typeof row.showNote === 'boolean' ? row.showNote : index === 0) ? (
              <span className="ui-breakdown__note">{repairMojibakeText(row.note)}</span>
            ) : null}
          </div>
          <span className="ui-breakdown__amount">{row.amount}</span>
        </div>
      ))}

      <div className="ui-breakdown__divider" />

      <div className="ui-breakdown__row ui-breakdown__row--total">
        <div className="ui-breakdown__left">
          <span className="ui-breakdown__label">{repairMojibakeText(totalLabel)}</span>
        </div>
        <span className="ui-breakdown__amount">{totalAmount}</span>
      </div>
    </section>
  )
}

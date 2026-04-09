import LoadingGlyph from './LoadingGlyph'

export default function StateSurface({
  eyebrow = '',
  icon,
  title,
  body,
  children,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  tone = 'neutral',
  compact = false,
}) {
  const isProgress = tone === 'progress'
  const hasPrimaryAction = Boolean(actionLabel && onAction)
  const hasSecondaryAction = Boolean(secondaryActionLabel && onSecondaryAction)

  return (
    <div className="ui-state ui-surface-panel" data-tone={tone} data-compact={compact}>
      {isProgress ? (
        <LoadingGlyph
          className="ui-state__loading"
          icon={icon}
          size={compact ? 'sm' : 'md'}
        />
      ) : icon ? <div className="ui-state__icon" aria-hidden="true">{icon}</div> : null}
      {eyebrow ? <p className="ui-state__eyebrow">{eyebrow}</p> : null}
      {title ? <h2 className="ui-state__title">{title}</h2> : null}
      {body ? <p className="ui-state__body">{body}</p> : null}
      {children}
      {hasSecondaryAction ? (
        <div className="ui-state__actions">
          {hasPrimaryAction ? (
            <button type="button" className="ui-state__action pressable" onClick={onAction}>
              {actionLabel}
            </button>
          ) : null}
          <button
            type="button"
            className="ui-state__action ui-state__action--secondary pressable"
            onClick={onSecondaryAction}
          >
            {secondaryActionLabel}
          </button>
        </div>
      ) : hasPrimaryAction ? (
        <button type="button" className="ui-state__action pressable" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}

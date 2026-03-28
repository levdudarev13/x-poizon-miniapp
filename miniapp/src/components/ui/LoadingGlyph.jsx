function DefaultLoadingIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path d="M21 12a9 9 0 1 1-2.64-6.36" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M21 4v6h-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function LoadingGlyph({
  icon,
  size = 'md',
  className = '',
  progress = true,
}) {
  const classes = ['ui-loading', `ui-loading--${size}`]

  if (className) {
    classes.push(className)
  }

  return (
    <div className={classes.join(' ')} aria-hidden="true">
      <div className="ui-loading__halo" />
      <div className="ui-loading__core">
        <div className="ui-loading__ring ui-loading__ring--outer" />
        <div className="ui-loading__ring ui-loading__ring--accent" />
        <div className="ui-loading__icon">
          {icon || <DefaultLoadingIcon />}
        </div>
      </div>

      {progress ? (
        <div className="ui-loading__progress">
          <div className="ui-loading__track">
            <div className="ui-loading__bar" />
          </div>

          <div className="ui-loading__dots">
            <span />
            <span />
            <span />
          </div>
        </div>
      ) : null}
    </div>
  )
}

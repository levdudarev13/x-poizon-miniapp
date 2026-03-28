export function AdminSectionShell({
  topbar = null,
  hero = null,
  stats = null,
  notice = null,
  children,
  contentClassName = '',
  ...props
}) {
  const nextClassName = ['admin-section-shell__content', contentClassName].filter(Boolean).join(' ')
  return (
    <div className="admin-shell admin-section-shell" {...props}>
      {topbar}
      {hero}
      {notice}
      {stats}
      <div className={nextClassName}>{children}</div>
    </div>
  )
}

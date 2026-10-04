export default function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <section className="detail-card empty-state-card oi-empty-state">
      <div className="empty-state-icon" aria-hidden="true">∅</div>
      <h2>{title}</h2>
      <p>{description}</p>
      {actionLabel && onAction && (
        <div className="empty-state-actions">
          <button className="primary-action" type="button" onClick={onAction}>{actionLabel}</button>
        </div>
      )}
    </section>
  )
}

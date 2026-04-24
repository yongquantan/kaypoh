export default function HonestyCard({ score }) {
  const hasScore = score && typeof score.score === 'number'
  const value = hasScore ? score.score : null

  let verdictLabel = 'Awaiting Audit'
  let cardClass = 'score-card warning-card'
  if (hasScore) {
    if (value >= 80) {
      verdictLabel = 'Highly Defensible'
      cardClass = 'score-card'
    } else if (value >= 50) {
      verdictLabel = 'Needs Verification'
      cardClass = 'score-card warning-card'
    } else {
      verdictLabel = 'Fails Audit'
      cardClass = 'score-card warning-card'
    }
  }

  return (
    <div className={cardClass}>
      <span>Honesty Index</span>
      <strong>
        {hasScore ? value : '—'}
        <small>/100</small>
      </strong>
      <em>{verdictLabel}</em>
    </div>
  )
}

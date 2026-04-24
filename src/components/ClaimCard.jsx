import { MagnifyingGlass, WarningCircle } from '@phosphor-icons/react'

// Map our frozen verdict enum to the existing stamp classes in App.css:
// stamp-true / stamp-warn / stamp-false
const VERDICT_TO_STAMP = {
  true: { stamp: 'true', label: 'Verified True' },
  overstated: { stamp: 'warn', label: 'Overstated' },
  misleading: { stamp: 'warn', label: 'Misleading' },
  false: { stamp: 'false', label: 'False / Misleading' },
  unverifiable: { stamp: 'warn', label: 'Unverifiable' },
}

function VerdictStamp({ type, children }) {
  return <span className={`verdict-stamp stamp-${type}`}>{children}</span>
}

function PendingStamp() {
  return (
    <span className="verdict-stamp stamp-warn pending-stamp">Auditing…</span>
  )
}

export default function ClaimCard({ index, claim, verdict }) {
  const hasVerdict = !!verdict
  const mapped = hasVerdict ? VERDICT_TO_STAMP[verdict.verdict] : null
  const isFalse = mapped?.stamp === 'false'

  const idLabel = String(index + 1).padStart(2, '0')

  return (
    <article
      className={`claim-card theme-panel theme-border ${isFalse ? 'is-false' : ''} ${
        hasVerdict ? '' : 'is-pending'
      }`}
    >
      {isFalse && <WarningCircle weight="fill" className="claim-watermark" />}
      <div className="claim-header">
        <div>
          <span>Listing Claim {idLabel}</span>
          <p>"{claim.raw_text}"</p>
        </div>
        {hasVerdict ? (
          mapped ? (
            <VerdictStamp type={mapped.stamp}>{mapped.label}</VerdictStamp>
          ) : (
            // Unknown verdict type — render plain text, no stamp.
            <span className="verdict-plain">{verdict.verdict}</span>
          )
        ) : (
          <PendingStamp />
        )}
      </div>
      <div className="claim-body">
        <MagnifyingGlass />
        <div>
          <span>GrabMaps Intel</span>
          <p>
            {hasVerdict
              ? verdict.finding || '—'
              : 'Awaiting verification against GrabMaps evidence…'}
          </p>
        </div>
      </div>
    </article>
  )
}

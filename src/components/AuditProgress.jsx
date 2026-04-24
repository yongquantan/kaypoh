/**
 * AuditProgress
 *
 * Compact progress strip shown while an audit is running:
 *   • Spinner + current phase label
 *   • Phase chain (scraping → extracting → geocoding → auditing → scoring)
 *   • Per-claim progress bar with "Verifying 3 / 8 · quiet · quiet residential road"
 *
 * Consumes `phase` and `progress` from useAuditStream.
 */
import { CircleNotch, CheckCircle } from '@phosphor-icons/react'

const PHASES = [
  { id: 'scraping', label: 'Scrape' },
  { id: 'extracting', label: 'Extract' },
  { id: 'geocoding', label: 'Geocode' },
  { id: 'auditing', label: 'Audit' },
  { id: 'scoring', label: 'Score' },
]

function phaseState(phaseId, current, status) {
  if (!current && status !== 'done') return 'pending'
  const curIdx = PHASES.findIndex((p) => p.id === current)
  const thisIdx = PHASES.findIndex((p) => p.id === phaseId)
  if (status === 'done' && thisIdx <= PHASES.length - 1) return 'done'
  if (thisIdx < curIdx) return 'done'
  if (thisIdx === curIdx) return 'active'
  return 'pending'
}

export default function AuditProgress({ status, phase, progress }) {
  if (status === 'idle') return null

  const busy = status === 'streaming'
  const percent = progress?.total ? (progress.current / progress.total) * 100 : 0

  return (
    <section className="audit-progress theme-panel theme-border" aria-live="polite">
      <div className="audit-progress-head">
        <span className={`audit-spinner ${busy ? 'spinning' : 'done'}`}>
          {busy ? <CircleNotch weight="bold" /> : <CheckCircle weight="fill" />}
        </span>
        <span className="audit-progress-label">
          {busy
            ? phase
              ? `Phase: ${phase}`
              : 'Starting…'
            : status === 'done'
              ? 'Audit complete'
              : status === 'error'
                ? 'Audit errored'
                : 'Audit cancelled'}
        </span>
      </div>

      <ol className="phase-chain" aria-label="Audit phase chain">
        {PHASES.map((p) => {
          const s = phaseState(p.id, phase, status)
          return (
            <li key={p.id} className={`phase phase-${s}`}>
              <span className="phase-dot" />
              <span className="phase-name">{p.label}</span>
            </li>
          )
        })}
      </ol>

      {progress && progress.total > 0 && (
        <div className="progress-row">
          <div className="progress-meta">
            <span className="progress-count">
              {progress.current} / {progress.total}
            </span>
            <span className="progress-type">{progress.claim_type}</span>
            <span className="progress-text">"{progress.claim_text}"</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${percent}%` }} />
          </div>
        </div>
      )}
    </section>
  )
}

import { useState } from 'react'
import {
  ArrowRight,
  Camera,
  Check,
  CheckCircle,
  MagicWand,
  ShieldCheck,
  SparkleIcon,
  TrendUp,
  Warning,
  X,
} from '@phosphor-icons/react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Only allow <mark>…</mark>; strip everything else. Keeps copy safe-to-render
// via dangerouslySetInnerHTML without opening an HTML-injection surface.
function sanitizeMarked(text) {
  if (!text) return ''
  const escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .replace(/&lt;mark&gt;/g, '<mark>')
    .replace(/&lt;\/mark&gt;/g, '</mark>')
}

// Accept photo_brief as an array OR a "1) … 2) … 3) …" single string and
// always return a clean array of items.
function normalizePhotoBrief(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw
      .map((item) => (typeof item === 'string' ? item : item?.text || ''))
      .map((s) => s.trim())
      .filter(Boolean)
  }
  if (typeof raw !== 'string') return []
  // Split on leading "1) " / "1. " / newlines-then-number patterns
  const parts = raw
    .split(/\s*(?:\d+\s*[\.\)]\s+)|\n{2,}/g)
    .map((s) => s.trim())
    .filter(Boolean)
  if (parts.length > 1) return parts
  // Fallback: split on bullets or sentence boundaries
  return raw
    .split(/(?:[•\-–—]\s+)|(?:\.\s+(?=[A-Z]))/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

function StrategyCard({ type, title, items, keyPrefix }) {
  const Icon = type === 'truth' ? ShieldCheck : Warning
  return (
    <article className="strategy-card theme-panel theme-border">
      <div className="strategy-title">
        <Icon weight="fill" className={type === 'truth' ? 'good' : 'warn'} />
        <h3>{title}</h3>
      </div>
      <ul>
        {items.map((item, i) => (
          <li key={`${keyPrefix}-${i}`}>
            {type === 'truth' ? <Check className="good" /> : <X className="warn" />}
            {item}
          </li>
        ))}
      </ul>
    </article>
  )
}

function AuditScore({ score, predicted }) {
  const value = predicted ?? score?.score
  const hasValue = typeof value === 'number'
  return (
    <div className="audit-score">
      <span>Predicted Audit Score</span>
      <strong>
        {hasValue ? value : '—'}
        <small>/100</small>
        {hasValue && <TrendUp weight="fill" />}
      </strong>
      <em>
        {!hasValue
          ? 'Awaiting rewrite'
          : value >= 80
            ? 'Highly Defensible'
            : 'Needs Tuning'}
      </em>
    </div>
  )
}

function deriveStrategies({ listing, verdicts, claims }) {
  const trustedClaims = claims
    .filter((c) => verdicts[c.id]?.verdict === 'true')
    .map((c) => c.raw_text)
  const weakClaims = claims
    .filter((c) => {
      const v = verdicts[c.id]?.verdict
      return v === 'overstated' || v === 'false' || v === 'misleading'
    })
    .map((c) => c.raw_text)

  return {
    listing,
    truths: trustedClaims.length
      ? trustedClaims
      : ['Awaiting verified claims from audit.'],
    softens: weakClaims.length
      ? weakClaims.map((t) => `"${t}" → soften / re-frame`)
      : ['No weak claims flagged yet.'],
  }
}

export default function WayangView({ listing, claims, verdicts, score, auditId }) {
  const [loading, setLoading] = useState(false)
  const [rewrite, setRewrite] = useState(null)
  const [error, setError] = useState(null)

  const strategies = deriveStrategies({ listing, verdicts, claims })

  const canFlip = !!auditId && !loading

  const onFlip = async () => {
    if (!auditId) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/rewrite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audit_id: auditId }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setRewrite(json)
    } catch (err) {
      setError(err?.message || 'Rewrite failed')
    } finally {
      setLoading(false)
    }
  }

  const title = rewrite?.title || listing?.title || 'Awaiting Listing'
  const copyParas = rewrite?.copy
    ? Array.isArray(rewrite.copy)
      ? rewrite.copy
      : String(rewrite.copy)
          .split(/\n{2,}/)
          .map((p) => p.trim())
          .filter(Boolean)
    : null
  const photoBriefItems = normalizePhotoBrief(rewrite?.photo_brief)
  const improvements = Array.isArray(rewrite?.improvements)
    ? rewrite.improvements
    : []

  return (
    <div className="view-stack">
      <div className="strategy-top theme-border-heavy">
        <div>
          <div className="kicker-row">
            <span className="seller-pill">Seller Strategy Deck</span>
          </div>
          <h1>{title}</h1>
          <p>Optimized Listing Draft {rewrite ? 'v2.1' : '(preview)'}</p>
        </div>
        <AuditScore score={score} predicted={rewrite?.predicted_score} />
      </div>

      <div className="wayang-actions">
        <button
          type="button"
          className="flip-button"
          onClick={onFlip}
          disabled={!canFlip}
        >
          {loading ? 'Rewriting…' : rewrite ? 'Re-flip to seller' : 'Flip to seller'}
        </button>
        {!auditId && (
          <span className="hint-muted">
            Run an audit first — the seller rewrite needs an audit_id.
          </span>
        )}
        {error && <span className="hint-danger">Rewrite error: {error}</span>}
      </div>

      <div className="strategy-grid">
        <StrategyCard
          type="truth"
          title="Strongest Truths (Anchor)"
          items={strategies.truths}
          keyPrefix="truth"
        />
        <StrategyCard
          type="soften"
          title="Weak Claims (Soften)"
          items={strategies.softens}
          keyPrefix="soften"
        />
      </div>

      <section className="copy-panel">
        <div className="copy-heading">
          <h2>Optimized Listing Copy</h2>
          <div>
            <span>
              <MagicWand weight="fill" />
              Filter Optimized
            </span>
            <span className="safe">
              <CheckCircle weight="fill" />
              {rewrite ? 'Technically Defensible' : 'Preview'}
            </span>
          </div>
        </div>

        <article className="listing-copy theme-panel theme-border">
          <div className="quote-mark">"</div>
          {copyParas ? (
            copyParas.map((p, i) => (
              <p
                key={`copy-${i}`}
                dangerouslySetInnerHTML={{ __html: sanitizeMarked(p) }}
              />
            ))
          ) : (
            <p className="copy-placeholder">
              Click “Flip to seller” to generate a defensible rewrite. Improved
              claims appear highlighted so you can see exactly what changed.
            </p>
          )}
        </article>

        {improvements.length > 0 && (
          <section className="improvements-panel theme-panel theme-border">
            <div className="improvements-title">
              <SparkleIcon weight="fill" />
              <h3>How this copy improved</h3>
            </div>
            <ul>
              {improvements.map((imp, i) => (
                <li key={`imp-${i}`}>
                  <span className="imp-was">{imp.was || '—'}</span>
                  <ArrowRight className="imp-arrow" />
                  <span className="imp-now">{imp.now || '—'}</span>
                  {imp.why && <small className="imp-why">{imp.why}</small>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </section>

      <section className="proof-brief theme-panel theme-border">
        <div className="proof-title">
          <Camera />
          Visual Proof Brief
        </div>
        {photoBriefItems.length > 0 ? (
          photoBriefItems.map((item, i) => (
            <label key={`pb-${i}`}>
              <input type="checkbox" readOnly />
              <span>{item}</span>
            </label>
          ))
        ) : (
          <p className="hint-muted" style={{ margin: 0 }}>
            Photo brief will populate after rewrite.
          </p>
        )}
      </section>
    </div>
  )
}

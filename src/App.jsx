import { useEffect, useRef, useState } from 'react'
import {
  CircleNotch,
  Crosshair,
  Detective,
  Link,
  MapPin,
  MaskHappy,
  Robot,
} from '@phosphor-icons/react'
import './App.css'
import AuditProgress from './components/AuditProgress.jsx'
import ClaimCard from './components/ClaimCard.jsx'
import FieldMap from './components/FieldMap.jsx'
import HonestyCard from './components/HonestyCard.jsx'
import WayangView from './components/WayangView.jsx'
import { useAuditStream } from './hooks/useAuditStream.js'

const DEFAULT_URL =
  'https://www.propertyguru.com.sg/listing/the-continuum-2489110'

const FIXTURES = [
  { id: 'demo_bishan', label: 'Bishan' },
  { id: 'demo_tampines', label: 'Tampines' },
  { id: 'demo_tiong_bahru', label: 'Tiong Bahru' },
]

function Header({ mode, onToggle, url, setUrl, onRunUrl, disabled }) {
  const isWayang = mode === 'wayang'
  const submit = (e) => {
    e.preventDefault()
    if (!disabled) onRunUrl()
  }

  return (
    <header className="app-header theme-panel theme-border">
      <div className="brand-search">
        <div className="brand-mark">
          <Crosshair weight="fill" className="brand-icon" />
          <div>
            <div className="brand-name">
              PropIntel<span>.sg</span>
            </div>
            <div className="tagline">
              {isWayang
                ? 'Sell until still defensible.'
                : 'Check until cannot bluff.'}
            </div>
          </div>
        </div>

        <form className="audit-search" onSubmit={submit} aria-label="Audit listing URL">
          <Link className="url-icon" />
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste a PropertyGuru URL"
            aria-label="Listing URL"
          />
          <button type="submit" disabled={disabled} className="run-audit-btn">
            {disabled ? (
              <span className="btn-spinning">
                <CircleNotch weight="bold" />
                Auditing…
              </span>
            ) : (
              'Run Audit'
            )}
          </button>
        </form>
      </div>

      <div className="mode-tools">
        <div className="module-label">Active Module</div>
        <button
          type="button"
          className={`mode-toggle ${isWayang ? 'is-wayang' : ''}`}
          onClick={onToggle}
          aria-pressed={isWayang}
          aria-label="Toggle Kaypoh and Wayang modes"
        >
          <span className="toggle-slider" />
          <span className={`toggle-option ${!isWayang ? 'active' : 'inactive'}`}>
            <Detective size={18} />
            Kaypoh
          </span>
          <span className={`toggle-option ${isWayang ? 'active' : 'inactive'}`}>
            <MaskHappy size={18} />
            Wayang
          </span>
        </button>
      </div>
    </header>
  )
}

function FixtureChips({ onPick, disabled }) {
  return (
    <div className="fixture-chips">
      <span className="fixture-label">Fixtures:</span>
      {FIXTURES.map((fx) => (
        <button
          key={fx.id}
          type="button"
          className="fixture-chip"
          disabled={disabled}
          onClick={() => onPick(fx.id)}
        >
          {fx.label}
        </button>
      ))}
    </div>
  )
}

function AgentSummary({ listing, verdicts, claims }) {
  const total = claims.length
  const done = Object.keys(verdicts).length
  const overstated = Object.values(verdicts).filter(
    (v) => v.verdict === 'overstated' || v.verdict === 'false' || v.verdict === 'misleading',
  ).length
  const trueCount = Object.values(verdicts).filter((v) => v.verdict === 'true').length

  const headline = listing?.title || 'Listing not loaded'
  const summary =
    total === 0
      ? 'Run an audit to extract claims and verify them against GrabMaps evidence.'
      : done < total
        ? `Listing contains ${total} primary claims. ${done}/${total} verified so far.`
        : `Listing contains ${total} primary claims. ${trueCount} verified true, ${overstated} overstated or misleading. Proceed with negotiation leverage.`

  return (
    <div className="agent-summary theme-panel theme-border">
      <div className="robot-badge theme-toggle-bg theme-border">
        <Robot weight="fill" />
      </div>
      <div>
        <h2>Agent Summary</h2>
        <p>
          <strong>{headline}.</strong> {summary}
        </p>
      </div>
    </div>
  )
}

function KaypohView({ listing, claims, verdicts, score }) {
  return (
    <div className="view-stack">
      <div className="dossier-top">
        <div>
          <div className="kicker-row">
            <span className="pill theme-panel theme-border">Target Dossier</span>
            <span>ID: {listing?.url ? listing.url.slice(-10) : '—'}</span>
          </div>
          <h1>{listing?.title || 'Awaiting target'}</h1>
          <p className="location-line">
            <MapPin />
            {listing?.address || 'No address yet'}
          </p>
        </div>
        <HonestyCard score={score} />
      </div>

      <AgentSummary listing={listing} verdicts={verdicts} claims={claims} />

      <section className="ledger">
        <h2>Fact-Check Ledger</h2>
        {claims.length === 0 ? (
          <div className="ledger-empty theme-panel theme-border">
            No claims yet. Run an audit to populate the ledger.
          </div>
        ) : (
          claims.map((claim, idx) => (
            <ClaimCard
              key={claim.id}
              index={idx}
              claim={claim}
              verdict={verdicts[claim.id]}
            />
          ))
        )}
      </section>
    </div>
  )
}

function DetailPanel({ mode, listing, claims, verdicts, score, auditId }) {
  return (
    <main className="detail-panel">
      <div className={`mode-section ${mode === 'kaypoh' ? 'visible' : 'hidden'}`}>
        <KaypohView
          listing={listing}
          claims={claims}
          verdicts={verdicts}
          score={score}
        />
      </div>
      <div className={`mode-section ${mode === 'wayang' ? 'visible' : 'hidden'}`}>
        <WayangView
          listing={listing}
          claims={claims}
          verdicts={verdicts}
          score={score}
          auditId={auditId}
        />
      </div>
    </main>
  )
}

export default function App() {
  const [mode, setMode] = useState('kaypoh')
  const [url, setUrl] = useState(DEFAULT_URL)
  const mapRef = useRef(null)

  const {
    status,
    statusLines,
    listing,
    claims,
    verdicts,
    score,
    auditId,
    phase,
    progress,
    runAudit,
  } = useAuditStream({ mapRef })

  useEffect(() => {
    document.body.classList.toggle('wayang-mode', mode === 'wayang')
    return () => document.body.classList.remove('wayang-mode')
  }, [mode])

  const isBusy = status === 'streaming'

  return (
    <div className="app-shell">
      <Header
        mode={mode}
        onToggle={() =>
          setMode((current) => (current === 'kaypoh' ? 'wayang' : 'kaypoh'))
        }
        url={url}
        setUrl={setUrl}
        onRunUrl={() => runAudit({ url })}
        disabled={isBusy}
      />
      <FixtureChips onPick={(id) => runAudit({ fixture: id })} disabled={isBusy} />
      <AuditProgress status={status} phase={phase} progress={progress} />
      <div className="workspace">
        <FieldMap
          mapRef={mapRef}
          listing={listing}
          statusLines={statusLines}
          status={status}
        />
        <DetailPanel
          mode={mode}
          listing={listing}
          claims={claims}
          verdicts={verdicts}
          score={score}
          auditId={auditId}
        />
      </div>
    </div>
  )
}

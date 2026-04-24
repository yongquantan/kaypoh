import { useEffect, useMemo, useState } from 'react'
import {
  Buildings,
  Camera,
  Check,
  CheckCircle,
  Crosshair,
  Detective,
  Link,
  MagicWand,
  MagnifyingGlass,
  MapPin,
  MaskHappy,
  Ruler,
  ShieldCheck,
  TrafficCone,
  Train,
  TrendUp,
  Warning,
  WarningCircle,
  WifiHigh,
  X,
  Stack,
  Robot,
} from '@phosphor-icons/react'
import './App.css'

const kaypohLogs = [
  { text: '> Initializing agent audit session 0x9A2F...', tone: 'muted' },
  { text: '> Target URL locked. Extracting claims... [4 found]', tone: 'muted' },
  { text: '> Connecting to GrabMaps GIS... [CONNECTED]', tone: 'success' },
  { text: '> Running routing matrix for POI: Dakota MRT (CC8)' },
  {
    text: '> WARN: Pedestrian path unsheltered. Distance: 850m. Avg walk time: 11.2 mins.',
    tone: 'warn',
  },
  { text: '> Querying OneMap API for school zones (1km radius)...' },
  {
    text: "> Found: Kong Hwa, Tanjong Katong Pri, Haig Girls', CHIJ (Katong) Pri. [VERIFIED]",
    tone: 'success',
  },
  {
    text: '> Processing street-view imagery (Lat: 1.305, Lng: 103.896) Azimuth 270deg...',
  },
  {
    text: '> ALERT: Elevation data shows Block 4 structures obstruct west-facing vectors. "Unblocked" claim fails validation.',
    tone: 'danger',
  },
]

const wayangLogs = [
  { text: '> Switching to Strategy Engine v2...' },
  { text: '> Loading NLP models for real estate optimization...' },
  { text: '> Analyzing Kaypoh vulnerabilities... [2 critical flags found]' },
  { text: '> REWRITE TRIGGERED: View claims need softening.', tone: 'warn' },
  { text: '> REWRITE TRIGGERED: Distance claims need re-framing.', tone: 'warn' },
  { text: '> Generating defensible copy...' },
  {
    text: '> Cross-referencing against filter optimization rules... [PASS]',
    tone: 'success',
  },
  { text: '> Compiling Photo Brief to match rewritten narrative...' },
  {
    text: '> SUCCESS: Dossier ready. Predicted audit survival rate: 92%.',
    tone: 'warn',
  },
]

const claims = [
  {
    id: '01',
    claim: '"Near Dakota MRT"',
    verdict: 'Overstated',
    stamp: 'warn',
    intel:
      '11 min walk to CC8 Dakota MRT Station (850m). Route involves 2 major crossings and is 80% unsheltered.',
  },
  {
    id: '02',
    claim: '"Within 1km of reputable schools"',
    verdict: 'Verified True',
    stamp: 'true',
    intel:
      "Confirmed. 4 primary schools fall strictly within the 1km radius polygon (Kong Hwa, Tanjong Katong, Haig Girls', CHIJ).",
  },
  {
    id: '03',
    claim: '"Near amenities in Tanjong Katong"',
    verdict: 'Verified True',
    stamp: 'true',
    intel:
      'High density detected. 18+ F&B and retail amenity hits within a 5-minute walk radius.',
  },
  {
    id: '04',
    claim: '"Unblocked 270-degree views"',
    verdict: 'False / Misleading',
    stamp: 'false',
    intel:
      'Street-view validation and 3D elevation check confirms adjacent HDB blocks obstruct views below floor 15 on the West-facing stacks. Claim is generic and factually incorrect for majority of units.',
  },
]

function Header({ mode, onToggle }) {
  const isWayang = mode === 'wayang'

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
              {isWayang ? 'Sell until still defensible.' : 'Check until cannot bluff.'}
            </div>
          </div>
        </div>

        <form className="audit-search" aria-label="Audit listing URL">
          <Link className="url-icon" />
          <input
            type="text"
            value="https://www.propertyguru.com.sg/listing/the-continuum-2489110"
            readOnly
            aria-label="Listing URL"
          />
          <button type="button">Run Audit</button>
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

function MapPanel() {
  return (
    <section className="map-shell theme-border">
      <div className="map-stage">
        <div className="feed-card theme-panel theme-border">
          <div className="feed-status">
            <span />
            Live Feed Active
          </div>
          <div className="feed-target">Target: The Continuum</div>
          <div className="feed-coords">1.3056deg N, 103.8967deg E</div>
        </div>

        <div className="map-controls">
          {[Stack, Ruler, TrafficCone].map((Icon, index) => (
            <button type="button" className="map-button theme-panel theme-border" key={index}>
              <Icon />
            </button>
          ))}
        </div>

        <div className="site-block">
          <Buildings size={28} />
          <span>Site</span>
        </div>

        <div className="station-marker">
          <div>
            <Train weight="fill" />
          </div>
          <span className="theme-panel theme-border">CC8 Dakota</span>
        </div>

        <svg className="route-layer" aria-hidden="true">
          <path d="M 40% 50% L 20% 30%" />
          <circle cx="40%" cy="50%" r="4" />
        </svg>

        <div className="amenities-cluster">
          <i />
          <i />
          <i className="red" />
          <i className="strong" />
          <i className="yellow" />
          <span>TK Amenities</span>
        </div>
      </div>
    </section>
  )
}

function Terminal({ mode }) {
  const logs = useMemo(() => (mode === 'wayang' ? wayangLogs : kaypohLogs), [mode])
  const [visibleCount, setVisibleCount] = useState(logs.length)

  useEffect(() => {
    const timers = logs.map((_, index) =>
      window.setTimeout(() => setVisibleCount(index + 1), index * 150),
    )

    return () => timers.forEach(window.clearTimeout)
  }, [logs])

  return (
    <section className="terminal theme-console">
      <div className="terminal-bar">
        <span>Terminal // grab_maps_api_v4</span>
        <span>
          <WifiHigh weight="fill" className="stream-icon" />
          Stream OK
        </span>
      </div>
      <div className="terminal-output" aria-live="polite">
        {logs.slice(0, visibleCount).map((log, index) => (
          <div className={`terminal-line ${log.tone || ''}`} key={`${mode}-${index}`}>
            {log.text}
          </div>
        ))}
        <div className="cursor">_</div>
      </div>
    </section>
  )
}

function FieldMap({ mode }) {
  return (
    <aside className="field-map">
      <MapPanel />
      <Terminal key={mode} mode={mode} />
    </aside>
  )
}

function HonestyCard() {
  return (
    <div className="score-card warning-card">
      <span>Honesty Index</span>
      <strong>
        68<small>/100</small>
      </strong>
      <em>Needs Verification</em>
    </div>
  )
}

function AgentSummary() {
  return (
    <div className="agent-summary theme-panel theme-border">
      <div className="robot-badge theme-toggle-bg theme-border">
        <Robot weight="fill" />
      </div>
      <div>
        <h2>Agent Summary</h2>
        <p>
          Listing contains <strong>4 primary claims</strong>. Proximity to schools is verified.
          Transport claims omit crucial walking conditions. View claims contradict physical
          terrain data. Proceed with negotiation leverage.
        </p>
      </div>
    </div>
  )
}

function VerdictStamp({ type, children }) {
  return <span className={`verdict-stamp stamp-${type}`}>{children}</span>
}

function ClaimCard({ claim }) {
  const isFalse = claim.stamp === 'false'

  return (
    <article className={`claim-card theme-panel theme-border ${isFalse ? 'is-false' : ''}`}>
      {isFalse && <WarningCircle weight="fill" className="claim-watermark" />}
      <div className="claim-header">
        <div>
          <span>Listing Claim {claim.id}</span>
          <p>{claim.claim}</p>
        </div>
        <VerdictStamp type={claim.stamp}>{claim.verdict}</VerdictStamp>
      </div>
      <div className="claim-body">
        <MagnifyingGlass />
        <div>
          <span>GrabMaps Intel</span>
          <p>{claim.intel}</p>
        </div>
      </div>
    </article>
  )
}

function KaypohView() {
  return (
    <div className="view-stack">
      <div className="dossier-top">
        <div>
          <div className="kicker-row">
            <span className="pill theme-panel theme-border">Target Dossier</span>
            <span>ID: THCN-8821</span>
          </div>
          <h1>The Continuum</h1>
          <p className="location-line">
            <MapPin />
            Thiam Siew Ave, D15
          </p>
        </div>
        <HonestyCard />
      </div>

      <AgentSummary />

      <section className="ledger">
        <h2>Fact-Check Ledger</h2>
        {claims.map((claim) => (
          <ClaimCard claim={claim} key={claim.id} />
        ))}
      </section>
    </div>
  )
}

function StrategyCard({ type, title, items }) {
  const Icon = type === 'truth' ? ShieldCheck : Warning

  return (
    <article className="strategy-card theme-panel theme-border">
      <div className="strategy-title">
        <Icon weight="fill" className={type === 'truth' ? 'good' : 'warn'} />
        <h3>{title}</h3>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item}>
            {type === 'truth' ? <Check className="good" /> : <X className="warn" />}
            {item}
          </li>
        ))}
      </ul>
    </article>
  )
}

function WayangView() {
  return (
    <div className="view-stack">
      <div className="strategy-top theme-border-heavy">
        <div>
          <div className="kicker-row">
            <span className="seller-pill">Seller Strategy Deck</span>
          </div>
          <h1>The Continuum</h1>
          <p>Optimized Listing Draft v2.1</p>
        </div>
        <div className="audit-score">
          <span>Predicted Audit Score</span>
          <strong>
            92<small>/100</small>
            <TrendUp weight="fill" />
          </strong>
          <em>Highly Defensible</em>
        </div>
      </div>

      <div className="strategy-grid">
        <StrategyCard
          type="truth"
          title="Strongest Truths (Anchor)"
          items={[
            'Verified 1km radius to 4 top primary schools.',
            'Extremely high amenity density in Tanjong Katong.',
          ]}
        />
        <StrategyCard
          type="soften"
          title="Weak Claims (Soften)"
          items={[
            '"Near MRT" -> Frame as "Access to Dakota MRT".',
            '"Unblocked views" -> Restrict to "selected premium stacks".',
          ]}
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
              Technically Defensible
            </span>
          </div>
        </div>

        <article className="listing-copy theme-panel theme-border">
          <div className="quote-mark">"</div>
          <p>
            Discover The Continuum, a rare freehold sanctuary positioned at the intersection of
            lifestyle and convenience. <mark>Enjoy verified access to Dakota MRT (CC8)</mark>,
            connecting you effortlessly to the city core.
          </p>
          <p>
            For families, location is paramount. This development sits{' '}
            <mark>within the coveted 1km radius of four reputable primary schools</mark>, including
            Kong Hwa and Tanjong Katong Primary, ensuring your educational needs are strictly met.
          </p>
          <p>
            Step outside and immerse yourself in an{' '}
            <mark>established enclave with over 18 nearby amenities</mark> along the vibrant Tanjong
            Katong stretch. Retreat home to thoughtfully designed layouts where{' '}
            <mark>selected premium stacks enjoy open, expansive outlooks</mark> over the surrounding
            landed estate.
          </p>
        </article>
      </section>

      <section className="proof-brief theme-panel theme-border">
        <div className="proof-title">
          <Camera />
          Visual Proof Brief
        </div>
        <label>
          <input type="checkbox" checked readOnly />
          <span>Shoot wide angle of the Tanjong Katong amenity cluster (shows lifestyle).</span>
        </label>
        <label>
          <input type="checkbox" checked readOnly />
          <span>
            Capture school gates of Kong Hwa with condo development in background (proves proximity).
          </span>
        </label>
        <label>
          <input type="checkbox" readOnly />
          <span>
            Focus drone shots ONLY on East-facing stacks overlooking landed property (defends view
            claim).
          </span>
        </label>
      </section>
    </div>
  )
}

function DetailPanel({ mode }) {
  return (
    <main className="detail-panel">
      <div className={`mode-section ${mode === 'kaypoh' ? 'visible' : 'hidden'}`}>
        <KaypohView />
      </div>
      <div className={`mode-section ${mode === 'wayang' ? 'visible' : 'hidden'}`}>
        <WayangView />
      </div>
    </main>
  )
}

function App() {
  const [mode, setMode] = useState('kaypoh')

  useEffect(() => {
    document.body.classList.toggle('wayang-mode', mode === 'wayang')
    return () => document.body.classList.remove('wayang-mode')
  }, [mode])

  return (
    <div className="app-shell">
      <Header
        mode={mode}
        onToggle={() => setMode((current) => (current === 'kaypoh' ? 'wayang' : 'kaypoh'))}
      />
      <div className="workspace">
        <FieldMap mode={mode} />
        <DetailPanel mode={mode} />
      </div>
    </div>
  )
}

export default App

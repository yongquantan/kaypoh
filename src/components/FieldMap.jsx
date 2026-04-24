import { Ruler, Stack, TrafficCone } from '@phosphor-icons/react'
import MapPanel from './MapPanel.jsx'
import Terminal from './Terminal.jsx'

function formatCoords(listing) {
  if (!listing) return '—'
  if (listing.lat && listing.lng) {
    return `${listing.lat.toFixed(4)}° N, ${listing.lng.toFixed(4)}° E`
  }
  return listing.address || '—'
}

export default function FieldMap({ mapRef, listing, statusLines, status }) {
  const targetName = listing?.title || 'Awaiting target'
  return (
    <aside className="field-map">
      <section className="map-shell theme-border">
        <div className="map-stage">
          <MapPanel ref={mapRef} />

          <div className="feed-card theme-panel theme-border">
            <div className="feed-status">
              <span />
              {status === 'streaming' ? 'Live Feed Active' : 'Feed Idle'}
            </div>
            <div className="feed-target">Target: {targetName}</div>
            <div className="feed-coords">{formatCoords(listing)}</div>
          </div>

          <div className="map-controls">
            {[Stack, Ruler, TrafficCone].map((Icon, index) => (
              <button
                type="button"
                className="map-button theme-panel theme-border"
                key={index}
                aria-label={`Map layer ${index + 1}`}
              >
                <Icon />
              </button>
            ))}
          </div>
        </div>
      </section>
      <Terminal lines={statusLines} connected={status === 'streaming'} />
    </aside>
  )
}

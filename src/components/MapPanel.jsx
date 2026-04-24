import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { polyline6ToLngLat } from '../utils/polyline.js'

const STYLE_URL = 'https://maps.grab.com/api/style.json'
const DEFAULT_CENTER = [103.8481, 1.3519] // Bishan-ish, [lng,lat]
const DEFAULT_ZOOM = 12

// Build transformRequest bound to the current API key.
// Rewrites BUG-02 tile path + injects Authorization Bearer for maps.grab.com.
function buildTransformRequest(apiKey) {
  return (url) => {
    let rewritten = url
    // BUG-02: advertised tile path 403s; correct path is /api/v1/maps/tiles/...
    if (rewritten.includes('maps.grab.com/maps/tiles/')) {
      rewritten = rewritten.replace(
        'maps.grab.com/maps/tiles/',
        'maps.grab.com/api/v1/maps/tiles/',
      )
    }
    if (rewritten.includes('maps.grab.com')) {
      return {
        url: rewritten,
        headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
      }
    }
    return { url: rewritten }
  }
}

const MapPanel = forwardRef(function MapPanel(_, ref) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const pinsRef = useRef(new Map()) // id -> maplibregl.Marker
  const routesRef = useRef(new Map()) // id -> { sourceId, layerId }
  const pinCounterRef = useRef(0)
  const routeCounterRef = useRef(0)
  const readyRef = useRef(false)
  const queueRef = useRef([])

  const [streetView, setStreetView] = useState(null) // {photo_urls, heading, lat, lng}
  const [missingKeyBanner, setMissingKeyBanner] = useState(false)

  const apiKey = import.meta.env.VITE_GRABMAPS_KEY

  useEffect(() => {
    if (!apiKey || apiKey === 'bm_replace_me') {
      console.warn(
        '[MapPanel] VITE_GRABMAPS_KEY missing or unset. GrabMaps tiles will fail.',
      )
      setMissingKeyBanner(true)
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
      transformRequest: buildTransformRequest(apiKey),
    })

    mapRef.current = map

    map.on('load', () => {
      readyRef.current = true
      // Flush queued imperative calls that arrived pre-load
      const queue = queueRef.current
      queueRef.current = []
      queue.forEach((fn) => {
        try {
          fn()
        } catch (err) {
          console.warn('[MapPanel] queued op failed', err)
        }
      })
    })

    map.on('error', (evt) => {
      // Surface tile/style errors but don't crash
      if (evt && evt.error) {
        console.warn('[MapPanel] maplibre error', evt.error?.message || evt.error)
      }
    })

    // Capture refs for cleanup (linter wants stable values).
    const pins = pinsRef.current
    const routes = routesRef.current

    return () => {
      readyRef.current = false
      pins.forEach((m) => m.remove())
      pins.clear()
      routes.clear()
      map.remove()
      mapRef.current = null
    }
    // apiKey intentionally read once per mount; ignore hook deps warning for it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Schedule ops until the map is loaded.
  const schedule = (fn) => {
    if (readyRef.current && mapRef.current) {
      return fn()
    }
    queueRef.current.push(fn)
    return undefined
  }

  useImperativeHandle(ref, () => ({
    flyTo({ lat, lng, zoom = 15 }) {
      schedule(() => {
        mapRef.current.flyTo({
          center: [lng, lat],
          zoom,
          speed: 1.2,
          essential: true,
        })
      })
    },
    addPin({ lat, lng, color = '#a97629', label = '' } = {}) {
      pinCounterRef.current += 1
      const id = `pin-${pinCounterRef.current}`
      schedule(() => {
        const marker = new maplibregl.Marker({ color })
          .setLngLat([lng, lat])
          .addTo(mapRef.current)
        if (label) {
          marker.setPopup(new maplibregl.Popup({ offset: 18 }).setText(label))
        }
        pinsRef.current.set(id, marker)
      })
      return id
    },
    addRoute({ from, to, polyline, color = '#a97629', id } = {}) {
      const routeId = id || `route-${++routeCounterRef.current}`
      schedule(() => {
        const map = mapRef.current
        let coords
        if (polyline) {
          coords = polyline6ToLngLat(polyline)
        } else if (from && to) {
          coords = [
            [from[1], from[0]],
            [to[1], to[0]],
          ]
        } else {
          return
        }
        if (!coords.length) return

        const sourceId = `route-src-${routeId}`
        const layerId = `route-layer-${routeId}`

        // Clean up a pre-existing entry under the same id
        if (routesRef.current.has(routeId)) {
          const prev = routesRef.current.get(routeId)
          if (map.getLayer(prev.layerId)) map.removeLayer(prev.layerId)
          if (map.getSource(prev.sourceId)) map.removeSource(prev.sourceId)
        }

        map.addSource(sourceId, {
          type: 'geojson',
          data: {
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: coords },
          },
        })
        map.addLayer({
          id: layerId,
          type: 'line',
          source: sourceId,
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': color,
            'line-width': 4,
            'line-opacity': 0.85,
          },
        })
        routesRef.current.set(routeId, { sourceId, layerId })
      })
      return routeId
    },
    openStreetView({ photo_urls = [], heading = 0, lat, lng } = {}) {
      setStreetView({ photo_urls: photo_urls || [], heading, lat, lng })
    },
    clear(what = 'all') {
      const targets =
        what === 'all'
          ? ['routes', 'pins', 'streetview']
          : [what]

      if (targets.includes('pins')) {
        schedule(() => {
          pinsRef.current.forEach((m) => m.remove())
          pinsRef.current.clear()
        })
      }
      if (targets.includes('routes')) {
        schedule(() => {
          const map = mapRef.current
          routesRef.current.forEach(({ sourceId, layerId }) => {
            if (map.getLayer(layerId)) map.removeLayer(layerId)
            if (map.getSource(sourceId)) map.removeSource(sourceId)
          })
          routesRef.current.clear()
        })
      }
      if (targets.includes('streetview')) {
        setStreetView(null)
      }
    },
  }))

  return (
    <div className="map-layer-host">
      <div ref={containerRef} className="maplibre-container" />

      {missingKeyBanner && (
        <div className="map-warning-banner">
          GrabMaps key missing — set VITE_GRABMAPS_KEY in .env.local
        </div>
      )}

      {streetView && (
        <div className="streetview-overlay">
          <div className="streetview-head">
            <span>Street View</span>
            <button
              type="button"
              onClick={() => setStreetView(null)}
              aria-label="Close street view"
            >
              ×
            </button>
          </div>
          <div className="streetview-body">
            {streetView.photo_urls && streetView.photo_urls.length > 0 ? (
              <img
                src={streetView.photo_urls[0]}
                alt={`Street view at ${streetView.lat}, ${streetView.lng}`}
              />
            ) : (
              <div className="streetview-empty">
                No street view imagery for this location.
              </div>
            )}
          </div>
          {streetView.heading != null && streetView.photo_urls?.length > 0 && (
            <div className="streetview-foot">
              Heading {Math.round(streetView.heading)}°
            </div>
          )}
        </div>
      )}
    </div>
  )
})

export default MapPanel

// Offline replay of a plausible audit stream for demo_bishan.
// Yields events to match specs/sse-contract.md exactly.
// Enable by appending ?mock=1 to the URL.

const BISHAN = { lat: 1.3519, lng: 103.8481 }
const BISHAN_MRT = { lat: 1.35086, lng: 103.84825 }
const JUNCTION_8 = { lat: 1.35041, lng: 103.84891 }
const AI_TONG = { lat: 1.35608, lng: 103.83998 }

// Synthetic polyline6 (MapLibre will just draw from/to as a fallback if decode is empty,
// but our decoder will consume any valid sequence). We pass an empty polyline for some
// mock routes so the straight-line fallback is exercised.
const EMPTY_PL = ''

let seq = 0
const nextSeq = () => ++seq
const now = () => Date.now() / 1000
const base = () => ({ t: now(), seq: nextSeq() })

export const MOCK_EVENTS = [
  {
    delay: 100,
    event: 'status',
    data: { stage: 'scraping', message: '> Scraping listing fixture: demo_bishan', tone: 'muted' },
  },
  {
    delay: 250,
    event: 'listing',
    data: {
      url: 'https://www.propertyguru.com.sg/listing/demo-bishan',
      title: 'Luxurious 3BR @ Bishan Heights',
      address: 'Bishan Street 13, Singapore',
      price_sgd: 1680000,
      bedrooms: 3,
      sqft: 1119,
    },
  },
  {
    delay: 180,
    event: 'status',
    data: { stage: 'geocoding', message: '> MCP.search -> Bishan Street 13', tone: 'muted' },
  },
  {
    delay: 220,
    event: 'geocode',
    data: { ...BISHAN, label: 'Bishan Street 13', confidence: true },
  },
  {
    delay: 120,
    event: 'map_event',
    data: { op: 'flyTo', lat: BISHAN.lat, lng: BISHAN.lng, zoom: 16 },
  },
  {
    delay: 60,
    event: 'map_event',
    data: { op: 'pin', lat: BISHAN.lat, lng: BISHAN.lng, color: '#1b4332', label: 'Site' },
  },
  {
    delay: 180,
    event: 'status',
    data: { stage: 'extracting', message: '> Claude extracted 4 claims [temp=0]', tone: 'muted' },
  },
  {
    delay: 80,
    event: 'claims',
    data: {
      claims: [
        {
          id: 'c-01',
          type: 'walk_time',
          raw_text: '5 min walk to Bishan MRT',
          parsed: { destination: 'Bishan MRT', minutes: 5 },
        },
        {
          id: 'c-02',
          type: 'amenity',
          raw_text: 'Right next to Junction 8 shopping',
          parsed: { destination: 'Junction 8', category: 'mall' },
        },
        {
          id: 'c-03',
          type: 'school_access',
          raw_text: 'Within 1km of Ai Tong School',
          parsed: { destination: 'Ai Tong School', radius_km: 1 },
        },
        {
          id: 'c-04',
          type: 'quiet',
          raw_text: 'Peaceful, quiet road',
          parsed: {},
        },
      ],
    },
  },
  {
    delay: 300,
    event: 'status',
    data: { stage: 'auditing', message: '> Verifying claim c-01 (walk_time)', tone: 'muted' },
  },
  {
    delay: 300,
    event: 'verdict',
    data: {
      claim_id: 'c-01',
      verdict: 'overstated',
      finding: 'Real walk: 8.4 min to Bishan MRT. Listing claimed 5 min.',
      delta: 0.68,
      evidence: {
        destination: 'Bishan MRT',
        destination_latlng: [BISHAN_MRT.lat, BISHAN_MRT.lng],
        real_minutes: 8.4,
        claimed_minutes: 5,
      },
      endpoints_called: ['search', 'navigation'],
      map_events: [
        { op: 'pin', lat: BISHAN_MRT.lat, lng: BISHAN_MRT.lng, color: '#a97629', label: 'Bishan MRT' },
        {
          op: 'route',
          from: [BISHAN.lat, BISHAN.lng],
          to: [BISHAN_MRT.lat, BISHAN_MRT.lng],
          profile: 'walking',
          color: '#a97629',
          polyline: EMPTY_PL,
        },
      ],
    },
  },
  {
    delay: 300,
    event: 'verdict',
    data: {
      claim_id: 'c-02',
      verdict: 'true',
      finding: 'Junction 8 is 220m away (~3 min walk). Claim verified.',
      delta: null,
      evidence: {
        destination: 'Junction 8',
        destination_latlng: [JUNCTION_8.lat, JUNCTION_8.lng],
      },
      endpoints_called: ['nearby', 'navigation'],
      map_events: [
        { op: 'pin', lat: JUNCTION_8.lat, lng: JUNCTION_8.lng, color: '#2f7a3d', label: 'Junction 8' },
        {
          op: 'route',
          from: [BISHAN.lat, BISHAN.lng],
          to: [JUNCTION_8.lat, JUNCTION_8.lng],
          profile: 'walking',
          color: '#2f7a3d',
          polyline: EMPTY_PL,
        },
      ],
    },
  },
  {
    delay: 300,
    event: 'verdict',
    data: {
      claim_id: 'c-03',
      verdict: 'true',
      finding: 'Ai Tong School is 720m away, within the 1km radius.',
      delta: null,
      evidence: {
        destination: 'Ai Tong School',
        destination_latlng: [AI_TONG.lat, AI_TONG.lng],
      },
      endpoints_called: ['search', 'navigation'],
      map_events: [
        { op: 'pin', lat: AI_TONG.lat, lng: AI_TONG.lng, color: '#2f7a3d', label: 'Ai Tong School' },
      ],
    },
  },
  {
    delay: 300,
    event: 'verdict',
    data: {
      claim_id: 'c-04',
      verdict: 'misleading',
      finding: '3 traffic incidents in the past 24h within 200m. Road is not quiet.',
      delta: null,
      evidence: {},
      endpoints_called: ['incidents_bbox'],
      map_events: [],
    },
  },
  {
    delay: 220,
    event: 'status',
    data: { stage: 'scoring', message: '> Computing honesty index', tone: 'muted' },
  },
  {
    delay: 180,
    event: 'score',
    data: {
      score: 54,
      breakdown: { true: 2, overstated: 1, misleading: 1, false: 0, unverifiable: 0 },
      audit_id: 'audit_mock_bishan',
      endpoints_used: ['search', 'navigation', 'nearby', 'incidents_bbox'],
    },
  },
  {
    delay: 60,
    event: 'done',
    data: { ok: true, duration_ms: 3120 },
  },
]

// Playback: invokes emit(eventName, parsedJsonObject) with realistic timing.
// Returns a cancel function.
export function playMockStream({ emit, onDone, onError } = {}) {
  let cancelled = false
  let timer = null
  let idx = 0

  const step = () => {
    if (cancelled) return
    if (idx >= MOCK_EVENTS.length) {
      onDone && onDone()
      return
    }
    const item = MOCK_EVENTS[idx++]
    timer = setTimeout(() => {
      if (cancelled) return
      try {
        emit(item.event, { ...base(), ...item.data })
      } catch (err) {
        onError && onError(err)
      }
      step()
    }, item.delay)
  }

  // Reset seq for a fresh run
  seq = 0
  step()

  return () => {
    cancelled = true
    if (timer) clearTimeout(timer)
  }
}

export function isMockMode() {
  if (typeof window === 'undefined') return false
  try {
    return new URLSearchParams(window.location.search).get('mock') === '1'
  } catch {
    return false
  }
}

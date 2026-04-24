import { useCallback, useEffect, useRef, useState } from 'react'
import { isMockMode, playMockStream } from '../devmode/mockAuditStream.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const KNOWN_OPS = new Set(['pin', 'route', 'flyTo', 'streetview', 'clear'])

// Dispatches a single map_events entry onto the MapPanel imperative API.
function dispatchMapOp(mapRef, op) {
  if (!mapRef?.current || !op || !op.op) return
  if (!KNOWN_OPS.has(op.op)) {
    console.warn('[useAuditStream] unknown map_events op, ignoring:', op.op)
    return
  }
  const api = mapRef.current
  try {
    switch (op.op) {
      case 'pin':
        api.addPin({ lat: op.lat, lng: op.lng, color: op.color, label: op.label })
        break
      case 'route':
        api.addRoute({
          from: op.from,
          to: op.to,
          polyline: op.polyline,
          color: op.color,
          id: op.id,
        })
        break
      case 'flyTo':
        api.flyTo({ lat: op.lat, lng: op.lng, zoom: op.zoom })
        break
      case 'streetview':
        api.openStreetView({
          photo_urls: op.photo_urls || [],
          heading: op.heading,
          lat: op.lat,
          lng: op.lng,
        })
        break
      case 'clear':
        api.clear(op.what || 'all')
        break
      default:
        break
    }
  } catch (err) {
    console.warn('[useAuditStream] map op dispatch failed:', err)
  }
}

// Streams text/event-stream from fetch(). We support "POST + SSE" — EventSource
// only handles GET. Events arrive as blocks separated by blank lines; within
// each block, "event:" names the type and "data:" carries a JSON payload
// (possibly split across multiple data: lines).
async function consumeSSE({ url, body, onEvent, signal }) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (!block.trim()) continue

      let eventName = 'message'
      const dataLines = []
      for (const line of block.split('\n')) {
        if (line.startsWith(':')) continue
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (dataLines.length === 0) continue
      const raw = dataLines.join('\n')
      let parsed
      try {
        parsed = JSON.parse(raw)
      } catch {
        parsed = { raw }
      }
      onEvent(eventName, parsed)
    }
  }
}

export function useAuditStream({ mapRef }) {
  const [status, setStatus] = useState('idle') // idle | streaming | done | error | cancelled
  const [statusLines, setStatusLines] = useState([]) // [{tone, text, seq}]
  const [listing, setListing] = useState(null)
  const [claims, setClaims] = useState([]) // raw claims list
  const [verdicts, setVerdicts] = useState({}) // claim_id -> verdict event
  const [score, setScore] = useState(null)
  const [auditId, setAuditId] = useState(null)
  // Which phase is active: 'scraping' → 'extracting' → 'geocoding' → 'auditing' → 'scoring'
  const [phase, setPhase] = useState(null)
  // { current, total, claim_type, claim_text } while a verifier is in flight
  const [progress, setProgress] = useState(null)

  const abortRef = useRef(null)
  const cancelMockRef = useRef(null)
  const lineCounterRef = useRef(0)

  const appendLine = useCallback((text, tone = 'muted') => {
    lineCounterRef.current += 1
    setStatusLines((prev) => [
      ...prev,
      { text, tone, seq: lineCounterRef.current },
    ])
  }, [])

  const resetRunState = useCallback(() => {
    lineCounterRef.current = 0
    setStatusLines([])
    setListing(null)
    setClaims([])
    setVerdicts({})
    setScore(null)
    setAuditId(null)
    setPhase(null)
    setProgress(null)
  }, [])

  // Central event handler applied to both live SSE and mock stream.
  const handleEvent = useCallback(
    (name, data) => {
      switch (name) {
        case 'status': {
          const text = data.message || ''
          appendLine(text, data.tone || 'muted')
          if (data.stage) setPhase(data.stage)
          break
        }
        case 'progress':
          setProgress({
            current: data.current,
            total: data.total,
            claim_id: data.claim_id,
            claim_type: data.claim_type,
            claim_text: data.claim_text,
          })
          break
        case 'listing':
          setListing(data)
          break
        case 'geocode': {
          if (mapRef?.current) {
            mapRef.current.flyTo({ lat: data.lat, lng: data.lng, zoom: 16 })
            mapRef.current.addPin({
              lat: data.lat,
              lng: data.lng,
              color: '#1b4332',
              label: data.label || 'Site',
            })
          }
          break
        }
        case 'claims':
          setClaims(Array.isArray(data.claims) ? data.claims : [])
          break
        case 'verdict': {
          if (!data?.claim_id) break
          setVerdicts((prev) => ({ ...prev, [data.claim_id]: data }))
          if (Array.isArray(data.map_events)) {
            data.map_events.forEach((op) => dispatchMapOp(mapRef, op))
          }
          break
        }
        case 'map_event':
          dispatchMapOp(mapRef, data)
          break
        case 'score':
          setScore(data)
          if (data?.audit_id) setAuditId(data.audit_id)
          break
        case 'done':
          setStatus('done')
          appendLine('> Audit complete.', 'success')
          break
        case 'error':
          appendLine(`> ERROR: ${data?.message || 'stream error'}`, 'danger')
          if (!data?.recoverable) {
            setStatus('error')
          }
          break
        default:
          // Unknown event types: log and ignore per spec.
          console.info('[useAuditStream] unknown event:', name, data)
      }
    },
    [appendLine, mapRef],
  )

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    if (cancelMockRef.current) {
      cancelMockRef.current()
      cancelMockRef.current = null
    }
    setStatus((prev) => (prev === 'streaming' ? 'cancelled' : prev))
  }, [])

  const runAudit = useCallback(
    async (payload) => {
      cancel()
      resetRunState()
      if (mapRef?.current) {
        try {
          mapRef.current.clear('all')
        } catch {
          // non-fatal
        }
      }
      setStatus('streaming')
      appendLine('> Initializing audit session...', 'muted')

      if (isMockMode()) {
        appendLine('> Mock mode ON (?mock=1). Replaying canned stream.', 'warn')
        cancelMockRef.current = playMockStream({
          emit: (name, data) => handleEvent(name, data),
          onDone: () => {
            setStatus((prev) => (prev === 'streaming' ? 'done' : prev))
          },
          onError: (err) => {
            appendLine(`> Mock error: ${err?.message || err}`, 'danger')
            setStatus('error')
          },
        })
        return
      }

      const controller = new AbortController()
      abortRef.current = controller

      try {
        await consumeSSE({
          url: `${API_BASE}/audit/stream`,
          body: payload || {},
          signal: controller.signal,
          onEvent: handleEvent,
        })
        setStatus((prev) => (prev === 'streaming' ? 'done' : prev))
      } catch (err) {
        if (err?.name === 'AbortError') return
        appendLine(
          `> Connection dropped: ${err?.message || 'unknown error'}`,
          'danger',
        )
        setStatus('error')
      } finally {
        abortRef.current = null
      }
    },
    [appendLine, cancel, handleEvent, mapRef, resetRunState],
  )

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort()
      if (cancelMockRef.current) cancelMockRef.current()
    }
  }, [])

  return {
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
    cancel,
  }
}

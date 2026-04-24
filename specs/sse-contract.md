# Spec: SSE Contract

**Status:** Frozen. Both backend and frontend must implement exactly this contract.

The backend streams an audit run to the frontend over Server-Sent Events at
`POST /audit/stream` (body: `{"url": "..."} | {"fixture": "..."} | {"fixture": "...", "canned": true}`).

Every event is a JSON object preceded by an `event:` line. All events share:

```jsonc
{
  "t": 1745500000.123,   // server timestamp, seconds since epoch (float)
  "seq": 17              // monotonic per stream, starts at 1
}
```

Additional fields below per event type. Unknown event types MUST be ignored by the
frontend, not errored — this lets us add event types without breaking the client.

---

## Events

### `status` — human-readable progress line for the terminal feed

```jsonc
{
  "stage": "scraping" | "extracting" | "geocoding" | "auditing" | "scoring" | "done",
  "message": "Connecting to GrabMaps GIS...",
  "tone": "muted" | "success" | "warn" | "danger"  // optional, defaults "muted"
}
```

Mapped into the existing Kaypoh `Terminal` component's log array. The frontend
appends one terminal line per `status` event, using `tone` to colour it.

### `listing` — the scraped/loaded listing header

```jsonc
{
  "url": "https://www.propertyguru.com.sg/listing/...",
  "title": "Luxurious 3BR @ Bishan...",
  "address": "Bishan Street 13, Singapore",
  "price_sgd": 1680000,
  "bedrooms": 3,
  "sqft": 1119
}
```

Populates the Target Dossier header (title, address, ID, price).

### `geocode` — origin locked; fly the map there

```jsonc
{
  "lat": 1.3519,
  "lng": 103.8481,
  "label": "Bishan Street 13",
  "confidence": true
}
```

Frontend: `MapPanel.flyTo({lat, lng, zoom: 16})`, drops a "site" pin.

### `claims` — claim list extracted from the listing

```jsonc
{
  "claims": [
    {
      "id": "c-01",
      "type": "walk_time" | "drive_time" | "quiet" | "amenity" | "view" | "school_access",
      "raw_text": "5 min walk to Bishan MRT",
      "parsed": { /* type-specific, see audit-agent.md */ }
    }
  ]
}
```

Frontend shows the claims as placeholder cards awaiting verdicts.

### `progress` — a claim is about to be verified (live network call pending)

```jsonc
{
  "current": 3,
  "total": 6,
  "claim_id": "c-03",
  "claim_type": "quiet",
  "claim_text": "Located on a quiet residential road"
}
```

Fired BEFORE each verdict. Lets the UI show a spinner + "Verifying 3 / 6 ·
quiet · quiet residential road" while the REST call is in flight (1-3s).
The corresponding `verdict` event arrives right after and closes the row.

---

### `verdict` — one claim verified

```jsonc
{
  "claim_id": "c-01",
  "verdict": "true" | "overstated" | "false" | "misleading" | "unverifiable",
  "finding": "Real walk: 14.2 min to Bishan MRT. Listing claimed 5 min.",
  "delta": 1.84,                         // (real - claimed) / claimed, null if N/A
  "evidence": {                          // type-specific; see below
    "destination": "Bishan MRT",
    "destination_latlng": [1.3518, 103.8481],
    "real_minutes": 14.2,
    "claimed_minutes": 5
  },
  "endpoints_called": ["search", "navigation"],
  "map_events": [                        // structured events for MapPanel
    {"op": "pin", "lat": 1.3518, "lng": 103.8481, "color": "#a97629", "label": "Bishan MRT"},
    {"op": "route", "from": [1.3519, 103.8481], "to": [1.3518, 103.8481],
     "profile": "walking", "color": "#a97629", "polyline": "wkopAsimaeE..."}
  ]
}
```

Frontend:
1. Finds the claim card by `claim_id`, stamps the verdict colour + text.
2. Increments the "endpoints pinged" counter by `endpoints_called.length`.
3. Runs each `map_events[i]` against `MapPanel` imperative API.

### `map_event` — standalone map update not tied to a verdict

```jsonc
{
  "op": "pin" | "route" | "flyTo" | "streetview" | "clear",
  // op-specific payload (see below)
}
```

Used during the demo for: initial fly-to after geocode, opening a street-view
viewer, clearing markers on new audit.

### `score` — the final 0-100

```jsonc
{
  "score": 34,
  "breakdown": {
    "true": 1,
    "overstated": 2,
    "misleading": 1,
    "false": 2,
    "unverifiable": 0
  },
  "audit_id": "audit_1745500000_bishan",
  "endpoints_used": ["search", "navigation", "nearby", "street_view", "incidents_bbox"]
}
```

Populates the Honesty Index card and persists `audit_id` so the Wayang flip can
POST to `/rewrite` with it.

### `done` — terminal event for this stream

```jsonc
{
  "ok": true,
  "duration_ms": 7423
}
```

### `error` — stream-level error

```jsonc
{
  "message": "Playwright scrape timed out after 15s",
  "recoverable": true
}
```

Frontend shows in terminal, does not kill the connection if `recoverable: true`
(the backend can emit more `status`/`verdict` events after).

---

## Map event operations (`map_events[*].op`)

| op | payload | frontend action (raw MapLibre v5) |
|---|---|---|
| `pin` | `{lat, lng, color, label}` | `new maplibregl.Marker({color}).setLngLat([lng,lat]).setPopup(new maplibregl.Popup().setText(label)).addTo(map)` |
| `route` | `{from: [lat,lng], to: [lat,lng], profile, color, polyline}` | Decode polyline6 → GeoJSON LineString, add source + line layer |
| `flyTo` | `{lat, lng, zoom}` | `map.flyTo({center: [lng,lat], zoom, speed: 1.2})` |
| `streetview` | `{lat, lng, photo_urls: [str], heading}` | Open an overlay panel showing `photo_urls[0]`; not a native widget |
| `clear` | `{what: "routes" | "pins" | "all"}` | Remove relevant sources/layers/markers |

**Coordinate convention everywhere in this contract: `[lat, lng]`.** The backend
converts to MapLibre's `[lng, lat]` order ONLY inside `map_events` payloads for
`flyTo`. All other payloads are `[lat, lng]` and the frontend swaps to MapLibre
order at the call site.

---

## Canned replay

`POST /audit/stream` with `{"fixture": "demo_bishan", "canned": true}` streams a
pre-recorded event log from `backend/fixtures/canned/demo_bishan.jsonl`, one
event per line, honouring original inter-event timestamps. Same events, same
order, same visual output — but offline.

---

## Endpoint summary

- `POST /audit/stream` → `text/event-stream` of events above.
- `POST /rewrite` body `{"audit_id": "..."}` → JSON `{title, copy, photo_brief, predicted_score}`.
- `POST /warmup` → pre-fetches all fixture data to disk cache. Returns `{ok: true, cached: [...]}`.
- `GET /health` → `{ok: true, has_key: bool, mcp_reachable: bool}`.
- `GET /map/codegen-reference.html` → static file, the pitch-slide artifact.

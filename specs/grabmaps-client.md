# Spec: GrabMaps Client

**Status:** Frozen. Defines what `backend/maps/` must provide and the live-verified
response shapes we parse against.

Two surfaces, one facade:

- `maps.http_client.GrabMapsHTTP` — direct REST via `httpx.AsyncClient`. All audit
  evidence comes from here.
- `maps.mcp_client.GrabMapsMCP` — streamable-HTTP JSON-RPC to `maps.grab.com/api/v1/mcp`.
  Used for ONE visible call per demo run (address `search`) so the terminal log
  shows a real MCP round-trip. Optionally used at dev time for codegen artefacts.
- `maps.facade.GrabMaps` — composes both, owns the disk cache.

Auth: `Authorization: Bearer $GRAB_MAPS_API_KEY` on every request to maps.grab.com.
`X-API-Key` does NOT work (verified; returns 401).

Base URL: `https://maps.grab.com`.

## REST endpoints used

Each entry documents the verified-live response shape (April 2026). Parse
defensively: several endpoints nest fields under `location`, and several ignore
query-string `limit`.

### `GET /api/v1/maps/poi/v1/search` → places

Params: `keyword`, `country` (required, `SGP`), `location` (`"lat,lng"`, optional),
`limit` (ignored server-side — see docs/bug-hunter.md BUG-05; always slice client-side).

Response:

```jsonc
{
  "is_confident": true,
  "places": [
    {
      "name": "Bishan MRT",
      "formatted_address": "200 Bishan, Singapore, 579827",
      "location": { "latitude": 1.3518553, "longitude": 103.8481119 },
      "category": "commercial building",
      "business_type": "station",
      "city": "Singapore City",
      "country_code": "SGP",
      "poi_id": "IT.2KBW91ETVY25Y",
      "postcode": "579827",
      "street": "Bishan",
      "opening_hours": "{}",   // NB: a JSON-encoded STRING, not an object
      "time_zone": { "name": "Asia/Singapore", "offset": 28800 }
    }
  ],
  "uuid": "7d8ccaf6-..."
}
```

**Parser contract:**
```python
Place(
    name=p["name"],
    address=p.get("formatted_address", ""),
    lat=p["location"]["latitude"],
    lng=p["location"]["longitude"],
    category=p.get("category"),
    business_type=p.get("business_type"),
    poi_id=p.get("poi_id"),
    raw=p,
)
```

### `GET /api/v1/maps/eta/v1/direction` → route

Params: `coordinates` (required; repeated `coordinates=lng,lat` query pairs OR
`;`-joined `"lng,lat;lng,lat"` — the scaffold uses the `;` form; both work),
`profile` (`walking` | `driving` | `cycling` | `motorcycle` | `tricycle`),
`overview` (`simplified` | `full` | `no`, default `simplified`), `geometries`
(`polyline6` default, `polyline`, `no`), `steps` (bool).

**Coordinate order: `lng,lat` (not `lat,lng`) in the query string.** Scaffold bug
was here — it used `lng,lat` correctly via a join, but the parser mishandled the
response.

Response:

```jsonc
{
  "code": "ok",
  "routes": [
    {
      "distance": 2349.465,              // metres
      "duration": 1901.1,                // seconds
      "geometry": "wkopAsimaeE...",      // polyline6
      "legs": [{"distance": 2349.465, "duration": 1901.1}]
    }
  ]
}
```

**Parser contract:**
```python
Route(
    distance_m=r["distance"],
    duration_s=r["duration"],
    geometry=r.get("geometry"),
    profile=profile,
    raw=r,
)
```

### `GET /api/v1/maps/place/v2/nearby` → nearby places (amenity check)

Params: `latitude`, `longitude`, `radius_km` (km, NOT metres), `limit`, optional
`keyword` to filter by category-ish string.

Response shape: `{ "places": [...] }` with the same per-place shape as `search`.

### `GET /api/v1/traffic/real-time/bbox` → traffic samples

Params: `nw_lat`, `nw_lng`, `se_lat`, `se_lng`, optional `road_class`
(comma-separated 1-8), optional `congestion_level` (comma-separated 0-5).
Requires `linkReference=GRAB_WAY` per the `generate_builder_map_code`
documentation.

### `GET /api/v1/traffic/incidents/bbox` → incidents

Params: `nw_lat`, `nw_lng`, `se_lat`, `se_lng`. Response: `{ incidents: [...] }`
or `{ data: [...] }` — handle both keys.

### `GET /api/v1/openstreetcam-api/2.0/photo/` → street-view photos

Params: `lat`, `lng`, `radius` (m), `limit`, `orderBy=distance`,
`orderDirection=asc`, `projection=SPHERE`.

Response (verified shape):

```jsonc
{
  "status": { "httpCode": 200, "apiCode": 600 },
  "result": {
    "data": [
      {
        "id": "1865261337",
        "lat": "1.351835",               // NB: strings
        "lng": "103.848072",             // NB: strings
        "heading": "192.12",             // NB: string
        "fieldOfView": "360",
        "fileurl":    "https://storage13.openstreetcam.org/files/photo/.../{{sizeprefix}}/8320233_....jpg",
        "fileurlTh":  "https://storage13.openstreetcam.org/files/photo/.../th/...jpg",
        "fileurlLTh": "https://storage13.openstreetcam.org/files/photo/.../lth/...jpg",
        "imageLthUrl":  "https://cdn.kartaview.org/pr:sharp/<base64>",
        "dateAdded": "2023-11-28 07:06:18"
      }
    ]
  }
}
```

Photo URLs are on public CDNs (`storage13.openstreetcam.org`, `cdn.kartaview.org`)
and do NOT require the Bearer token. `fileurl` has a `{{sizeprefix}}` placeholder —
it's meant to be substituted with `th` / `lth` / `proc` on the client. We skip
it and use the already-substituted `fileurlTh` for previews.

**Parser contract:**
```python
Photo(
    id=p["id"],
    lat=float(p["lat"]),
    lng=float(p["lng"]),
    heading=float(p.get("heading", 0)),
    thumb_url=p["fileurlTh"],
    full_url=p["fileurlLTh"],
    cdn_url=p.get("imageLthUrl"),
    date=p.get("dateAdded"),
    raw=p,
)
```

## Tile serving (for the map, not audit)

The React `<MapPanel>` loads MapLibre which then fetches vector tiles. The style
at `/api/style.json` advertises tile URLs that **403**. See BUG-02 for details.

Client-side fix in `MapPanel.jsx`:

```js
const transformRequest = (url, resourceType) => {
  let rewritten = url;
  // Fix BUG-02: rewrite tile URL path
  if (rewritten.includes('maps.grab.com/maps/tiles/')) {
    rewritten = rewritten.replace(
      'maps.grab.com/maps/tiles/',
      'maps.grab.com/api/v1/maps/tiles/'
    );
  }
  // Inject auth for every maps.grab.com request
  if (rewritten.includes('maps.grab.com')) {
    return { url: rewritten, headers: { Authorization: `Bearer ${API_KEY}` } };
  }
  return { url };
};
```

## MCP client

Streamable-HTTP JSON-RPC. `initialize` once, reuse `mcp-session-id` header for
subsequent calls. Accept both `application/json` and `text/event-stream` on
responses.

```python
await mcp.initialize()
result = await mcp.call_tool("search", {"keyword": "Bishan MRT", "country": "SGP", "limit": 1})
```

`call_tool` parses the SSE wrapper and returns the `result.content[0].text`
JSON-decoded.

## Disk cache

Both clients share `GM_CACHE_DIR` (default `.cache/grabmaps/`). Key:
`sha256({transport, path, params}) → .json`. `bust=True` forces a re-fetch. Cache
entries are stored with their original response body verbatim.

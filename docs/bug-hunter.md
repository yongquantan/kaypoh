# GrabMaps API Bug Hunter Log

Real issues hit while building Ground Truth / Kaypoh against `maps.grab.com`.
Each entry is an independent candidate for the Hackathon Bug Hunter prize.

Format per bug: **Summary · Severity · Repro · Observed · Expected · Workaround.**

---

## BUG-01 — MCP codegen leaks internal service URLs

**Severity:** High (makes codegen output unusable in production clients without manual rewriting).

**Repro.** Call MCP tool `grabmaps_library_vibe_snippet` with `integration=maplibre_standalone`, `container_id=map`, `task=init`, any coords.

**Observed.** Returned `code` string contains:

```
<link href="https://b2c-map-service.grab.prd.mesh.internal/assets/css/maplibre-gl.css" ...>
<script src="https://b2c-map-service.grab.prd.mesh.internal/assets/js/maplibre-gl.js"></script>
style: 'https://b2c-map-service.grab.prd.mesh.internal/api/style.json'
```

`b2c-map-service.grab.prd.mesh.internal` is not resolvable from a browser / public
client — pasting the snippet as-is produces 3 network errors.

**Expected.** Returned code should reference the public host (`https://maps.grab.com`),
or at minimum honour the `base_url`, `library_url`, `maplibre_js_url`,
`maplibre_css_url`, `style_url` optional inputs as overrides — **it already accepts
them** but defaults to the mesh URL.

**Workaround.** Either pass every override on every call, or post-process the returned
string to replace the mesh host.

---

## BUG-02 — `/api/style.json` advertises tile URLs that 403

**Severity:** High (breaks MapLibre OOTB against the documented style URL).

**Repro.**

```bash
K=$GRAB_MAPS_API_KEY
# 1. Fetch the style
curl -s "https://maps.grab.com/api/style.json" -H "Authorization: Bearer $K" \
  | jq '.sources.grabmaptiles.tiles'
# → [ "https://maps.grab.com/maps/tiles/v2/vector/karta-v3/{z}/{x}/{y}.pbf" ]

# 2. Fetch a tile from the advertised URL (with auth)
curl -i "https://maps.grab.com/maps/tiles/v2/vector/karta-v3/11/1614/1022.pbf" \
  -H "Authorization: Bearer $K"
# → 403

# 3. The same tile at a DIFFERENT path (under /api/v1/) works
curl -i "https://maps.grab.com/api/v1/maps/tiles/v2/vector/karta-v3/11/1614/1022.pbf" \
  -H "Authorization: Bearer $K"
# → 200, 2281 bytes of protobuf
```

**Observed.** Style JSON points at a tile host path that rejects every auth scheme
(Bearer, `X-API-Key`, query-string `api_key`, with and without `Referer`).

**Expected.** Either (a) the style should advertise the `/api/v1/`-prefixed tile
URLs that the platform actually serves, or (b) the `/maps/tiles/...` path should
accept the same Bearer token as the rest of the API.

**Workaround.** Use MapLibre's `transformRequest` to rewrite every tile request URL
from `https://maps.grab.com/maps/tiles/...` → `https://maps.grab.com/api/v1/maps/tiles/...`
AND inject the `Authorization` header. Code in `frontend/src/components/MapPanel.jsx`.

---

## BUG-03 — MCP tool outputs contain unresolved `<no value>` template placeholders

**Severity:** Medium (every integrator needs to know about it; blocks MCP-returned URL from being usable as-is).

**Repro.**

```
call mcp__grab-maps-playground__get_tile with {z:14, x:12865, y:8389, type:"vector"}
```

**Observed.**

```json
{ "success": true, "tile_url": "<no value>/api/v1/tiles/vector/14/12865/8389" }
```

`<no value>` is a Go template leak (e.g. `{{ .BaseURL }}` against a nil field).

Same bug in `get_street_view`:

```
call mcp__grab-maps-playground__get_street_view with {lat:1.3518, lng:103.8481}
```

→ returns `"endpoint": "<no value>/api/v1/openstreetcam-api/..."`.

**Expected.** Either a resolved absolute URL (`https://maps.grab.com/...`) or a
relative path with the base documented. Never an unrendered template.

**Workaround.** Treat the `*_url` / `endpoint` fields as path-only and prefix
`https://maps.grab.com` manually.

---

## BUG-04 — `get_tile` MCP tool points at a path that 404s

**Severity:** Medium (paired with BUG-03, it sends integrators to a dead path).

**Repro.** After stripping the `<no value>` (BUG-03), the path the MCP returns is
`/api/v1/tiles/vector/{z}/{x}/{y}`:

```bash
curl -i "https://maps.grab.com/api/v1/tiles/vector/14/12865/8389" -H "Authorization: Bearer $K"
# → HTTP 404
```

**Expected.** The working path is `/api/v1/maps/tiles/v2/vector/karta-v3/{z}/{x}/{y}.pbf`
(same as BUG-02). The MCP tool should either return that, or be documented as
deprecated.

---

## BUG-05 — `search` ignores `limit`

**Severity:** Low (over-returns cause bandwidth + parsing work).

**Repro.** MCP `search` with `{keyword: "Bishan MRT Station", country: "SGP", limit: 2}`.

**Observed.** `places` array has **8 entries** — not 2. Every call we've tried
returns the server default regardless of requested limit.

**Expected.** Server truncates to the requested limit.

**Workaround.** Slice client-side.

---

## BUG-06 — `get_street_view` MCP tool is a descriptor, not a fetcher

**Severity:** Medium (misleading tool name for LLM agents; an agent looking at
`get_street_view` reasonably expects photos back).

**Repro.** Call `get_street_view` with `{lat:1.3518, lng:103.8481, radius:200, limit:3}`.

**Observed.** Returns a single-element `photos` array whose sole item is a
**metadata description** of the HTTP endpoint to call — not any photo records.
The actual photos only come back from the direct REST call to
`/api/v1/openstreetcam-api/2.0/photo/`.

**Expected.** Either (a) the MCP tool should proxy the photos through, like
`search` and `navigation` do, or (b) the tool should be renamed
(`describe_street_view_endpoint`) so an agent doesn't dispatch it expecting data.

---

## BUG-07 — style.json tile URL drifted to a third path; old URL now serves 403

**Severity:** Medium (breaks any client whose `transformRequest` was written against BUG-02's original advertised path).

**Repro.**

```bash
K=$GRAB_MAPS_API_KEY
curl -s "https://maps.grab.com/api/style.json" -H "Authorization: Bearer $K" \
  | jq '.sources.grabmaptiles.tiles'
# → [ "https://maps.grab.com/api/maps/tiles/v2/vector/karta-v3/{z}/{x}/{y}.pbf" ]

# The originally-documented (BUG-02) advertised path now 403s, as before:
curl -i "https://maps.grab.com/maps/tiles/v2/vector/karta-v3/12/3277/2037.pbf" \
  -H "Authorization: Bearer $K"
# → 403

# Both currently-live paths return 200 with Bearer:
curl -i "https://maps.grab.com/api/maps/tiles/v2/vector/karta-v3/12/3277/2037.pbf" \
  -H "Authorization: Bearer $K"
# → 200
curl -i "https://maps.grab.com/api/v1/maps/tiles/v2/vector/karta-v3/12/3277/2037.pbf" \
  -H "Authorization: Bearer $K"
# → 200
```

**Observed.** As of Apr 2026 the `style.json` advertises tiles under
`/api/maps/tiles/...` — a THIRD path, different from both the originally
advertised `/maps/tiles/...` (BUG-02) and the workaround `/api/v1/maps/tiles/...`
that BUG-02 recommends. Clients that deployed the BUG-02 workaround
(`replace('/maps/tiles/','/api/v1/maps/tiles/')`) no longer hit the replace
branch because the URL no longer contains `/maps/tiles/` (it contains
`/api/maps/tiles/`). They still end up at a 200-serving path — but only
accidentally, because the new advertised path also works.

**Expected.** Either freeze a single canonical tile URL scheme, or document
the migration in the style. Silent URL drift inside the style makes BUG-02's
workaround stale and future-fragile.

**Workaround.** Our `transformRequest` injects Bearer for ALL maps.grab.com
requests and only rewrites if it sees the legacy `/maps/tiles/` path — which
still matches the BUG-02 case, while letting the new advertised path pass
through untouched. Both variants serve 200 today with Bearer.

---

## BUG-08 — `direction` rejects `;`-joined coordinates; wants repeated query params

**Severity:** Medium (every scaffold that followed the MCP reference's
"coordinates=lng,lat" text gets 400s).

**Repro.**

```bash
K=$GRAB_MAPS_API_KEY
# Semicolon-joined, which the MCP reference doc's example suggests:
curl -i "https://maps.grab.com/api/v1/maps/eta/v1/direction?coordinates=103.85074%2C1.34981%3B103.84811%2C1.35186&profile=walking" -H "Authorization: Bearer $K"
# → 400

# REPEATED coordinates params — works:
curl -i "https://maps.grab.com/api/v1/maps/eta/v1/direction?coordinates=103.85074,1.34981&coordinates=103.84811,1.35186&profile=walking" -H "Authorization: Bearer $K"
# → 200
```

**Expected.** Either both forms accepted, or the MCP reference doc's
"coordinates=lng,lat" phrasing should make the multi-waypoint format
unambiguous.

**Workaround.** Always issue repeated `coordinates=lng,lat` query params,
one per waypoint. Implemented in `backend/maps/http_client.py::direction`.

---

## BUG-09 — `traffic/incidents/bbox` rejects `nw_lat/nw_lng/se_lat/se_lng`

**Severity:** Medium (naming mismatch between MCP tool args and the
underlying REST endpoint).

**Repro.**

```bash
K=$GRAB_MAPS_API_KEY

# MCP tool accepts nw_lat/nw_lng/se_lat/se_lng (works through MCP).
# Direct REST with the same names:
curl "https://maps.grab.com/api/v1/traffic/incidents/bbox?nw_lat=1.355&nw_lng=103.846&se_lat=1.345&se_lng=103.855" -H "Authorization: Bearer $K"
# → 400 {"target":"","reason":"invalid_argument","message":"invalid request: invalid lat/lon"}

# The same bbox with lat1/lat2/lon1/lon2 + linkReference:
curl -i "https://maps.grab.com/api/v1/traffic/incidents/bbox?lat1=1.355&lat2=1.345&lon1=103.846&lon2=103.855&linkReference=GRAB_WAY" -H "Authorization: Bearer $K"
# → 200
```

**Expected.** Either the REST endpoint accepts the `nw_*`/`se_*` shape its
MCP wrapper advertises, or the MCP docs note the rename at the REST boundary.

**Workaround.** Map `nw_lat/nw_lng/se_lat/se_lng` → `lat1/lat2/lon1/lon2`
at the REST boundary and always include `linkReference=GRAB_WAY`. Implemented
in `backend/maps/http_client.py::incidents_bbox`.

---

## BUG-10 — `/api/v1/maps/place/v2/nearby` returns 400 for our app key; MCP works

**Severity:** High (forces every client to go through MCP for nearby — no
direct REST path).

**Repro.**

```bash
K=$GRAB_MAPS_API_KEY

# Direct REST — every documented param shape 400s with "invalid argument"
# regardless of latitude/longitude/radius_km naming, whether keyword is
# present or absent, and whether we try limit=20 or limit=1.
curl "https://maps.grab.com/api/v1/maps/place/v2/nearby?latitude=1.3498&longitude=103.8507&radius_km=1.0&limit=5" -H "Authorization: Bearer $K"
# → 400 {"target":"","reason":"invalid_argument","message":"invalid argument"}

# Meanwhile the MCP `search_nearby_pois` tool with the same lat/lng/radius_km
# returns 5 Bishan POIs correctly (Cold Storage, Bishan CC, etc.).
```

**Observed.** The underlying REST endpoint rejects every parameter shape we've
tried with our `bm_…` app key, while the MCP's `search_nearby_pois` tool —
which per its own tool description wraps this same endpoint — works.
Suggests our key lacks the scope the MCP's internal server has, but the
error message ("invalid argument") is misleading if so.

**Expected.** Either the REST endpoint should work for app keys, or the 400
should say "scope denied" and direct the caller to `create_api_key` with a
different permission set.

**Workaround.** Route all `nearby` calls through the MCP `search_nearby_pois`
tool from the backend. Implemented in `backend/maps/facade.py::nearby`.
Filter by category client-side (the API has no server-side category filter
per the MCP tool description).

---

## BUG-11 — `generate_builder_map_code` `setup_steps` references unrendered `<no value>`

**Severity:** Low (only shown in human-facing setup prose, not the `html_code`).

**Repro.** Call the MCP `generate_builder_map_code` with any valid params.

**Observed.** The `html_code` uses a clean `BASE_URL_HERE` placeholder (good!)
but the returned `setup_steps` string still contains:

> "Replace '<no value>' with your actual API server base URL (must end with /)"
> "Or visit <no value>/admin and create one in the dashboard"

The `<no value>` Go template leak was fixed in one code path but not the other.

**Expected.** Setup steps should reference the same placeholder the code uses,
OR both should be resolved to the public host.

---

## Candidates to investigate

- Does `navigation` respect `profile=cycling` in SG? (MCP schema advertises it).
- Are the "traffic real-time" bbox payloads useful at hackathon-day zoom levels,
  or sparse?
- Does `search_nearby_pois` accept a `category` filter, or only `keyword`?
  (Scaffold's `grabmaps.py` sends `keyword=category` — worth verifying.)

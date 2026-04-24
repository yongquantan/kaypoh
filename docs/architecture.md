# Architecture

Ground Truth / Kaypoh is a two-mode property-listing intel tool. **Kaypoh** audits
listings against GrabMaps evidence; **Wayang** rewrites them defensibly.

Target: GrabMaps API Hackathon, Singapore, Jun 2026.

## High-level

```
                                ┌──────────────────────────┐
 PropertyGuru / fixture  ────▶  │  FastAPI backend         │
 URL                            │                          │
                                │  listing.py  (Playwright │
                                │              + Claude)   │
                                │  agent.py    (rule-based │
                                │              dispatch)   │
                                │  maps/       (REST + MCP)│
                                │  score.py    (det. 0–100)│
                                └─────────┬────────────────┘
                                          │ SSE (structured)
                                          ▼
                                ┌──────────────────────────┐
                                │  Kaypoh React SPA        │
                                │                          │
                                │  <MapPanel/>   MapLibre5 │
                                │  <Terminal/>   status    │
                                │  <ClaimCard/>  verdicts  │
                                │  <Honesty/>    score     │
                                │  <Wayang/>     rewrite   │
                                └──────────────────────────┘
                                          │
                                          │ Bearer + transformRequest
                                          ▼
                                ┌──────────────────────────┐
                                │   maps.grab.com          │
                                │   · /api/v1/maps/poi     │
                                │   · /api/v1/maps/eta     │
                                │   · /api/v1/maps/place   │
                                │   · /api/v1/traffic/...  │
                                │   · /api/v1/openstreet…  │
                                │   · /api/v1/maps/tiles…  │
                                │   · /api/v1/mcp (init+1) │
                                └──────────────────────────┘
```

## Domain map

| Domain | Code | Spec |
|---|---|---|
| SSE protocol | `backend/main.py::audit_stream`, `src/hooks/useAuditStream.js` | [specs/sse-contract.md](../specs/sse-contract.md) |
| GrabMaps client | `backend/maps/` | [specs/grabmaps-client.md](../specs/grabmaps-client.md) |
| Audit agent | `backend/agent.py`, `backend/score.py` | [specs/audit-agent.md](../specs/audit-agent.md) |
| Listing extraction | `backend/listing.py`, `backend/prompts/` | [specs/listing-extractor.md](../specs/listing-extractor.md) |
| Map rendering | `src/components/MapPanel.jsx` | [specs/grabmaps-client.md](../specs/grabmaps-client.md) §tiles |
| Seller rewrite | `backend/agent.py::rewrite_for_seller` | [specs/audit-agent.md](../specs/audit-agent.md) §rewrite |

## Directory

```
~/Projects/kaypoh/
├── AGENTS.md                             slim map for agents
├── README.md                             existing, minor updates
├── TODO.md                               phase checklist
├── docs/
│   ├── architecture.md                   this file
│   ├── bug-hunter.md                     accumulating API friction
│   └── codegen-reference.html            generated via MCP, for pitch slide
├── specs/                                source of truth for contracts
├── backend/                              FastAPI + async httpx + Claude
│   ├── main.py
│   ├── agent.py
│   ├── listing.py
│   ├── score.py
│   ├── prompts/
│   ├── maps/
│   │   ├── __init__.py
│   │   ├── http_client.py
│   │   ├── mcp_client.py
│   │   └── facade.py
│   ├── fixtures/
│   │   ├── demo_bishan.json
│   │   ├── demo_tampines.json
│   │   ├── demo_tiong_bahru.json
│   │   └── canned/                       recorded SSE streams per fixture
│   ├── tests/
│   └── requirements.txt
├── src/                                  existing React app
│   ├── App.jsx                           rewired to SSE
│   ├── components/                       new split-out components
│   │   ├── MapPanel.jsx
│   │   ├── Terminal.jsx
│   │   ├── ClaimCard.jsx
│   │   └── WayangView.jsx
│   └── hooks/
│       └── useAuditStream.js
├── .agents/
│   └── workflows/
│       └── implement-and-verify.md
├── package.json                          + maplibre-gl@^5
├── vite.config.js
└── .env.example                          GRAB_MAPS_API_KEY, OPENAI_API_KEY, MCP_BEARER
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11 · FastAPI · httpx · uvicorn | Hackathon scaffold already in Python; async + SSE friendly |
| LLM | OpenAI SDK · `gpt-5` (fallback `gpt-5-mini`) | Claim extraction + seller rewrite only |
| Scraping | Playwright (chromium) | Fragile, demo uses fixtures |
| Frontend | React 19 · Vite 8 · MapLibre v5 | Kaypoh's existing stack |
| Maps | MapLibre v5 against GrabMaps style.json, tile-URL rewrite via `transformRequest` | See BUG-02 |
| MCP | `mcp_1777006996_…` Bearer, streamable-HTTP JSON-RPC | One visible call (`search`) per audit |
| Cache | Disk JSON keyed by sha256(path+params) | Demo-day resilience |
| Deploy | Localhost (hackathon). Future: Modal / Railway | Out of scope |

## Conventions

- **Coordinate order in our code:** `[lat, lng]` tuples. Swap to `[lng, lat]`
  at exactly two call sites: the `direction` endpoint query string, and
  MapLibre's `setCenter` / `flyTo`. The SSE contract is `[lat, lng]` everywhere
  except inside `map_events[*].op === "flyTo"`.
- **Auth injection:** every request to `maps.grab.com` carries
  `Authorization: Bearer $GRAB_MAPS_API_KEY`. `X-API-Key` is a 401.
- **Disk cache:** `.cache/grabmaps/*.json`. Safe to delete; audit re-runs
  repopulate. Demo should run from a warmed cache.
- **Errors:** every network call is wrapped; verifier exceptions become
  `verdict: unverifiable` events, never kill the stream.
- **No LLM in the verification hot path.** LLM only on the two boundaries
  (extract, rewrite). See `specs/audit-agent.md` for the rationale.

## Where the claims are load-bearing

The pitch rests on this table. Every row is a GrabMaps endpoint call per
audit; 8 distinct endpoints, 5 of 7 tool families (admin + styles excluded).

| Listing claim | GrabMaps call(s) | File |
|---|---|---|
| Address geocode | `search` | `agent.py::geocode_listing` |
| "X min walk to Y" | `search` + `direction(walking)` | `agent.py::verify_walk_time` |
| "X min drive to CBD" | `direction(driving)` + `traffic/real-time/bbox` | `agent.py::verify_drive_time` |
| "Near amenities" | `place/v2/nearby` | `agent.py::verify_amenity` |
| "Unobstructed view" | `openstreetcam-api/2.0/photo/` | `agent.py::verify_view` |
| "Quiet road" | `traffic/incidents/bbox` | `agent.py::verify_quiet` |
| "Near good schools" | `search(school)` + `direction(walking)` | `agent.py::verify_school_access` |
| Pitch slide | `generate_builder_map_code` (dev-time, once) | `docs/codegen-reference.html` |
| Visible live MCP call | `search` via MCP (one per audit) | `agent.py::geocode_listing` |

## Live vs. pre-captured — what actually runs on stage

The demo runs **fully live** by default. The only pre-captured assets are
ones that physically cannot be fetched live at demo time. Everything else
is a real API call.

| Step | Default path | Pre-captured fallback |
|---|---|---|
| PropertyGuru scrape | Fixture JSON | — (Cloudflare 403s headless Chromium; see `docs/playwriter-evaluation.md`) |
| Claim extraction (GPT) | **Live** — `gpt-5` via OpenAI SDK, temp=0, `response_format=json_object` | Pre-authored claims in the fixture JSON (used only when no `OPENAI_API_KEY` or the LLM call fails) |
| Address geocode | **Live MCP call** to `search` tool | REST `search` as fallback if MCP is 503 |
| Walk / drive time | **Live REST** `/api/v1/maps/eta/v1/direction` per claim | None — demo hard-depends |
| Incident density | **Live REST** `/api/v1/traffic/incidents/bbox` | None |
| Street-view photos | **Live REST** `/api/v1/openstreetcam-api/2.0/photo/` | None — 504 here falls through to "unverifiable" verdict |
| Nearby amenities | **Live MCP** `search_nearby_pois` (BUG-10 blocks REST for our key) | None |
| Score | Deterministic Python (not "live" in the API sense) | — |
| Wayang seller rewrite | **Live GPT-5** (fallback `gpt-5-mini`) | — (degrades to an error message) |
| Map tiles + style | **Live vector tiles** from `maps.grab.com`, transformRequest-authed | None |
| `?mode=canned` replay | Off by default | Explicit `{canned: true}` opt-in — byte-for-byte replay of a previously recorded audit. Only for the "WiFi died on stage" escape hatch. |

Which path actually ran on a given audit is reported back on the SSE stream
as a `status` event with tone `success` ("Claude extracted N claims live")
or `warn` ("Claude unavailable — using N pre-authored fixture claims"). The
Kaypoh Terminal component surfaces this so you can see the real path at
a glance during the demo.

## Risks and mitigations (live)

| Risk | Mitigation |
|---|---|
| MCP down on demo day | Everything except geocode is direct REST; geocode falls back to REST if MCP fails. |
| Venue WiFi | `/warmup` pre-populates disk cache; `?canned=true` replays SSE. |
| GPT extraction drift | Temperature 0, `response_format=json_object`, strict prompt, baked fixtures as fallback. |
| Tile URLs 403 | `transformRequest` rewrites path + injects auth. See BUG-02. |
| Tile-auth token leaks | API key only in frontend via Vite env, backend proxies preferred where feasible. |
| PropertyGuru DOM changes | Demo uses fixtures. Live URL is stretch. |

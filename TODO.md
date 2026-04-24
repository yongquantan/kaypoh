# TODO

Phased build for the GrabMaps Hackathon submission.

---

## Phase 1 — Scaffold

- [x] `docs/bug-hunter.md` with BUG-01 through BUG-06
- [x] `specs/sse-contract.md`
- [x] `specs/grabmaps-client.md`
- [x] `specs/audit-agent.md`
- [x] `specs/listing-extractor.md`
- [x] `specs/README.md`
- [x] `docs/architecture.md`
- [x] `AGENTS.md`
- [x] `TODO.md`
- [ ] `.agents/workflows/implement-and-verify.md`

## Phase 2 — Backend bones

- [ ] `backend/__init__.py`, `backend/main.py` FastAPI skeleton with `/health`
- [ ] `backend/maps/__init__.py` package
- [ ] `backend/maps/http_client.py` — REST with CORRECT field parsing per `specs/grabmaps-client.md`
- [ ] `backend/maps/mcp_client.py` — streamable-HTTP JSON-RPC
- [ ] `backend/maps/facade.py` — unified client, disk cache
- [ ] `backend/requirements.txt`
- [ ] Live smoke test of each REST endpoint against real SG coords

## Phase 3 — Claims and fixtures

- [ ] `backend/fixtures/demo_bishan.json` — fattened copy exercising 4–6 claim types
- [ ] `backend/fixtures/demo_tampines.json` — outright deceptive
- [ ] `backend/fixtures/demo_tiong_bahru.json` — honest
- [ ] `backend/prompts/extract_claims.md`
- [ ] `backend/listing.py` — fixture loader + Playwright scrape + Claude extraction
  - Verdict (see `docs/playwriter-evaluation.md`): keep Python Playwright in `listing.py` as the stretch path, but populate the three demo fixtures via the `playwriter-property-guru-temp` reference (dev-time one-shot, extracts from `__NEXT_DATA__`) — Cloudflare 403s anonymous fetches, so fresh headless Chromium is unreliable for live demo.
- [ ] Manual pass: all three fixtures yield 4+ claims with supported types

## Phase 4 — Audit loop

- [ ] `backend/agent.py` — verifier dispatch per `specs/audit-agent.md`
- [ ] `backend/score.py` — deterministic weighted score
- [ ] `backend/main.py::/audit/stream` — SSE emitting all events from `specs/sse-contract.md`
- [ ] `backend/tests/test_audit.py` — fixture-based audit with MCP mocked
- [ ] Three fixtures produce distinct scores in expected bands

## Phase 5 — Wayang rewrite

- [ ] `backend/prompts/rewrite_seller.md`
- [ ] `backend/agent.py::rewrite_for_seller`
- [ ] `backend/main.py::/rewrite`
- [ ] Manual: rewritten copy is readable, no invented facts, `predicted_score` is an int 0–100

## Phase 6 — Frontend map

- [ ] `npm i maplibre-gl@^5`
- [ ] `src/components/MapPanel.jsx` — MapLibre v5, `transformRequest` fix, imperative ref
- [ ] Bishan-centred map renders GrabMaps vector tiles locally
- [ ] Imperative: flyTo, addPin, addRoute, openStreetView, clear

## Phase 7 — Rewire kaypoh to real data

- [ ] `src/hooks/useAuditStream.js` — SSE client, dispatches to React state + MapPanel ref
- [ ] `src/components/Terminal.jsx` extracted from `App.jsx`, consumes `status` events
- [ ] `src/components/ClaimCard.jsx` extracted, consumes `claims` + `verdict` events
- [ ] `HonestyCard` consumes `score` event
- [ ] `WayangView` posts to `/rewrite` on flip
- [ ] End-to-end: fixture chip click → map flies, terminal logs stream, verdicts stamp, score lands

## Phase 8 — Demo hardening

- [ ] `POST /warmup` populates disk cache for all three fixtures
- [ ] `POST /audit/stream` supports `{canned: true}` replay from `fixtures/canned/*.jsonl`
- [ ] Record canned streams for all three fixtures
- [ ] Network off, fixtures still play byte-for-byte

## Phase 9 — Pitch artefacts

- [ ] `docs/codegen-reference.html` — single `generate_builder_map_code` output, committed
- [ ] `docs/bug-hunter.md` cleaned up with reproducible repros (ongoing)
- [ ] `README.md` updated with run instructions and the pitch cheat sheet
- [ ] One backup video recorded of the demo loop

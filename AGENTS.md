# AGENTS.md

Slim map for agents working in this repo. ~100 lines. Everything deep lives in
`docs/` and `specs/`.

## Non-Negotiable Rules

1. **Frozen specs are the contract.** Edits to `specs/sse-contract.md`,
   `specs/grabmaps-client.md`, `specs/audit-agent.md` require same-commit updates
   to both backend and frontend.
2. **No LLM in the verification hot path.** Audit agent is rule-based dispatch.
   LLM only in `listing.py::extract_claims` and `agent.py::rewrite_for_seller`.
3. **Never commit secrets.** `.env` is gitignored. Secrets live in `~/.grab-maps.env`
   (GrabMaps), `OPENAI_API_KEY` in shell env, and the MCP bearer in
   `~/.claude.json`'s `mcpServers` block.
4. **Every bug hit against `maps.grab.com` goes in `docs/bug-hunter.md`**, with a
   curl repro. Bug Hunter is a hackathon prize track — accumulate ruthlessly.

## Repo map

| Path | Purpose |
|---|---|
| `specs/sse-contract.md` | Frozen event shapes between backend and frontend |
| `specs/grabmaps-client.md` | GrabMaps REST + MCP, verified field shapes |
| `specs/audit-agent.md` | Verifier dispatch, scoring thresholds, map events |
| `specs/listing-extractor.md` | Playwright + Claude claim extraction |
| `docs/architecture.md` | High-level architecture + domain map |
| `docs/bug-hunter.md` | Accumulating API friction for the prize submission |
| `docs/codegen-reference.html` | Output of `generate_builder_map_code` — pitch slide artefact |
| `TODO.md` | Phased build checklist |
| `backend/` | FastAPI + httpx + Claude |
| `src/` | React 19 + Vite 8 + MapLibre v5 (kaypoh shell) |
| `.agents/workflows/` | Multi-step workflows worth codifying |

## Commands

| Task | Command |
|---|---|
| Install frontend | `npm install` (root) |
| Install backend | `python -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt` |
| Run backend | `set -a; source ~/.grab-maps.env; set +a; uvicorn backend.main:app --reload --port 8000` |
| Run frontend | `VITE_API_BASE=http://localhost:8000 npm run dev` |
| Lint frontend | `npm run lint` |
| Build frontend | `npm run build` |
| Test backend | `pytest backend/tests` |
| Warmup | `curl -X POST http://localhost:8000/warmup` |

## Environment

| Var | Purpose | Where |
|---|---|---|
| `GRAB_MAPS_API_KEY` | `bm_…` key for maps.grab.com REST + style + tiles | `~/.grab-maps.env`, backend env |
| `OPENAI_API_KEY` | GPT-5 for claim extraction + Wayang rewrite | backend env |
| `MCP_BEARER` | `mcp_…` token for MCP JSON-RPC | backend env (optional; backend falls back to REST if missing) |
| `VITE_GRABMAPS_KEY` | Same value as `GRAB_MAPS_API_KEY`, exposed to the browser for MapLibre tile auth | `.env.local` at repo root |
| `VITE_API_BASE` | Backend base URL for SSE | `.env.local` default `http://localhost:8000` |

## How to work in this repo

1. Read `TODO.md` — find the current phase.
2. Read the spec for whichever domain you're touching (`specs/` index in `specs/README.md`).
3. If your change crosses backend + frontend, update the spec FIRST, then both sides in one commit.
4. Implement against the spec, not from memory.
5. If a GrabMaps call misbehaves, add a `docs/bug-hunter.md` entry before working around it.
6. Run: lint (frontend), pytest (backend), and one manual audit against `demo_bishan`.
7. Update `TODO.md` — check the box.

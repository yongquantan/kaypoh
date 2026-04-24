"""
FastAPI backend for Ground Truth / Kaypoh.

Endpoints (frozen per `specs/sse-contract.md`):

  POST /audit/stream         SSE of {status, listing, geocode, claims,
                             verdict, map_event, score, done, error}
  POST /rewrite              { audit_id } → { title, copy, photo_brief,
                             predicted_score }
  POST /warmup               Pre-populates disk cache for all fixtures.
  GET  /health               { ok, has_key, mcp_reachable }
  GET  /map/codegen-reference.html   Static pitch-slide artefact.

Every SSE event payload includes `t` (float seconds since epoch) and `seq`
(monotonic int starting at 1). Event format is strict:
  event: <type>\\n
  data: <json>\\n
  \\n
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator

# Load .env at repo root if present (gitignored). Lets `uvicorn backend.main:app`
# pick up GRAB_MAPS_API_KEY / OPENAI_API_KEY / MCP_BEARER without a separate
# shell export. Shell-exported values win (override=False).
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .agent import (
    AuditResult,
    audit_listing,
    rewrite_for_seller,
)
from .listing import (
    Claim,
    Listing,
    extract_claims,
    fetch_listing,
    load_fixture,
    load_fixture_by_url,
)
from .maps.facade import GrabMaps
from .scrape import ScrapeAllFailed, scrape_url
from .score import honesty_score, score_breakdown

ROOT_DIR = Path(__file__).parent.parent
DOCS_DIR = ROOT_DIR / "docs"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
CANNED_DIR = FIXTURES_DIR / "canned"

app = FastAPI(title="Kaypoh / Ground Truth", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    url: str | None = None
    fixture: str | None = None
    canned: bool = False


class RewriteRequest(BaseModel):
    audit_id: str


# In-memory store (hackathon scope)
AUDIT_STORE: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------ SSE helpers

def _sse_line(event_type: str, payload: dict[str, Any], seq: int) -> str:
    payload = {**payload, "t": time.time(), "seq": seq}
    return f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"


# ------------------------------------------------------------ basic endpoints


@app.get("/health")
async def health() -> dict[str, Any]:
    mcp_reachable = False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("https://maps.grab.com/api/v1/mcp")
            mcp_reachable = r.status_code < 500
    except Exception:
        mcp_reachable = False
    return {
        "ok": True,
        "has_key": bool(os.environ.get("GRAB_MAPS_API_KEY")),
        "mcp_reachable": mcp_reachable,
    }


@app.get("/map/codegen-reference.html")
async def codegen_reference() -> Any:
    path = DOCS_DIR / "codegen-reference.html"
    if not path.exists():
        raise HTTPException(404, "codegen reference not generated yet")
    return FileResponse(path)


@app.post("/warmup")
async def warmup() -> dict[str, Any]:
    """Pre-fetch the expensive calls for every committed fixture.

    Best-effort: if the network is unavailable, individual fixtures fail
    quietly. Returns which fixtures we managed to warm.
    """
    cached: list[str] = []
    fixtures = [p.stem for p in FIXTURES_DIR.glob("*.json")]
    for name in fixtures:
        try:
            listing = load_fixture(name)
        except Exception:
            continue
        try:
            async with GrabMaps() as gm:
                places = await gm.search(
                    listing.address or listing.title, country="SGP", limit=1
                )
                if places:
                    origin = (places[0].lat, places[0].lng)
                    # Cheap primer: one nearby + one incidents lookup
                    try:
                        await gm.nearby(origin[0], origin[1], radius_km=1.0, limit=5)
                    except Exception:
                        pass
                    try:
                        await gm.incident_density(origin[0], origin[1], 500)
                    except Exception:
                        pass
                    try:
                        await gm.street_view(origin[0], origin[1], radius=200, limit=3)
                    except Exception:
                        pass
            cached.append(name)
        except Exception:
            continue
    return {"ok": True, "cached": cached}


# ------------------------------------------------------------ audit stream


async def _canned_stream(fixture: str) -> AsyncIterator[str]:
    path = CANNED_DIR / f"{fixture}.jsonl"
    if not path.exists():
        seq_ctr = itertools.count(1)
        yield _sse_line(
            "error",
            {"message": f"No canned stream for {fixture}", "recoverable": False},
            next(seq_ctr),
        )
        return
    prev_t: float | None = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec.get("event", "status")
            data = rec.get("data", {})
            cur_t = data.get("t")
            if prev_t is not None and cur_t is not None:
                delay = max(0.0, min(2.0, cur_t - prev_t))
                if delay:
                    await asyncio.sleep(delay)
            prev_t = cur_t
            yield f"event: {ev}\ndata: {json.dumps(data, default=str)}\n\n"


async def _live_stream(req: AuditRequest) -> AsyncIterator[str]:
    seq_gen = itertools.count(1)

    def emit(ev: str, data: dict[str, Any]) -> str:
        return _sse_line(ev, data, next(seq_gen))

    start = time.time()
    try:
        if req.fixture:
            yield emit(
                "status",
                {
                    "stage": "scraping",
                    "message": f"Loading fixture: {req.fixture}",
                    "tone": "muted",
                },
            )
            listing = load_fixture(req.fixture)
        else:
            # Path B: live scrape chain. scrape_url pushes status events into
            # a queue which we drain in real time so the UI narrates each
            # attempt as it happens.
            status_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_status(stage: str, message: str, tone: str = "muted") -> None:
                await status_queue.put(
                    {"stage": stage, "message": message, "tone": tone}
                )

            scrape_task = asyncio.create_task(
                scrape_url(req.url or "", on_status)
            )
            # Interleave: yield each status, then check if scrape is done.
            while True:
                try:
                    status_payload = await asyncio.wait_for(
                        status_queue.get(), timeout=0.15
                    )
                    yield emit("status", status_payload)
                except asyncio.TimeoutError:
                    if scrape_task.done():
                        break

            # Drain any queued statuses that raced past the loop
            while not status_queue.empty():
                yield emit("status", status_queue.get_nowait())

            try:
                listing = scrape_task.result()
            except ScrapeAllFailed as e:
                yield emit(
                    "status",
                    {
                        "stage": "scraping",
                        "message": (
                            "Both scrapers failed. Falling back to a "
                            f"matching fixture… ({e})"
                        ),
                        "tone": "warn",
                    },
                )
                listing = load_fixture_by_url(req.url or "")
                yield emit(
                    "status",
                    {
                        "stage": "scraping",
                        "message": f"Replaying fixture: {listing.url}",
                        "tone": "warn",
                    },
                )

        yield emit("listing", listing.to_dict())

        yield emit(
            "status",
            {"stage": "extracting", "message": "Parsing claims with GPT-5…"},
        )
        source = "empty"
        try:
            listing, claims, source = await extract_claims(listing)
        except Exception as e:
            yield emit(
                "status",
                {
                    "stage": "extracting",
                    "message": f"Claim extraction failed: {e}",
                    "tone": "danger",
                },
            )
            claims = []

        if source == "llm":
            yield emit(
                "status",
                {
                    "stage": "extracting",
                    "message": f"GPT-5 extracted {len(claims)} claims live.",
                    "tone": "success",
                },
            )
        elif source == "baked":
            yield emit(
                "status",
                {
                    "stage": "extracting",
                    "message": (
                        f"LLM unavailable — using {len(claims)} pre-authored "
                        "fixture claims (safety net)."
                    ),
                    "tone": "warn",
                },
            )

        yield emit(
            "claims",
            {"claims": [asdict(c) for c in claims]},
        )

        yield emit(
            "status",
            {
                "stage": "geocoding",
                "message": "Geocoding via MCP (one visible round-trip)…",
            },
        )

        yield emit(
            "status",
            {
                "stage": "auditing",
                "message": "Cross-checking against GrabMaps…",
                "tone": "muted",
            },
        )

        audits: list[AuditResult] = []
        total_claims = len(claims)
        async with GrabMaps() as gm:
            async for item in audit_listing(listing, claims, gm=gm):
                if isinstance(item, dict) and item.get("_type") == "progress":
                    claim = item.get("claim")
                    idx = item.get("index", 0)
                    if claim is not None:
                        yield emit(
                            "progress",
                            {
                                "current": idx,
                                "total": total_claims,
                                "claim_id": claim.id,
                                "claim_type": claim.type,
                                "claim_text": claim.raw_text,
                            },
                        )
                    continue
                if isinstance(item, dict) and item.get("_type") == "geocode":
                    origin = item.get("origin")
                    meta = item.get("meta") or {}
                    if origin:
                        yield emit(
                            "geocode",
                            {
                                "lat": origin[0],
                                "lng": origin[1],
                                "label": meta.get("label", ""),
                                "confidence": bool(meta.get("confidence", True)),
                            },
                        )
                        # Fly the map there as a standalone map_event
                        yield emit(
                            "map_event",
                            {
                                "op": "flyTo",
                                "lat": origin[0],
                                "lng": origin[1],
                                "zoom": 16,
                            },
                        )
                    else:
                        yield emit(
                            "status",
                            {
                                "stage": "geocoding",
                                "message": "Address could not be geocoded.",
                                "tone": "danger",
                            },
                        )
                    continue
                assert isinstance(item, AuditResult)
                audits.append(item)
                yield emit(
                    "verdict",
                    {
                        "claim_id": item.claim.id,
                        "verdict": item.verdict,
                        "finding": item.grabmaps_finding,
                        "delta": item.delta,
                        "evidence": item.evidence,
                        "endpoints_called": item.endpoints_called,
                        "map_events": item.map_events,
                    },
                )
                # Small visible stagger so UI stamps in
                await asyncio.sleep(0.3)

        score = honesty_score(audits)
        breakdown = score_breakdown(audits)
        audit_id = f"audit_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        AUDIT_STORE[audit_id] = {
            "listing": listing.to_dict(),
            "audits": [
                {
                    "claim": asdict(a.claim),
                    "verdict": a.verdict,
                    "finding": a.grabmaps_finding,
                    "delta": a.delta,
                    "evidence": a.evidence,
                    "endpoints_called": a.endpoints_called,
                    "map_events": a.map_events,
                }
                for a in audits
            ],
            "score": score,
        }
        endpoints_used = sorted({ep for a in audits for ep in a.endpoints_called})
        yield emit(
            "score",
            {
                "score": score,
                "breakdown": breakdown,
                "audit_id": audit_id,
                "endpoints_used": endpoints_used,
            },
        )
        yield emit(
            "done",
            {"ok": True, "duration_ms": int((time.time() - start) * 1000)},
        )
    except Exception as e:
        yield emit("error", {"message": f"{type(e).__name__}: {e}", "recoverable": False})


@app.post("/audit/stream")
async def audit_stream(req: AuditRequest) -> StreamingResponse:
    if not req.url and not req.fixture:
        raise HTTPException(400, "Need url or fixture")

    generator: AsyncIterator[str]
    if req.canned and req.fixture:
        generator = _canned_stream(req.fixture)
    else:
        generator = _live_stream(req)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------ rewrite


@app.post("/rewrite")
async def rewrite(req: RewriteRequest) -> dict[str, Any]:
    if req.audit_id not in AUDIT_STORE:
        raise HTTPException(404, "Audit not found")
    audit = AUDIT_STORE[req.audit_id]
    listing = Listing(**audit["listing"])
    audits = [
        AuditResult(
            claim=Claim(**a["claim"]),
            verdict=a["verdict"],
            grabmaps_finding=a["finding"],
            delta=a.get("delta"),
            evidence=a.get("evidence", {}),
            endpoints_called=a.get("endpoints_called", []),
            map_events=a.get("map_events", []),
        )
        for a in audit["audits"]
    ]
    return await rewrite_for_seller(listing, audits)

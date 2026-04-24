"""
Audit agent — rule-based dispatch per `specs/audit-agent.md`.

Six verifiers, one dispatch table. NO LLM in the verification hot path.

Each verifier is wrapped by the orchestrator so any exception becomes a
single `unverifiable` AuditResult with the error message as the finding —
the stream never dies on a single bad call.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

from .listing import Claim, Listing
from .maps.facade import GrabMaps
from .maps.http_client import haversine_km

Verdict = Literal["true", "overstated", "false", "misleading", "unverifiable"]

# -------------------------------------------------------------- thresholds

WALK_TIME_THRESHOLDS = (1.10, 1.50)       # (true_ceiling, overstated_ceiling) x claimed
DRIVE_TIME_THRESHOLDS = (1.15, 1.60)
QUIET_THRESHOLDS = (5, 20)                # incidents/500m
AMENITY_COUNT_THRESHOLDS = (5, 1)         # (true_floor, overstated_floor)
AMENITY_DISTANCE_THRESHOLDS_KM = (0.5, 1.0)
SCHOOL_WALK_THRESHOLDS = (10, 15)         # minutes


# -------------------------------------------------------------- colours

VERDICT_COLORS = {
    "true": "#2f5a3f",
    "overstated": "#a97629",
    "false": "#a5282a",
    "misleading": "#a97629",
    "unverifiable": "#6b6558",
}


# -------------------------------------------------------------- result

@dataclass
class AuditResult:
    claim: Claim
    verdict: Verdict
    grabmaps_finding: str
    delta: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    endpoints_called: list[str] = field(default_factory=list)
    map_events: list[dict[str, Any]] = field(default_factory=list)


# -------------------------------------------------------------- helpers


def _verdict_color(v: str) -> str:
    return VERDICT_COLORS.get(v, "#6b6558")


def _route_event(
    origin: tuple[float, float],
    dest: tuple[float, float],
    profile: str,
    color: str,
    polyline: str | None,
) -> dict[str, Any]:
    return {
        "op": "route",
        "from": [origin[0], origin[1]],
        "to": [dest[0], dest[1]],
        "profile": profile,
        "color": color,
        "polyline": polyline,
    }


def _pin_event(lat: float, lng: float, color: str, label: str) -> dict[str, Any]:
    return {"op": "pin", "lat": lat, "lng": lng, "color": color, "label": label}


def _flyto_event(lat: float, lng: float, zoom: float = 16.0) -> dict[str, Any]:
    # Coord-order swap site #2: flyTo uses [lng, lat] inside MapLibre-land, but
    # the contract specifies lat/lng fields (the frontend swaps at the call
    # site); we keep lat/lng to match the contract.
    return {"op": "flyTo", "lat": lat, "lng": lng, "zoom": zoom}


# -------------------------------------------------------------- verifiers

async def verify_walk_time(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    target = claim.parsed.get("target", "")
    claimed = float(claim.parsed.get("minutes") or 0)
    places = await gm.search(target, country="SGP", location=origin, limit=1)
    if not places:
        return AuditResult(
            claim=claim,
            verdict="unverifiable",
            grabmaps_finding=f"Could not locate '{target}' on GrabMaps.",
            endpoints_called=["search"],
        )
    dest = places[0]
    real_min, route = await gm.walk_time_minutes(origin, (dest.lat, dest.lng))
    delta = ((real_min - claimed) / claimed) if claimed else None
    true_ceil, over_ceil = WALK_TIME_THRESHOLDS
    if claimed and real_min <= claimed * true_ceil:
        verdict: Verdict = "true"
    elif claimed and real_min <= claimed * over_ceil:
        verdict = "overstated"
    else:
        verdict = "false"
    color = _verdict_color(verdict)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=(
            f"Real walk: {real_min:.1f} min to {dest.name}. "
            f"Listing claimed {claimed:.0f} min."
        ),
        delta=delta,
        evidence={
            "destination": dest.name,
            "destination_latlng": [dest.lat, dest.lng],
            "real_minutes": real_min,
            "claimed_minutes": claimed,
        },
        endpoints_called=["search", "navigation"],
        map_events=[
            _flyto_event(dest.lat, dest.lng, zoom=15.5),
            _pin_event(dest.lat, dest.lng, color, dest.name),
            _route_event(origin, (dest.lat, dest.lng), "walking", color, route.geometry),
        ],
    )


async def verify_drive_time(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    target = claim.parsed.get("target", "CBD")
    claimed = float(claim.parsed.get("minutes") or 0)
    places = await gm.search(target, country="SGP", location=origin, limit=1)
    if not places:
        return AuditResult(
            claim=claim,
            verdict="unverifiable",
            grabmaps_finding=f"Could not locate '{target}' on GrabMaps.",
            endpoints_called=["search"],
        )
    dest = places[0]
    real_min, route = await gm.drive_time_minutes(origin, (dest.lat, dest.lng))
    delta = ((real_min - claimed) / claimed) if claimed else None
    true_ceil, over_ceil = DRIVE_TIME_THRESHOLDS
    if claimed and real_min <= claimed * true_ceil:
        verdict: Verdict = "true"
    elif claimed and real_min <= claimed * over_ceil:
        verdict = "overstated"
    else:
        verdict = "false"
    color = _verdict_color(verdict)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=(
            f"Real drive: {real_min:.1f} min to {dest.name}. "
            f"Listing claimed {claimed:.0f} min."
        ),
        delta=delta,
        evidence={
            "destination": dest.name,
            "destination_latlng": [dest.lat, dest.lng],
            "real_minutes": real_min,
            "claimed_minutes": claimed,
        },
        endpoints_called=["search", "navigation"],
        map_events=[
            _pin_event(dest.lat, dest.lng, color, dest.name),
            _route_event(origin, (dest.lat, dest.lng), "driving", color, route.geometry),
        ],
    )


async def verify_amenity(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    category = claim.parsed.get("category", "supermarket")
    places = await gm.nearby(
        origin[0], origin[1], radius_km=1.0, limit=20, keyword=category
    )
    count = len(places)
    nearest_km: float | None = None
    if places:
        nearest_km = min(
            haversine_km(origin[0], origin[1], p.lat, p.lng) for p in places
        )
    true_floor, over_floor = AMENITY_COUNT_THRESHOLDS
    true_dist, over_dist = AMENITY_DISTANCE_THRESHOLDS_KM
    if count >= true_floor and (nearest_km is not None and nearest_km <= true_dist):
        verdict: Verdict = "true"
    elif count >= over_floor and (nearest_km is not None and nearest_km <= over_dist):
        verdict = "overstated"
    else:
        verdict = "false"
    finding = (
        f"{count} {category}(s) within 1km. Nearest: {nearest_km:.2f}km"
        if nearest_km is not None
        else f"No {category} within 1km."
    )
    # Cap map pins at 5 nearest
    by_dist = sorted(places, key=lambda p: haversine_km(origin[0], origin[1], p.lat, p.lng))
    map_events = [
        _pin_event(p.lat, p.lng, "#6b6558", p.name) for p in by_dist[:5]
    ]
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=finding,
        evidence={
            "count_1km": count,
            "nearest_km": nearest_km,
            "category": category,
        },
        endpoints_called=["nearby"],
        map_events=map_events,
    )


async def verify_quiet(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    density, _incidents = await gm.incident_density(origin[0], origin[1], radius_m=500)
    true_ceil, over_ceil = QUIET_THRESHOLDS
    if density <= true_ceil:
        verdict: Verdict = "true"
        finding = f"Only {density} incidents logged within 500m. Plausibly quiet."
    elif density <= over_ceil:
        verdict = "overstated"
        finding = f"{density} incidents within 500m — not quiet by SG standards."
    else:
        verdict = "false"
        finding = f"{density} incidents within 500m. This is not a quiet road."
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=finding,
        evidence={"incident_count_500m": density},
        endpoints_called=["incidents_bbox"],
        map_events=[_pin_event(origin[0], origin[1], _verdict_color(verdict), "listing")],
    )


async def verify_view(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    photos = await gm.street_view(origin[0], origin[1], radius=200, limit=6)
    if not photos:
        # Graceful degradation per AGENTS.md: no photos → unverifiable (NOT false)
        return AuditResult(
            claim=claim,
            verdict="unverifiable",
            grabmaps_finding="No street view imagery available at this location.",
            endpoints_called=["street_view"],
        )
    photo_urls = [p.thumb_url for p in photos[:6] if p.thumb_url]
    heading = photos[0].heading
    # A view claim can't be auto-falsified from photos alone; we surface them
    # and label the claim `misleading` (subjective) so the UI prompts the user.
    verdict: Verdict = "misleading"
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=(
            f"Pulled {len(photos)} nearby street-view photos. Claim is "
            "subjective — see evidence for yourself."
        ),
        evidence={
            "photo_count": len(photos),
            "photos": [
                {
                    "id": p.id,
                    "lat": p.lat,
                    "lng": p.lng,
                    "heading": p.heading,
                    "thumb_url": p.thumb_url,
                    "full_url": p.full_url,
                }
                for p in photos[:6]
            ],
        },
        endpoints_called=["street_view"],
        map_events=[
            {
                "op": "streetview",
                "lat": origin[0],
                "lng": origin[1],
                "photo_urls": photo_urls,
                "heading": heading,
            }
        ],
    )


async def verify_school_access(
    claim: Claim, origin: tuple[float, float], gm: GrabMaps
) -> AuditResult:
    target_type = claim.parsed.get("target_type", "primary")
    target_name = claim.parsed.get("target_name")
    # If the listing named a specific school, search for it by name first —
    # the generic "primary school" search often returns famous-but-distant
    # schools that don't match the actual listing claim.
    query = target_name or f"{target_type} school"
    # BUG-05: `search` ignores `limit` server-side; we slice client-side.
    # Cast a wider net so the nearest actual school makes the slice.
    places = await gm.search(query, country="SGP", location=origin, limit=20)
    if not places:
        return AuditResult(
            claim=claim,
            verdict="unverifiable",
            grabmaps_finding=f"No {target_type} schools indexed near this address.",
            endpoints_called=["search"],
        )
    # Choose actual nearest by great-circle distance, not search order
    nearest = min(
        places, key=lambda p: haversine_km(origin[0], origin[1], p.lat, p.lng)
    )
    walk_min, route = await gm.walk_time_minutes(origin, (nearest.lat, nearest.lng))
    true_ceil, over_ceil = SCHOOL_WALK_THRESHOLDS
    if walk_min <= true_ceil:
        verdict: Verdict = "true"
    elif walk_min <= over_ceil:
        verdict = "overstated"
    else:
        verdict = "false"
    color = _verdict_color(verdict)
    return AuditResult(
        claim=claim,
        verdict=verdict,
        grabmaps_finding=(
            f"Nearest {target_type}: {nearest.name}, {walk_min:.1f} min walk."
        ),
        evidence={
            "school": nearest.name,
            "school_latlng": [nearest.lat, nearest.lng],
            "walk_min": walk_min,
        },
        endpoints_called=["search", "navigation"],
        map_events=[
            _pin_event(nearest.lat, nearest.lng, color, nearest.name),
            _route_event(
                origin,
                (nearest.lat, nearest.lng),
                "walking",
                color,
                route.geometry,
            ),
        ],
    )


# -------------------------------------------------------------- dispatch


VERIFIERS: dict[
    str,
    Callable[[Claim, tuple[float, float], GrabMaps], Awaitable[AuditResult]],
] = {
    "walk_time": verify_walk_time,
    "drive_time": verify_drive_time,
    "amenity": verify_amenity,
    "quiet": verify_quiet,
    "view": verify_view,
    "school_access": verify_school_access,
}


# -------------------------------------------------------------- orchestration


async def geocode_listing(
    listing: Listing, gm: GrabMaps
) -> tuple[tuple[float, float] | None, dict[str, Any]]:
    """Geocode via MCP (falls back to REST). Returns (origin, metadata)."""
    query = listing.address or listing.title
    places, used_mcp = await gm.mcp_search(query, country="SGP", limit=1)
    if not places:
        return None, {"used_mcp": used_mcp, "label": query}
    p = places[0]
    return (p.lat, p.lng), {
        "used_mcp": used_mcp,
        "label": p.name or query,
        "confidence": True,
        "address": p.address,
    }


async def audit_listing(
    listing: Listing, claims: list[Claim], gm: GrabMaps | None = None
) -> AsyncIterator[AuditResult | dict[str, Any]]:
    """Run the full audit loop, yielding verdicts (and a geocode metadata
    dict once at the start) as they arrive.

    The first yielded item is a dict with shape
    `{"_type": "geocode", "origin": (lat,lng), "meta": {...}}` so the caller
    can emit the SSE `geocode` event before streaming verdicts. Everything
    afterwards is an AuditResult.
    """
    owns_gm = gm is None
    if owns_gm:
        gm = GrabMaps()
        await gm.__aenter__()
    try:
        origin, meta = await geocode_listing(listing, gm)
        yield {"_type": "geocode", "origin": origin, "meta": meta}
        if origin is None:
            return
        for idx, claim in enumerate(claims, start=1):
            # Announce which claim is about to be verified so the UI can
            # update its progress chip before the verifier starts (live
            # REST calls can take 1-3 seconds).
            yield {"_type": "progress", "index": idx, "claim": claim}
            verifier = VERIFIERS.get(claim.type)
            if not verifier:
                yield AuditResult(
                    claim=claim,
                    verdict="unverifiable",
                    grabmaps_finding="No verifier registered for this claim type.",
                )
                continue
            try:
                yield await verifier(claim, origin, gm)
            except Exception as e:
                yield AuditResult(
                    claim=claim,
                    verdict="unverifiable",
                    grabmaps_finding=f"Verifier failed: {type(e).__name__}: {e}",
                )
    finally:
        if owns_gm:
            await gm.__aexit__(None, None, None)


# -------------------------------------------------------------- rewrite


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_rewrite_prompt() -> str:
    with open(os.path.join(PROMPTS_DIR, "rewrite_seller.md")) as f:
        return f.read()


async def rewrite_for_seller(
    listing: Listing, audits: list[AuditResult]
) -> dict[str, Any]:
    """GPT rewrite. Uses audit facts as hard ground truth."""
    import json as _json

    from openai import AsyncOpenAI

    facts_lines = []
    for a in audits:
        facts_lines.append(
            f"- [{a.claim.type}] {a.grabmaps_finding} (verdict: {a.verdict})"
        )
    facts = "\n".join(facts_lines) or "- No audit facts available."
    prompt = (
        _load_rewrite_prompt()
        .replace("{facts}", facts)
        .replace("{original}", listing.raw_copy[:6000])
    )
    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "title": listing.title,
            "copy": "",
            "photo_brief": "",
            "predicted_score": 0,
            "error": "OPENAI_API_KEY missing",
        }
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    text = ""
    # Use gpt-5-mini with `reasoning_effort=minimal` — the flip is latency-
    # sensitive (user clicks and expects seconds, not minutes). Empirically:
    # default reasoning effort runs 40-60s; minimal runs 4-6s for this task
    # with no visible quality regression for well-constrained JSON output.
    for model, reasoning in (
        ("gpt-5-mini", "minimal"),
        ("gpt-5", "minimal"),
    ):
        try:
            msg = await client.chat.completions.create(
                model=model,
                reasoning_effort=reasoning,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (msg.choices[0].message.content or "").strip()
            if text:
                break
        except Exception:
            continue
    if not text:
        return {
            "title": listing.title,
            "copy": listing.raw_copy[:1000],
            "photo_brief": "",
            "predicted_score": 0,
        }
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return {
            "title": listing.title,
            "copy": text[:1200],
            "photo_brief": "",
            "predicted_score": 0,
        }

# Spec: Audit Agent

**Status:** Frozen. Pure rule-based dispatch. No LLM in the verification path.

## What it does

Given a `Listing` + a list of `Claim`s (already extracted by
`specs/listing-extractor.md`), produce an `AuditResult` per claim and yield them
to the SSE stream (`verdict` event) one by one, with a 250–400ms stagger so
the UI stamps visibly.

## Claim types and their parsed shape

| `type` | `parsed` keys | What the verifier checks |
|---|---|---|
| `walk_time` | `target: str, minutes: float, mode: "walk"` | `search(target)` → `direction(profile=walking)` |
| `drive_time` | `target: str, minutes: float, mode: "drive"` | `search(target)` → `direction(profile=driving)` |
| `amenity` | `category: str, proximity_phrase: str` | `nearby(category, radius_km=1.0)` — count and nearest distance |
| `quiet` | `claim_phrase: str` | `incidents_bbox(±500m)` — incident count |
| `view` | `claim_phrase: str, direction_if_stated: str\|null` | `street_view(radius=200m)` — surfaces photos |
| `school_access` | `target_type: "primary"\|"secondary", target_name: str\|null` | `search("primary school")` → `direction(walking)` |

**Unknown types** → emit a `verdict` with `verdict: "unverifiable"` and a generic
finding. **No LLM fallback.** The listing extractor is expected to coerce novel
phrasings into one of the six above, or drop them.

## Verdict thresholds (hardcoded, tunable in one file)

```python
WALK_TIME_THRESHOLDS = (1.10, 1.50)        # (true_ceiling, overstated_ceiling) as multiplier
DRIVE_TIME_THRESHOLDS = (1.15, 1.60)       # drive times are noisier
QUIET_THRESHOLDS = (5, 20)                 # incidents/500m: (true_ceiling, overstated_ceiling)
AMENITY_COUNT_THRESHOLDS = (5, 1)          # (true_floor, overstated_floor)
AMENITY_DISTANCE_THRESHOLDS_KM = (0.5, 1.0)
SCHOOL_WALK_THRESHOLDS = (10, 15)          # minutes
```

Tuning these requires no code change. Keep them at the top of `agent.py`.

## Per-claim verifier signatures

```python
async def verify_walk_time(claim, origin, gm) -> AuditResult: ...
async def verify_drive_time(claim, origin, gm) -> AuditResult: ...
async def verify_amenity(claim, origin, gm) -> AuditResult: ...
async def verify_quiet(claim, origin, gm) -> AuditResult: ...
async def verify_view(claim, origin, gm) -> AuditResult: ...
async def verify_school_access(claim, origin, gm) -> AuditResult: ...

VERIFIERS = {
    "walk_time": verify_walk_time,
    "drive_time": verify_drive_time,
    "amenity": verify_amenity,
    "quiet": verify_quiet,
    "view": verify_view,
    "school_access": verify_school_access,
}
```

Each returns:

```python
@dataclass
class AuditResult:
    claim: Claim
    verdict: Literal["true", "overstated", "false", "misleading", "unverifiable"]
    grabmaps_finding: str              # one-line human-readable
    delta: float | None                # (real - claimed) / claimed when meaningful
    evidence: dict                     # type-specific, see sse-contract.md
    endpoints_called: list[str]
    map_events: list[dict]             # structured, per sse-contract.md
```

## Map event generation (per verifier)

Each verifier emits `map_events` so the map reacts as verdicts stream in:

- `walk_time` / `drive_time`: `[flyTo(dest), pin(dest, color=verdict_color), route(origin, dest, polyline=..., color=verdict_color)]`
- `amenity`: `[pin(each nearest match, color=stone)]` capped at 5
- `quiet`: `[pin(origin, color=incident_heat_color)]` (optional: incident pins)
- `view`: `[streetview(origin, photo_urls=[...], heading=...)]`
- `school_access`: `[pin(school, color=forest), route(origin, school)]`

Colours by verdict: true=`#2f5a3f` (forest), overstated=`#a97629` (amber),
false=`#a5282a` (blood), misleading=`#a97629`, unverifiable=`#6b6558` (stone).

## Orchestration

```python
async def audit_listing(listing, claims) -> AsyncIterator[AuditResult]:
    async with GrabMaps() as gm:
        origin = await geocode_listing(listing, gm)     # first visible MCP call
        yield_status("geocoding done", origin=origin)
        for claim in claims:
            verifier = VERIFIERS.get(claim.type)
            if not verifier:
                yield AuditResult(claim, "unverifiable", "No verifier for this claim type.", ...)
                continue
            try:
                yield await verifier(claim, origin, gm)
            except Exception as e:
                yield AuditResult(claim, "unverifiable", f"Verifier failed: {e}", ...)
```

Geocoding: `search(listing.address, country=SGP, limit=1)`. If not confident
(is_confident=False) or no results, emit a `status` event and bail out — no
further verification makes sense without an origin.

## Scoring

See `backend/score.py`:

```python
VERDICT_WEIGHTS = {"true": 1.0, "overstated": 0.4, "misleading": 0.2, "false": 0.0, "unverifiable": 0.6}
CLAIM_TYPE_WEIGHTS = {"walk_time": 1.5, "drive_time": 1.3, "quiet": 1.2, "amenity": 1.0,
                     "school_access": 1.3, "view": 0.8, "connectivity": 1.0, "ambiance": 0.5}

score = round(100 * sum(type_weight * verdict_score) / sum(type_weights))
```

`unverifiable` at 0.6 avoids punishing listings for missing GrabMaps coverage.

## Seller rewrite (Wayang mode)

LLM call, separate from verification. Prompt-in: the verdict list + original
copy. Prompt-out: `{title, copy, photo_brief, predicted_score}`. See PRD §3
"Ground Truth: Seller." Uses `openai.AsyncOpenAI`, model `gpt-5` with
`gpt-5-mini` fallback. Both calls use `response_format={"type": "json_object"}`
so the output parses strictly.

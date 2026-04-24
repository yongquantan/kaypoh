"""
Deterministic honesty score.

Weighted average across audit results. Weights per `specs/audit-agent.md`.
`unverifiable` at 0.6 so we don't punish listings for GrabMaps coverage gaps.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import AuditResult

VERDICT_WEIGHTS: dict[str, float] = {
    "true": 1.0,
    "overstated": 0.4,
    "misleading": 0.2,
    "false": 0.0,
    "unverifiable": 0.6,
}

CLAIM_TYPE_WEIGHTS: dict[str, float] = {
    "walk_time": 1.5,
    "drive_time": 1.3,
    "quiet": 1.2,
    "amenity": 1.0,
    "school_access": 1.3,
    "view": 0.8,
    "connectivity": 1.0,
    "ambiance": 0.5,
}


def honesty_score(audits: "list[AuditResult]") -> int:
    """0-100. 100 = spotless. 0 = total fabrication. 50 when no signal."""
    if not audits:
        return 50
    total_w = 0.0
    weighted = 0.0
    for a in audits:
        tw = CLAIM_TYPE_WEIGHTS.get(a.claim.type, 1.0)
        vw = VERDICT_WEIGHTS.get(a.verdict, 0.5)
        total_w += tw
        weighted += tw * vw
    raw = weighted / total_w if total_w else 0.5
    return max(0, min(100, round(raw * 100)))


def score_breakdown(audits: "list[AuditResult]") -> dict[str, int]:
    counts = {v: 0 for v in VERDICT_WEIGHTS}
    for a in audits:
        counts[a.verdict] = counts.get(a.verdict, 0) + 1
    return counts

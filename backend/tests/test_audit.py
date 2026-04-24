"""
Fixture-driven audit loop tests.

For each of the three fixtures:
  1. Construct a canned list of Claims mirroring what Claude WOULD extract
     from the fixture's raw_copy.
  2. Drive `audit_listing` against a FakeGrabMaps with per-fixture profile.
  3. Assert score in expected band + all expected verifier types fire at
     least once across the combined run.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.agent import AuditResult, audit_listing
from backend.listing import Claim, load_fixture
from backend.score import honesty_score

from .fake_maps import (
    FakeGrabMaps,
    bishan_profile,
    tampines_profile,
    tiong_bahru_profile,
)


def _bishan_claims() -> list[Claim]:
    return [
        Claim(
            id="c-01",
            type="walk_time",
            raw_text="5 min walk to Bishan MRT interchange",
            parsed={"target": "Bishan MRT", "minutes": 5, "mode": "walk"},
        ),
        Claim(
            id="c-02",
            type="drive_time",
            raw_text="12 min drive to Raffles Place",
            parsed={"target": "Raffles Place", "minutes": 12, "mode": "drive"},
        ),
        Claim(
            id="c-03",
            type="quiet",
            raw_text="quiet residential road",
            parsed={"claim_phrase": "quiet residential road"},
        ),
        Claim(
            id="c-04",
            type="amenity",
            raw_text="supermarkets and clinics all within 5 minutes",
            parsed={"category": "supermarket", "proximity_phrase": "within 5 min"},
        ),
        Claim(
            id="c-05",
            type="school_access",
            raw_text="top primary schools within walking distance",
            parsed={"target_type": "primary", "target_name": None},
        ),
    ]


def _tampines_claims() -> list[Claim]:
    return [
        Claim(
            id="c-01",
            type="walk_time",
            raw_text="3 min walk to Tampines MRT",
            parsed={"target": "Tampines MRT", "minutes": 3, "mode": "walk"},
        ),
        Claim(
            id="c-02",
            type="drive_time",
            raw_text="15 min drive to Marina Bay Sands",
            parsed={"target": "Marina Bay Sands", "minutes": 15, "mode": "drive"},
        ),
        Claim(
            id="c-03",
            type="amenity",
            raw_text="at least 10 supermarkets within walking distance",
            parsed={"category": "supermarket", "proximity_phrase": "walking distance"},
        ),
        Claim(
            id="c-04",
            type="quiet",
            raw_text="peaceful, quiet residential stretch",
            parsed={"claim_phrase": "peaceful, quiet residential stretch"},
        ),
        Claim(
            id="c-05",
            type="school_access",
            raw_text="top primary schools right next door",
            parsed={"target_type": "primary", "target_name": "Poi Ching"},
        ),
    ]


def _tiong_bahru_claims() -> list[Claim]:
    return [
        Claim(
            id="c-01",
            type="walk_time",
            raw_text="10 min walk to Tiong Bahru MRT",
            parsed={"target": "Tiong Bahru MRT", "minutes": 10, "mode": "walk"},
        ),
        Claim(
            id="c-02",
            type="drive_time",
            raw_text="14 min drive to Raffles Place",
            parsed={"target": "Raffles Place", "minutes": 14, "mode": "drive"},
        ),
        Claim(
            id="c-03",
            type="amenity",
            raw_text="cafés, bakeries, and a wet market within 10 minutes",
            parsed={"category": "cafe", "proximity_phrase": "within 10 minutes"},
        ),
        Claim(
            id="c-04",
            type="school_access",
            raw_text="12 min walk to Zhangde Primary",
            parsed={"target_type": "primary", "target_name": "Zhangde"},
        ),
        Claim(
            id="c-05",
            type="view",
            raw_text="street view captures the iconic art-deco shophouses",
            parsed={
                "claim_phrase": "iconic art-deco shophouses",
                "direction_if_stated": None,
            },
        ),
    ]


async def _run_audit(listing, claims, profile) -> tuple[list[AuditResult], FakeGrabMaps]:
    gm = FakeGrabMaps(profile)
    results: list[AuditResult] = []
    async with gm:
        async for item in audit_listing(listing, claims, gm=gm):  # type: ignore[arg-type]
            if isinstance(item, AuditResult):
                results.append(item)
            # geocode metadata dict: ignore
    return results, gm


@pytest.mark.asyncio
async def test_bishan_overstated_band():
    listing = load_fixture("demo_bishan")
    claims = _bishan_claims()
    results, _ = await _run_audit(listing, claims, bishan_profile())
    score = honesty_score(results)
    assert 20 <= score <= 50, f"Bishan score {score} outside expected 20-50 band"
    assert len(results) == len(claims)


@pytest.mark.asyncio
async def test_tampines_false_band():
    listing = load_fixture("demo_tampines")
    claims = _tampines_claims()
    results, _ = await _run_audit(listing, claims, tampines_profile())
    score = honesty_score(results)
    assert 0 <= score <= 30, f"Tampines score {score} outside expected 0-30 band"
    # The supermarket nearby returns [], so amenity verdict must be `false`
    amenity = [r for r in results if r.claim.type == "amenity"][0]
    assert amenity.verdict == "false"


@pytest.mark.asyncio
async def test_tiong_bahru_honest_band():
    listing = load_fixture("demo_tiong_bahru")
    claims = _tiong_bahru_claims()
    results, _ = await _run_audit(listing, claims, tiong_bahru_profile())
    score = honesty_score(results)
    assert 70 <= score <= 95, f"Tiong Bahru score {score} outside expected 70-95 band"
    # `view` for Tiong Bahru should be `misleading` (photos found)
    view = [r for r in results if r.claim.type == "view"][0]
    assert view.verdict == "misleading"


@pytest.mark.asyncio
async def test_all_six_verifiers_fire_across_fixtures():
    """Combined run must exercise all six claim types at least once."""
    fired: set[str] = set()
    for listing_name, claims_fn, profile_fn in [
        ("demo_bishan", _bishan_claims, bishan_profile),
        ("demo_tampines", _tampines_claims, tampines_profile),
        ("demo_tiong_bahru", _tiong_bahru_claims, tiong_bahru_profile),
    ]:
        listing = load_fixture(listing_name)
        results, _ = await _run_audit(listing, claims_fn(), profile_fn())
        for r in results:
            fired.add(r.claim.type)
    expected = {"walk_time", "drive_time", "amenity", "quiet", "view", "school_access"}
    missing = expected - fired
    assert not missing, f"Verifier types not fired: {missing}"

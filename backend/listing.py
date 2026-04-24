"""
Listing scraper + claim extractor.

Two entry points:

1. `fetch_listing(url)` — Playwright scrape, stretch goal. Stubbed for the
   hackathon: raises NotImplementedError and falls back to a fixture by URL.
2. `load_fixture(name)` — deterministic, for demo day.

Then `extract_claims(listing)` runs Claude over `listing.raw_copy` to produce
structured `Claim` records the audit agent can dispatch.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PROMPTS_DIR = Path(__file__).parent / "prompts"

ClaimType = Literal[
    "walk_time",
    "drive_time",
    "amenity",
    "quiet",
    "view",
    "school_access",
]

SUPPORTED_CLAIM_TYPES: set[str] = {
    "walk_time",
    "drive_time",
    "amenity",
    "quiet",
    "view",
    "school_access",
}


@dataclass
class Listing:
    url: str
    title: str
    address: str
    price_sgd: int | None
    bedrooms: int | None
    sqft: int | None
    raw_copy: str
    photos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    id: str
    type: str
    raw_text: str
    parsed: dict[str, Any]


# Module-level store for pre-extracted claims keyed by fixture url. Lets
# fixtures ship with hand-authored claims so demo day doesn't depend on
# Claude being up. Populated by `load_fixture`, read by `extract_claims`.
_PRELOADED_CLAIMS: dict[str, list[Claim]] = {}


# ---------------------------------------------------------------- fixtures


def load_fixture(name: str) -> Listing:
    path = FIXTURES_DIR / f"{name}.json"
    data = json.loads(path.read_text())
    data.setdefault("photos", [])
    listing = Listing(
        url=data.get("url", ""),
        title=data.get("title", ""),
        address=data.get("address", ""),
        price_sgd=data.get("price_sgd"),
        bedrooms=data.get("bedrooms"),
        sqft=data.get("sqft"),
        raw_copy=data.get("raw_copy", ""),
        photos=data.get("photos", []),
    )
    raw_claims = data.get("claims")
    if isinstance(raw_claims, list) and raw_claims:
        claims: list[Claim] = []
        for raw in raw_claims[:8]:
            c = _coerce_claim(raw)
            if c:
                claims.append(c)
        if claims:
            _PRELOADED_CLAIMS[listing.url] = claims
    return listing


def load_fixture_by_url(url: str) -> Listing:
    for path in FIXTURES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("url") == url or path.stem in (url or ""):
            return load_fixture(path.stem)
    return load_fixture("demo_bishan")


# ---------------------------------------------------------------- Playwright


async def fetch_listing(url: str) -> Listing:
    """Playwright path. Stubbed for hackathon — falls back to fixture.

    The real implementation would:
      async with async_playwright() as p:
          browser = await p.chromium.launch(headless=True)
          ...
    But we don't want to depend on `playwright install chromium` during tests.
    """
    try:
        # Best-effort real scrape when SK_ENABLE_PLAYWRIGHT is set
        if os.environ.get("KP_ENABLE_PLAYWRIGHT"):
            from playwright.async_api import async_playwright  # type: ignore

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                title = (
                    await page.locator("h1").first.text_content(timeout=3000)
                ) or ""
                body = await page.locator("body").inner_text()
                await browser.close()
                return Listing(
                    url=url,
                    title=title.strip(),
                    address="",
                    price_sgd=None,
                    bedrooms=None,
                    sqft=None,
                    raw_copy=body[:8000],
                    photos=[],
                )
        raise NotImplementedError(
            "Playwright scrape disabled; set KP_ENABLE_PLAYWRIGHT=1 to enable."
        )
    except Exception:
        # Fall back to a fixture match
        return load_fixture_by_url(url)


# ---------------------------------------------------------------- extraction


def _load_prompt() -> str:
    return (PROMPTS_DIR / "extract_claims.md").read_text()


def _coerce_claim(raw: dict[str, Any]) -> Claim | None:
    """Filter one claim through our hard rules. Returns None to drop."""
    c_type = raw.get("type")
    if c_type not in SUPPORTED_CLAIM_TYPES:
        return None
    parsed = raw.get("parsed") or {}
    # Shape checks per type
    if c_type in ("walk_time", "drive_time"):
        if "target" not in parsed or "minutes" not in parsed:
            return None
        try:
            parsed["minutes"] = float(parsed["minutes"])
        except (TypeError, ValueError):
            return None
        parsed.setdefault("mode", "walk" if c_type == "walk_time" else "drive")
    elif c_type == "amenity":
        if "category" not in parsed:
            return None
        parsed.setdefault("proximity_phrase", "")
    elif c_type == "quiet":
        parsed.setdefault("claim_phrase", raw.get("raw_text", ""))
    elif c_type == "view":
        parsed.setdefault("claim_phrase", raw.get("raw_text", ""))
        parsed.setdefault("direction_if_stated", None)
    elif c_type == "school_access":
        parsed.setdefault("target_type", "primary")
        parsed.setdefault("target_name", None)
    return Claim(
        id=str(raw.get("id", "")),
        type=c_type,
        raw_text=str(raw.get("raw_text", "")),
        parsed=parsed,
    )


async def extract_claims(
    listing: Listing,
) -> tuple[Listing, list[Claim], str]:
    """Use GPT to turn free-text listing into structured claims.

    Live-by-default. If the listing ships with pre-authored `claims`
    (fixture safety net), we only fall back to them when the LLM fails or
    no API key is available. This keeps the demo genuinely live while
    preserving a deterministic fallback for the moment the OPENAI_API_KEY
    is rate-limited or the model is down.

    Returns `(listing, claims, source)` where `source` is one of:
      - `"llm"`    — GPT extracted the claims live
      - `"baked"`  — fixture's pre-authored claims used (LLM skipped or failed)
      - `"empty"`  — no claims available, audit will be a no-op
    """
    fallback = _PRELOADED_CLAIMS.get(listing.url)

    if not os.environ.get("OPENAI_API_KEY"):
        if fallback:
            return listing, fallback, "baked"
        return listing, [], "empty"

    from openai import AsyncOpenAI

    prompt = _load_prompt().replace("{copy}", listing.raw_copy[:8000])

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    text: str = ""
    # GPT-5 models: `reasoning_effort=minimal` is the fast path — extraction
    # is a constrained JSON task, heavy reasoning gives no benefit and costs
    # 40+ seconds per call. `response_format=json_object` keeps parsing tight.
    for model in ("gpt-5-mini", "gpt-5"):
        try:
            msg = await client.chat.completions.create(
                model=model,
                reasoning_effort="minimal",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (msg.choices[0].message.content or "").strip()
            if text:
                break
        except Exception:
            continue
    if not text:
        # LLM unavailable (rate-limited / model down / network). Use the
        # fixture's pre-authored claims if present — never kill the demo.
        return listing, fallback or [], "baked" if fallback else "empty"
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return listing, fallback or [], "baked" if fallback else "empty"

    if not listing.address:
        listing.address = data.get("address", "") or listing.address
    if listing.price_sgd is None:
        listing.price_sgd = data.get("price_sgd")
    if listing.bedrooms is None:
        listing.bedrooms = data.get("bedrooms")
    if listing.sqft is None:
        listing.sqft = data.get("sqft")

    claims: list[Claim] = []
    for i, raw in enumerate((data.get("claims") or [])[:8], start=1):
        c = _coerce_claim(raw)
        if c:
            # Always stamp a deterministic unique id; GPT output sometimes
            # collides ("1", "2", "2") which breaks React key uniqueness.
            c.id = f"c-{i:02d}"
            claims.append(c)
    # If the LLM returned zero parseable claims but the fixture ships with a
    # safety net, use it — a zero-claim audit is a worse demo than a safely
    # baked one.
    if not claims and fallback:
        return listing, fallback, "baked"
    if not claims:
        return listing, [], "empty"
    return listing, claims, "llm"

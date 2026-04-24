"""
Listing scraper chain for Path B (URL input).

Two real scrapers, tried in order:
    1. Playwright  — headless Chromium. Fast, but Cloudflare-blocked on PG.
    2. Playwriter  — shells out to `~/Projects/playwriter-property-guru-temp/`
                     which drives the user's real Chrome via a browser
                     extension. Survives Cloudflare.

Each attempt surfaces through an async `on_status(stage, message, tone)`
callback so the demo terminal narrates the chain in real time.

Returns a `Listing` on the first success, raises `ScrapeAllFailed` if
everything fails — callers decide whether to fall back to a fixture.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from .listing import Listing

# Callback signature: async (stage, message, tone) -> None
StatusCB = Callable[[str, str, str], Awaitable[None]]

PLAYWRITER_DIR = Path.home() / "Projects" / "playwriter-property-guru-temp"


class ScrapeAllFailed(RuntimeError):
    """Every scraper in the chain failed."""


# ------------------------------------------------------------- Playwright


async def scrape_with_playwright(url: str, on_status: StatusCB) -> Listing:
    """Headless Chromium scrape. Expected to 403 on PropertyGuru."""
    await on_status("scraping", "Launching Playwright (headless Chromium)…", "muted")

    from playwright.async_api import async_playwright  # type: ignore

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-SG",
            )
            page = await ctx.new_page()
            await on_status(
                "scraping", f"GET {url}", "muted"
            )
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            status = response.status if response else None
            if status and status >= 400:
                raise RuntimeError(
                    f"HTTP {status} — likely Cloudflare. PG blocks headless Chromium."
                )
            body = await page.locator("body").inner_text()
            # Cloudflare interstitial detection
            if "Just a moment" in body[:400] or "cf-turnstile" in body:
                raise RuntimeError(
                    "Cloudflare challenge page served — scrape blocked."
                )
            if len(body) < 500:
                raise RuntimeError(
                    f"Body was only {len(body)} chars — likely blocked."
                )
            title = (await page.locator("h1").first.text_content(timeout=2_000)) or ""
            return Listing(
                url=url,
                title=title.strip(),
                address="",
                price_sgd=None,
                bedrooms=None,
                sqft=None,
                raw_copy=body[:8_000],
                photos=[],
            )
        finally:
            await browser.close()


# ------------------------------------------------------------- Playwriter


def _parse_sqft(area: str | None) -> int | None:
    if not area:
        return None
    # "1,690 sqft" / "818 sqft" / "1119 sqft"
    m = re.search(r"([\d,]+)", area)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _listing_from_playwriter_record(url: str, rec: dict[str, Any]) -> Listing:
    """Map the playwriter detail.json shape onto our Listing dataclass."""
    address = rec.get("fullAddress") or ""
    # Fall back to an inferred address from the title if fullAddress is null
    if not address and rec.get("title"):
        address = f"{rec['title']}, Singapore"
    photos = rec.get("images") or []
    if isinstance(photos, list) and photos and isinstance(photos[0], dict):
        # Some shapes nest {url: ...}
        photos = [p.get("url", "") for p in photos if isinstance(p, dict)]
    return Listing(
        url=url,
        title=rec.get("title") or "",
        address=address,
        price_sgd=rec.get("priceValue"),
        bedrooms=rec.get("bedrooms"),
        sqft=_parse_sqft(rec.get("area")),
        raw_copy=(rec.get("description") or "")[:8_000],
        photos=photos[:8],
    )


async def scrape_with_playwriter(
    url: str, on_status: StatusCB, timeout_s: float = 60.0
) -> Listing:
    """Shell out to the playwriter Node CLI — uses the user's real Chrome.

    Requires:
      - ~/Projects/playwriter-property-guru-temp/ to exist with `npm install` done
      - The Playwriter Chrome extension installed and a session established
        (the user did this already per the eval agent's notes).
    """
    if not PLAYWRITER_DIR.exists():
        raise RuntimeError(f"Playwriter repo not found at {PLAYWRITER_DIR}")

    await on_status(
        "scraping",
        "Falling back to Playwriter (driving your real Chrome)…",
        "warn",
    )

    # Write to a tmp file rather than parse stdout — the CLI logs progress to
    # stdout and only writes JSON when --out is passed.
    out_path = Path("/tmp") / f"kaypoh-playwriter-{os.getpid()}.json"
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "run",
            "scrape",
            "--silent",
            "--",
            url,
            "--pages",
            "1",
            "--out",
            str(out_path),
            "--navigation-timeout",
            "30000",
            "--challenge-timeout",
            "45000",
            cwd=str(PLAYWRITER_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"Playwriter timed out after {timeout_s}s")

        if proc.returncode != 0:
            tail = (stderr or b"").decode(errors="replace")[-400:].strip()
            raise RuntimeError(
                f"Playwriter exited {proc.returncode}: {tail or '(no stderr)'}"
            )

        if not out_path.exists():
            raise RuntimeError("Playwriter completed without writing output.")

        data = json.loads(out_path.read_text())
        listings = data.get("listings") or []
        if not listings:
            raise RuntimeError(
                "Playwriter returned zero listings — URL may not be a detail page."
            )
        rec = listings[0]
        await on_status(
            "scraping",
            f"Playwriter scraped '{rec.get('title') or 'listing'}' "
            f"({len((rec.get('description') or ''))} chars of copy).",
            "success",
        )
        return _listing_from_playwriter_record(url, rec)
    finally:
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- chain


async def scrape_url(url: str, on_status: StatusCB) -> Listing:
    """Try Playwright, then Playwriter. Raises ScrapeAllFailed if both fail.

    Each step narrates through `on_status` so the UI can show the chain
    playing out live.
    """
    errors: list[str] = []

    # Step 1 — Playwright
    try:
        listing = await scrape_with_playwright(url, on_status)
        await on_status(
            "scraping",
            f"Playwright succeeded ({len(listing.raw_copy)} chars).",
            "success",
        )
        return listing
    except Exception as e:
        errors.append(f"Playwright: {e}")
        await on_status("scraping", f"Playwright failed: {e}", "warn")

    # Step 2 — Playwriter
    try:
        listing = await scrape_with_playwriter(url, on_status)
        return listing
    except Exception as e:
        errors.append(f"Playwriter: {e}")
        await on_status("scraping", f"Playwriter failed: {e}", "danger")

    raise ScrapeAllFailed("; ".join(errors))

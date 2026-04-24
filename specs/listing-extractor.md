# Spec: Listing Extractor

**Status:** Draft → Frozen once the first E2E audit passes.

Two entry points into the backend:

1. `fetch_listing(url)` — Playwright scrape of PropertyGuru / 99.co / EdgeProp.
   Fragile by definition. Falls back to fixture by URL match.
2. `load_fixture(name)` — deterministic, for demo day.

Then `extract_claims(listing)` runs Claude over `listing.raw_copy` to produce
structured `Claim` records per `specs/audit-agent.md`.

## Playwright path

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    ctx = await browser.new_context(user_agent=CHROME_UA_MAC)
    page = await ctx.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
    title = await page.locator("h1").first.text_content(timeout=3000)
    body  = await page.locator("body").inner_text()
    await browser.close()
    return Listing(url=url, title=title, address="", ..., raw_copy=body[:8000], photos=[])
```

Generic selectors — tuned per platform is out of scope for the hackathon.
Cap `raw_copy` at 8000 characters for LLM cost control.

Demo uses fixtures. Live scrape is stretch.

## Claim extraction (Claude)

Prompt: `backend/prompts/extract_claims.md` (substituted with `{copy}`). Responds
with a JSON object:

```jsonc
{
  "address": "Bishan Street 13, Singapore",
  "price_sgd": 1680000,
  "bedrooms": 3,
  "sqft": 1119,
  "claims": [
    {
      "id": "c-01",
      "type": "walk_time",
      "raw_text": "5 min walk to Bishan MRT",
      "parsed": {"target": "Bishan MRT", "minutes": 5, "mode": "walk"}
    }
  ]
}
```

**Hard rules in the prompt:**

- Only emit claims whose `type` is one of the six supported by the audit agent
  (`walk_time`, `drive_time`, `amenity`, `quiet`, `view`, `school_access`). Drop
  everything else rather than emit an unknown `type`.
- Every claim's `parsed` must match the exact key shape for its type
  (see `specs/audit-agent.md`).
- No invention: if the copy doesn't state minutes, omit the claim.
- Max 8 claims per listing (keeps audit time bounded).

Model: `gpt-5` (fallback: `gpt-5-mini`). Temperature 0.
`response_format={"type": "json_object"}` so malformed output is impossible.

## Fixtures

`backend/fixtures/*.json`. Three SG listings, each exercising a different audit
shape:

| File | Intent | Expected score |
|---|---|---|
| `demo_bishan.json` | Overstated on every claim (the showcase) | 30–40 |
| `demo_tampines.json` | Outright false — fabricated amenities | 10–25 |
| `demo_tiong_bahru.json` | Honest, high-quality listing | 75–90 |

Each fixture fields:

```jsonc
{
  "url": "https://www.propertyguru.com.sg/listing/demo-bishan",
  "title": "...",
  "address": "Bishan Street 13, Singapore",
  "price_sgd": 1680000,
  "bedrooms": 3,
  "sqft": 1119,
  "raw_copy": "...",   // fed to Claude for claim extraction
  "photos": []
}
```

**Fatten the copy** — each fixture's `raw_copy` should contain 4–6 distinct
claim types so the audit touches all of walk_time, drive_time, amenity, quiet,
view, school_access across the three fixtures.

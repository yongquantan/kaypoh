# Playwriter vs Python Playwright — PropertyGuru Scrape Evaluation

## 1. TL;DR

Python Playwright alone will not survive demo day on PropertyGuru — anonymous fetches return Cloudflare 403, and a fresh Chromium fingerprint gets flagged fast. Recommendation: **(c) Hybrid** — ship fixtures as the primary demo path, and use the `playwriter` reference as a dev-time one-shot to populate those fixtures with real, claim-rich `raw_copy`.

## 2. How the reference works

Source: `/Users/yongquantan/Projects/playwriter-property-guru-temp/`

Flow, end to end:

1. `src/scrape-propertyguru.js::scrapePropertyGuru()` is the entry point. It creates/reuses a Playwriter session via `src/playwriter-runner.js::createSession()`, which shells out to `npx playwriter@latest session new` and scrapes the session id from stdout.
2. It builds a JavaScript payload via `src/propertyguru-agent.js::buildPropertyGuruAgentCode()` that will run inside the Playwriter sandbox (globals: `state`, `page`, `context`, `require`, plus Playwriter helpers like `waitForPageLoad`). The code is passed via `playwriter -s <id> --timeout <ms> -e "<code>"`.
3. Inside the sandbox, `main()`:
   - Navigates the user's real Chrome tab to the target URL (`waitUntil: "domcontentloaded"`, 30s timeout).
   - Polls `waitForSearchPayload()` up to 45s, re-reading `document.querySelector("script#__NEXT_DATA__")` until PropertyGuru's server-rendered JSON appears. This handles the Cloudflare JS challenge — the real browser with real cookies clears it once.
   - For paginated scrapes, uses **in-browser `fetch()` with `credentials: "include"`** to hit subsequent pages. The cookies and TLS fingerprint of the user's Chrome carry the session; Cloudflare sees a legitimate logged-in user.
   - Parses `__NEXT_DATA__` script tag via regex, reaches into `props.pageProps.pageData.data.listingData / listingsData`, and normalizes via `normalizeListing()`.
4. Results are written to a transfer file in `.tmp/` and emitted via a `__PG_SCRAPE_RESULT__` stdout marker the Node parent reads back.

**Key insight:** the reference does **not** scrape CSS selectors at all. It extracts from PropertyGuru's own Next.js server-rendered JSON blob, which is structurally stable across redesigns. That's why `data/detail.json` and `data/propertyguru.json` look like clean API responses, not HTML soup.

**Anti-bot strategy:** none beyond "use the user's real Chrome." No captcha solver, no proxy rotation, no UA spoofing. The README is candid: "Direct `curl` currently hits Cloudflare `403`. This scraper deliberately lets the real browser clear the challenge once, then fetches paginated HTML from inside that browser context using its cookies and fingerprint."

## 3. Live test results

Environment: `playwriter` CLI installed globally (v0.0.80, upgrade available to 0.0.102); Chrome extension connected; session id 13 created successfully.

**Control (Python Playwright equivalent):** `curl` with a Chrome UA against the detail URL returns **HTTP 403** from Cloudflare. Fresh headless Chromium would hit the same challenge page and, without cookie/interaction state, would typically fail to pass it for SG PropertyGuru in my experience.

**Playwriter live scrape** (against `https://www.propertyguru.com.sg/listing/for-sale-the-continuum-24436686`):

```
RESULT::{"title":"The Continuum Condominium For Sale at S$ 4,400,000 | PropertyGuru Singapore",
         "h1":"The Continuum","bodyLen":15704,"hasNextData":true}
```

- Loaded successfully on first try, no captcha interaction needed.
- `__NEXT_DATA__` script tag present — the reference's extraction path works.
- `body.innerText` is 15,704 chars — comfortably exceeds the 8,000-char `raw_copy` cap in `specs/listing-extractor.md`.

**Fields present in reference output** (from `data/detail.json`, The Continuum listing) mapped to `Listing` schema:

| `Listing` field | Source in reference JSON | Present? |
|---|---|---|
| `url` | `listings[0].url` | yes |
| `title` | `listings[0].title` ("The Continuum") | yes |
| `address` | `listings[0].fullAddress` ("Thiam Siew Avenue, East Coast (D15-16)") | yes |
| `price_sgd` | `listings[0].priceValue` (4400000) | yes |
| `bedrooms` | `listings[0].bedrooms` (4) | yes |
| `sqft` | `listings[0].area` ("1,690 sqft" — needs parsing to int) | yes |
| `raw_copy` | `listings[0].description` — the full agent blurb with "proximity to Paya Lebar and Dakota MRT," "Within 1km of reputable schools like Kong Hwa School and Haig Girls' School," "unblocked 270-degree views." **This is exactly the claim-rich text we need.** | yes |
| `photos` | `listings[0].images[].src` (6 URLs) | yes |

**Bonus:** reference JSON also surfaces `nearby.mrt` and `nearby.schools` with walking distances and coordinates — that's ground-truth data we could cross-check Claude's extracted claims against for free, independent of GrabMaps.

## 4. Scoring matrix

| Criterion | Python Playwright (current plan) | Playwriter (reference) |
|---|---|---|
| **Reliability on PropertyGuru** | Poor. Cloudflare 403 on anonymous fetch confirmed via curl. Headless Chromium usually gets challenged; TLS and behavioural fingerprints leak. No retry/captcha strategy in the spec. | High. Reference has real scraped output from today. Real Chrome session carries cookies and fingerprint past Cloudflare on first load. |
| **Setup cost** | `pip install playwright && playwright install chromium` (~300 MB). Hackathon-portable, no user action beyond pip. | Requires **Chrome extension install** (user action, not scriptable), plus Node 20, plus keeping Chrome open with the extension enabled. Not portable to CI/teammate machines without onboarding. |
| **Stack fit** | Native Python integration — direct `async_playwright`, no IPC, matches `backend/listing.py` design. | Node-only sandbox. Integration requires either (a) shelling out from Python to `npx playwriter -e` (fragile, stdout-marker parsing, session management), or (b) rewriting listing ingestion in Node. Neither is cheap. |
| **Data quality** | Selector-based (`h1`, `body.innerText`, capped at 8k chars). Grabs nav chrome and footer boilerplate alongside the description. Needs per-platform selector tuning, explicitly out-of-scope per `specs/listing-extractor.md`. | Structured extraction from `__NEXT_DATA__` — pristine description text, typed numeric fields, images, floor plans, plus `nearby.mrt` / `nearby.schools` with walking distances. Strictly richer. |
| **Demo-day risk** | Two failure modes: (1) Cloudflare 403 mid-demo, (2) selector drift if PG changes H1. Fails silently to empty `raw_copy`. | One failure mode: if PG renames the `__NEXT_DATA__` contract (unlikely in a week). But requires user's laptop + Chrome + extension active on stage — a single "is my Chrome logged out?" kills it. |

## 5. Recommendation

**(c) Hybrid.** Treat the demo as fixture-driven (as `specs/listing-extractor.md` already states: "Demo uses fixtures. Live scrape is stretch."), and use playwriter as a **dev-time tool run by the human operator** to populate those fixtures with high-quality real `raw_copy`.

Rationale:

- Port (b) — rewriting `backend/listing.py` to shell out to Node — adds real integration pain (session management, JSON marker parsing, extension dependency) for a stretch feature we're already committing to skip at demo time.
- Port (a) — Playwright-only as specced — is flimsy. Even if the live scrape path is marked "stretch," having it break silently during development wastes debugging time and leaves fixtures thin.
- Port (d) — Playwright + clever tricks — does not solve Cloudflare. The reference's only "trick" is *not using headless Chromium.* Copying selectors wins nothing here.
- The hybrid uses each tool for its strength: Python Playwright stays as a structural placeholder for the stretch goal (cheap to keep; might work on less-hostile sites); playwriter is how the human actually produces the three fixtures with fat, claim-laden descriptions the audit agent needs.

## 6. Migration plan for (c)

**Files to touch (by the right agent — not this one):** none in `backend/`. The Playwright path in `backend/listing.py` stays as planned.

**New dev artefacts (outside `backend/`):**

1. Keep `/Users/yongquantan/Projects/playwriter-property-guru-temp/` as-is; it's already functional.
2. For each of the three target listings, the human operator runs:
   ```bash
   cd /Users/yongquantan/Projects/playwriter-property-guru-temp
   npm run scrape -- "<PG listing URL>" --out /tmp/pg-bishan.json
   ```
3. A short Python helper — `backend/scripts/pg_to_fixture.py` (new, small) — reads the playwriter JSON and emits `backend/fixtures/demo_<name>.json` in the schema defined in `specs/listing-extractor.md`:
   - `url` = `listings[0].url`
   - `title` = `listings[0].title`
   - `address` = `listings[0].fullAddress`
   - `price_sgd` = `listings[0].priceValue`
   - `bedrooms` = `listings[0].bedrooms`
   - `sqft` = `parseInt(listings[0].area.replace(/[^0-9]/g, ""))`
   - `raw_copy` = `listings[0].description` (truncate to 8000)
   - `photos` = `listings[0].images.map(i => i.src)`

**Contract** between Python and Node: none at runtime — one-way, file-based, dev-time only. The backend never invokes playwriter. Demo runs from `backend/fixtures/*.json`.

**New deps:** none in Python. Node side already pinned to `playwriter@^0.0.102` in the reference repo.

**Not doing:** installing the playwriter Chrome extension programmatically — that's a user action (see Rules).

## 7. Open questions

1. Are we willing to spend the ~2h manual effort to curate three listings whose scraped `description` fields already contain a mix of walk_time / drive_time / amenity / quiet / view / school_access claims? If not, we can hand-fatten the `raw_copy` after scraping (which is fine — fixtures are artisanal).
2. Do we want `demo_tampines.json` to be an "outright deceptive" listing (per TODO.md), meaning we deliberately edit a scraped description to inject false claims? If yes, that's a post-scrape manual step, and we should flag that the fixture is synthetic for transparency in the README.
3. Should the stretch "live scrape" path stay as Python Playwright (likely to 403) or be dropped from the demo entirely, with a "live mode requires playwriter" footnote? My vote: keep it as Playwright and let it fail gracefully to fixtures — code is already planned; removing it would require spec churn.

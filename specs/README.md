# Specs Index

| Spec | Purpose | Status |
|---|---|---|
| [sse-contract.md](sse-contract.md) | Frozen event shapes between backend and frontend | **Frozen** |
| [grabmaps-client.md](grabmaps-client.md) | GrabMaps REST + MCP client surfaces, field-shape truth table | **Frozen** |
| [audit-agent.md](audit-agent.md) | Rule-based per-claim verifiers, scoring, map-event generation | **Frozen** |
| [listing-extractor.md](listing-extractor.md) | Scraper + Claude claim extraction + fixtures | Draft |

## Editing rules

- Any change to a **Frozen** spec requires updating both the backend and frontend
  implementation in the same change. If you can't, revert the spec edit first.
- Drafts may change without coordination.
- The `sse-contract.md` is the sharpest frozen surface — don't touch it without
  checking both sides in one commit.

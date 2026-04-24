You are parsing a Singapore property listing into structured, **verifiable**
claims for an independent map-API audit.

Given the raw listing copy, output a JSON object. Claims must be specific
enough to verify against a map API (walk times, distances, POI categories,
street view, traffic patterns). Puffery like "luxurious" or "dream home" is
dropped silently.

## Hard rules

1. Only emit claims whose `type` is one of **exactly these six**:
   `walk_time`, `drive_time`, `amenity`, `quiet`, `view`, `school_access`.
   Drop anything else. Never emit an unknown type.
2. Every claim's `parsed` MUST match the exact key shape for its type (see
   table below). Missing keys → drop the claim.
3. No invention. If the copy does not state minutes for a walk/drive claim,
   drop the claim.
4. Maximum 8 claims per listing.
5. `id`s are short slugs like `c-01`, `c-02`, ... in emission order.

## Parsed key shapes

| type | parsed keys |
|---|---|
| `walk_time` | `{"target": str, "minutes": number, "mode": "walk"}` |
| `drive_time` | `{"target": str, "minutes": number, "mode": "drive"}` |
| `amenity` | `{"category": str, "proximity_phrase": str}` |
| `quiet` | `{"claim_phrase": str}` |
| `view` | `{"claim_phrase": str, "direction_if_stated": str \| null}` |
| `school_access` | `{"target_type": "primary" \| "secondary", "target_name": str \| null}` |

## Also extract

- `address`: full property address
- `price_sgd`: integer, no currency symbol (null if absent)
- `bedrooms`: integer (null if absent)
- `sqft`: integer (null if absent)

## Output

Return ONLY a JSON object of shape:

```json
{
  "address": "...",
  "price_sgd": 0,
  "bedrooms": 0,
  "sqft": 0,
  "claims": [
    {"id": "c-01", "type": "walk_time", "raw_text": "...", "parsed": {...}}
  ]
}
```

No prose, no code-fence. Just the JSON.

## Listing copy

---
{copy}
---

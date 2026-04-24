"""
Unified GrabMaps facade.

Composes the REST (http_client) and MCP (mcp_client) surfaces. The audit
agent uses this for ALL evidence calls; MCP is only opened explicitly for
the geocode so the terminal log shows a real round-trip.
"""
from __future__ import annotations

import os
from typing import Any

from .http_client import GrabMapsHTTP, Place
from .mcp_client import GrabMapsMCP, MCPUnavailable


class GrabMaps:
    """Owns the HTTP + MCP clients and exposes a single async context."""

    def __init__(
        self,
        api_key: str | None = None,
        mcp_bearer: str | None = None,
        cache_dir: Any = None,
    ):
        self.http = GrabMapsHTTP(api_key=api_key, cache_dir=cache_dir)
        self.mcp = GrabMapsMCP(bearer=mcp_bearer)
        self._mcp_initialised = False

    async def __aenter__(self) -> "GrabMaps":
        await self.http.__aenter__()
        await self.mcp.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.mcp.__aexit__(*exc)
        await self.http.__aexit__(*exc)

    # ------------------------------------------ direct passthroughs to HTTP

    async def search(self, *args: Any, **kwargs: Any) -> list[Place]:
        return await self.http.search(*args, **kwargs)

    async def nearby(
        self,
        lat: float,
        lng: float,
        radius_km: float = 1.0,
        limit: int = 20,
        keyword: str | None = None,
        **kwargs: Any,
    ) -> list[Place]:
        """Route nearby via MCP's `search_nearby_pois`. The direct REST
        endpoint `/api/v1/maps/place/v2/nearby` returns 400 for every
        documented parameter combination using our app key — see
        docs/bug-hunter.md BUG-08. MCP's `search_nearby_pois` wraps the
        same endpoint and works, so we proxy through it.

        `keyword` is applied client-side since the API has no server-side
        category filter (per MCP tool description).
        """
        from .http_client import parse_place
        if self.mcp.available:
            try:
                if not self._mcp_initialised:
                    await self.mcp.initialize()
                    self._mcp_initialised = True
                raw = await self.mcp.call_tool(
                    "search_nearby_pois",
                    {
                        "latitude": lat,
                        "longitude": lng,
                        "radius_km": radius_km,
                        "limit": max(limit * 4, limit),  # overfetch for filter
                    },
                )
                if isinstance(raw, str):
                    import json as _json
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = {}
                places_src: list[dict[str, Any]] = []
                if isinstance(raw, dict):
                    if isinstance(raw.get("places"), list):
                        places_src = raw["places"]
                    elif isinstance(raw.get("result"), dict) and isinstance(
                        raw["result"].get("places"), list
                    ):
                        places_src = raw["result"]["places"]
                places = [parse_place(p) for p in places_src]
                # If MCP gave us a usable raw set, treat its answer as canonical —
                # even a post-filter empty list. Don't fall through to a broken REST.
                if places_src:
                    if keyword:
                        kw = keyword.lower()
                        synonyms = {
                            "supermarket": ("supermarket", "grocery", "market", "fairprice", "cold storage", "sheng siong", "giant"),
                            "cafe": ("cafe", "coffee", "starbucks", "bakery", "food and beverage"),
                            "school": ("school", "primary", "secondary", "education"),
                            "clinic": ("clinic", "medical", "health", "doctor"),
                        }
                        needles = synonyms.get(kw, (kw,))
                        places = [
                            p for p in places
                            if any(
                                n in (p.name or "").lower()
                                or n in (p.business_type or "").lower()
                                or n in (p.category or "").lower()
                                for n in needles
                            )
                        ]
                    return places[:limit]
            except MCPUnavailable:
                pass
            except Exception:
                pass
        # Best-effort REST fallback (currently 400s; kept for when the
        # endpoint stabilises on this key scope).
        return await self.http.nearby(
            lat=lat, lng=lng, radius_km=radius_km, limit=limit, keyword=keyword
        )

    async def direction(self, *args: Any, **kwargs: Any):
        return await self.http.direction(*args, **kwargs)

    async def incidents_bbox(self, *args: Any, **kwargs: Any):
        return await self.http.incidents_bbox(*args, **kwargs)

    async def traffic_bbox(self, *args: Any, **kwargs: Any):
        return await self.http.traffic_bbox(*args, **kwargs)

    async def street_view(self, *args: Any, **kwargs: Any):
        return await self.http.street_view(*args, **kwargs)

    async def walk_time_minutes(self, *args: Any, **kwargs: Any):
        return await self.http.walk_time_minutes(*args, **kwargs)

    async def drive_time_minutes(self, *args: Any, **kwargs: Any):
        return await self.http.drive_time_minutes(*args, **kwargs)

    async def incident_density(self, *args: Any, **kwargs: Any):
        return await self.http.incident_density(*args, **kwargs)

    # ----------------------------------------------- MCP-backed geocode

    async def mcp_search(
        self, keyword: str, country: str = "SGP", limit: int = 1
    ) -> tuple[list[Place], bool]:
        """Try MCP `search` first; fall back to REST if MCP is unavailable.

        Returns (places, used_mcp).
        """
        if self.mcp.available:
            try:
                if not self._mcp_initialised:
                    await self.mcp.initialize()
                    self._mcp_initialised = True
                raw = await self.mcp.call_tool(
                    "search",
                    {"keyword": keyword, "country": country, "limit": limit},
                )
                # Normalise: raw may be a JSON string, dict, or already-decoded list
                if isinstance(raw, str):
                    import json as _json
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = {}
                places_src: list[dict[str, Any]] = []
                if isinstance(raw, dict):
                    if isinstance(raw.get("places"), list):
                        places_src = raw["places"]
                    elif isinstance(raw.get("result"), dict) and isinstance(
                        raw["result"].get("places"), list
                    ):
                        places_src = raw["result"]["places"]
                from .http_client import parse_place

                places = [parse_place(p) for p in places_src][:limit]
                # If MCP returned zero places but is reachable, still prefer its answer
                if places:
                    return places, True
            except MCPUnavailable:
                pass
            except Exception:
                pass
        # Fallback to REST
        places = await self.http.search(keyword=keyword, country=country, limit=limit)
        return places, False

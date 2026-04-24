"""
Async REST client for maps.grab.com.

Parser contracts follow `specs/grabmaps-client.md` verbatim — response fields
are nested under `location.latitude`/`location.longitude` (NOT flat `lat`/`lng`).
The original scaffold silently returned `0.0` coords because it tried the flat
shape first — this module refuses to be that bug.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from math import cos, radians, sqrt
from pathlib import Path
from typing import Any, Literal

import httpx

BASE_URL = "https://maps.grab.com"
CACHE_DIR = Path(os.getenv("GM_CACHE_DIR", ".cache/grabmaps"))


# --------------------------------------------------------------- dataclasses


@dataclass
class Place:
    name: str
    address: str
    lat: float
    lng: float
    category: str | None = None
    business_type: str | None = None
    poi_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Route:
    distance_m: float
    duration_s: float
    geometry: str | None
    profile: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Photo:
    id: str
    lat: float
    lng: float
    heading: float
    thumb_url: str
    full_url: str
    cdn_url: str | None = None
    date: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------- parser helpers


def parse_place(p: dict[str, Any]) -> Place:
    """Parse one /poi/v1/search or /place/v2/nearby place entry.

    lat/lng live under `location.latitude`/`location.longitude`. Address is
    `formatted_address`. Name is `name`. Category is a flat string.
    """
    loc = p.get("location") or {}
    # Defensive: if a caller hands us an already-flat shape (e.g. fixture), try those
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    if lat is None:
        lat = p.get("latitude") or p.get("lat") or 0.0
    if lng is None:
        lng = p.get("longitude") or p.get("lng") or 0.0
    return Place(
        name=p.get("name", ""),
        address=p.get("formatted_address") or p.get("address", ""),
        lat=float(lat),
        lng=float(lng),
        category=p.get("category"),
        business_type=p.get("business_type"),
        poi_id=p.get("poi_id"),
        raw=p,
    )


def parse_route(data: dict[str, Any], profile: str) -> Route:
    routes = data.get("routes") or []
    if not routes:
        return Route(0.0, 0.0, None, profile, raw=data)
    r = routes[0]
    return Route(
        distance_m=float(r.get("distance", 0.0)),
        duration_s=float(r.get("duration", 0.0)),
        geometry=r.get("geometry"),
        profile=profile,
        raw=r,
    )


def parse_photos(data: dict[str, Any]) -> list[Photo]:
    """Photos are nested under result.data[]; lat/lng/heading are strings."""
    result = data.get("result") or {}
    items = result.get("data") or []
    photos: list[Photo] = []
    for p in items:
        try:
            photos.append(
                Photo(
                    id=str(p.get("id", "")),
                    lat=float(p.get("lat") or 0.0),
                    lng=float(p.get("lng") or 0.0),
                    heading=float(p.get("heading") or 0.0),
                    thumb_url=p.get("fileurlTh") or "",
                    full_url=p.get("fileurlLTh") or p.get("fileurl", ""),
                    cdn_url=p.get("imageLthUrl"),
                    date=p.get("dateAdded"),
                    raw=p,
                )
            )
        except (TypeError, ValueError):
            continue
    return photos


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    """Flat-earth approximation — fine at SG scale."""
    lat_rad = radians((a_lat + b_lat) / 2)
    dx = (b_lng - a_lng) * cos(lat_rad) * 111.0
    dy = (b_lat - a_lat) * 111.0
    return sqrt(dx * dx + dy * dy)


# ----------------------------------------------------------------- client


class GrabMapsHTTP:
    """Async httpx client with disk cache."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 20.0,
        cache_dir: Path | None = None,
    ):
        self.api_key = api_key or os.environ.get("GRAB_MAPS_API_KEY", "")
        self.timeout = timeout
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GrabMapsHTTP":
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------- cache

    def _cache_key(self, path: str, params: dict[str, Any]) -> Path:
        payload = json.dumps(
            {"transport": "http", "p": path, "q": params}, sort_keys=True, default=str
        )
        h = hashlib.sha256(payload.encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}.json"

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | list[tuple[str, Any]],
        bust: bool = False,
    ) -> dict[str, Any]:
        cache_path = self._cache_key(path, params)
        if cache_path.exists() and not bust:
            try:
                return json.loads(cache_path.read_text())
            except json.JSONDecodeError:
                pass
        if self._client is None:
            raise RuntimeError("GrabMapsHTTP must be used as an async context manager")
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        data = resp.json()
        try:
            cache_path.write_text(json.dumps(data))
        except OSError:
            pass
        return data

    # --------------------------------------------------------- endpoints

    async def search(
        self,
        keyword: str,
        country: str = "SGP",
        location: tuple[float, float] | None = None,
        limit: int = 5,
        bust: bool = False,
    ) -> list[Place]:
        """POI/address search. `limit` is ignored server-side (BUG-05) so we
        always slice client-side."""
        params: dict[str, Any] = {
            "keyword": keyword,
            "country": country,
            "limit": limit,
        }
        if location:
            params["location"] = f"{location[0]},{location[1]}"
        data = await self._get("/api/v1/maps/poi/v1/search", params, bust=bust)
        places = [parse_place(p) for p in data.get("places", [])]
        # BUG-05: slice client-side
        return places[:limit]

    async def nearby(
        self,
        lat: float,
        lng: float,
        radius_km: float = 1.0,
        limit: int = 20,
        keyword: str | None = None,
        bust: bool = False,
    ) -> list[Place]:
        """Nearby POIs. radius_km is kilometres, NOT metres."""
        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lng,
            "radius_km": radius_km,
            "limit": limit,
        }
        if keyword:
            params["keyword"] = keyword
        data = await self._get("/api/v1/maps/place/v2/nearby", params, bust=bust)
        places = [parse_place(p) for p in data.get("places", [])]
        return places[:limit]

    async def direction(
        self,
        waypoints: list[tuple[float, float]],
        profile: Literal[
            "driving", "walking", "cycling", "motorcycle", "tricycle"
        ] = "walking",
        overview: str = "simplified",
        bust: bool = False,
    ) -> Route:
        """A→B routing. Our code passes (lat, lng) tuples; we flip to
        `lng,lat` for the query string (coord-order swap point #1).

        The endpoint wants REPEATED `coordinates` query params, one per
        waypoint — NOT a semicolon-joined string. The latter 400s.
        """
        params: list[tuple[str, Any]] = []
        for lat, lng in waypoints:
            params.append(("coordinates", f"{lng},{lat}"))
        params.append(("profile", profile))
        params.append(("overview", overview))
        data = await self._get("/api/v1/maps/eta/v1/direction", params, bust=bust)
        return parse_route(data, profile)

    async def traffic_bbox(
        self,
        nw_lat: float,
        nw_lng: float,
        se_lat: float,
        se_lng: float,
        bust: bool = False,
    ) -> dict[str, Any]:
        params = {
            "nw_lat": nw_lat,
            "nw_lng": nw_lng,
            "se_lat": se_lat,
            "se_lng": se_lng,
            "linkReference": "GRAB_WAY",
        }
        return await self._get("/api/v1/traffic/real-time/bbox", params, bust=bust)

    async def incidents_bbox(
        self,
        nw_lat: float,
        nw_lng: float,
        se_lat: float,
        se_lng: float,
        bust: bool = False,
    ) -> list[dict[str, Any]]:
        """The direct REST endpoint rejects `nw_lat/nw_lng/se_lat/se_lng`
        with "invalid lat/lon" despite that being the documented shape. The
        working param names are `lat1/lat2/lon1/lon2` plus the
        `linkReference=GRAB_WAY` marker that the codegen docs describe.
        """
        params = {
            "lat1": nw_lat,
            "lat2": se_lat,
            "lon1": nw_lng,
            "lon2": se_lng,
            "linkReference": "GRAB_WAY",
        }
        data = await self._get(
            "/api/v1/traffic/incidents/bbox", params, bust=bust
        )
        # Spec: response is either `{incidents: [...]}` or `{data: [...]}`
        return data.get("incidents", data.get("data", []))

    async def street_view(
        self,
        lat: float,
        lng: float,
        radius: int = 200,
        limit: int = 8,
        bust: bool = False,
    ) -> list[Photo]:
        """Street-view photos. Nested under result.data[]."""
        params: dict[str, Any] = {
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "limit": limit,
            "orderBy": "distance",
            "orderDirection": "asc",
            "projection": "SPHERE",
        }
        data = await self._get(
            "/api/v1/openstreetcam-api/2.0/photo/", params, bust=bust
        )
        photos = parse_photos(data)
        return photos[:limit]

    # -------------------------------------------- derived utility methods

    async def walk_time_minutes(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> tuple[float, Route]:
        r = await self.direction([origin, destination], profile="walking")
        return round(r.duration_s / 60.0, 1), r

    async def drive_time_minutes(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> tuple[float, Route]:
        r = await self.direction([origin, destination], profile="driving")
        return round(r.duration_s / 60.0, 1), r

    async def incident_density(
        self, lat: float, lng: float, radius_m: int = 500
    ) -> tuple[int, list[dict[str, Any]]]:
        delta = radius_m / 111_000.0
        incidents = await self.incidents_bbox(
            nw_lat=lat + delta,
            nw_lng=lng - delta,
            se_lat=lat - delta,
            se_lng=lng + delta,
        )
        return len(incidents), incidents

"""
Tiny fake GrabMaps facade for tests.

Exposes the same async methods the verifiers use but returns canned data
driven by per-fixture profiles. MCP is mocked fully — `mcp_search` simply
proxies to `search` and reports `used_mcp=False`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.maps.http_client import Photo, Place, Route


@dataclass
class FakeProfile:
    """Per-fixture canned response profile."""

    origin: tuple[float, float]
    # search(keyword) -> list[Place]
    search_responses: dict[str, list[Place]] = field(default_factory=dict)
    default_search: list[Place] = field(default_factory=list)
    # keyed by destination poi_id -> (walk_min, drive_min)
    durations: dict[str, tuple[float, float]] = field(
        default_factory=dict
    )
    # nearby(keyword) -> list[Place]
    nearby_responses: dict[str, list[Place]] = field(default_factory=dict)
    default_nearby: list[Place] = field(default_factory=list)
    # incident count in 500m
    incident_density: int = 0
    # street view photos
    photos: list[Photo] = field(default_factory=list)


class FakeGrabMaps:
    """Async context manager implementing the GrabMaps interface."""

    def __init__(self, profile: FakeProfile):
        self.profile = profile
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeGrabMaps":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def _log(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    async def mcp_search(
        self, keyword: str, country: str = "SGP", limit: int = 1
    ) -> tuple[list[Place], bool]:
        self._log("mcp_search", keyword=keyword)
        places = self.profile.search_responses.get(
            keyword, self.profile.default_search
        )
        return places[:limit], False

    async def search(
        self,
        keyword: str,
        country: str = "SGP",
        location: tuple[float, float] | None = None,
        limit: int = 5,
        **kw: Any,
    ) -> list[Place]:
        self._log("search", keyword=keyword)
        places = self.profile.search_responses.get(
            keyword, self.profile.default_search
        )
        return places[:limit]

    async def nearby(
        self,
        lat: float,
        lng: float,
        radius_km: float = 1.0,
        limit: int = 20,
        keyword: str | None = None,
        **kw: Any,
    ) -> list[Place]:
        self._log("nearby", keyword=keyword)
        places = self.profile.nearby_responses.get(
            keyword or "", self.profile.default_nearby
        )
        return places[:limit]

    async def walk_time_minutes(
        self, origin: tuple[float, float], dest: tuple[float, float]
    ) -> tuple[float, Route]:
        self._log("walk_time_minutes", dest=dest)
        key = self._dest_key(dest)
        walk, _ = self.profile.durations.get(key, (10.0, 20.0))
        return walk, Route(
            distance_m=walk * 80,
            duration_s=walk * 60,
            geometry="_fakepoly_",
            profile="walking",
        )

    async def drive_time_minutes(
        self, origin: tuple[float, float], dest: tuple[float, float]
    ) -> tuple[float, Route]:
        self._log("drive_time_minutes", dest=dest)
        key = self._dest_key(dest)
        _, drive = self.profile.durations.get(key, (10.0, 20.0))
        return drive, Route(
            distance_m=drive * 500,
            duration_s=drive * 60,
            geometry="_fakepoly_",
            profile="driving",
        )

    async def incident_density(
        self, lat: float, lng: float, radius_m: int = 500
    ) -> tuple[int, list[dict[str, Any]]]:
        self._log("incident_density", lat=lat, lng=lng)
        return self.profile.incident_density, []

    async def street_view(
        self, lat: float, lng: float, radius: int = 200, limit: int = 8, **kw: Any
    ) -> list[Photo]:
        self._log("street_view", lat=lat, lng=lng)
        return self.profile.photos[:limit]

    @staticmethod
    def _dest_key(dest: tuple[float, float]) -> str:
        return f"{round(dest[0], 5)}_{round(dest[1], 5)}"


# --------------------------------------------------------------- fixtures


def _place(
    name: str, lat: float, lng: float, category: str = "commercial building"
) -> Place:
    return Place(
        name=name,
        address=f"{name}, Singapore",
        lat=lat,
        lng=lng,
        category=category,
        raw={"name": name},
    )


def _photo(pid: str, lat: float, lng: float) -> Photo:
    return Photo(
        id=pid,
        lat=lat,
        lng=lng,
        heading=180.0,
        thumb_url=f"https://example.test/photo/{pid}_th.jpg",
        full_url=f"https://example.test/photo/{pid}_lth.jpg",
        cdn_url=None,
        date="2024-01-01",
    )


def bishan_profile() -> FakeProfile:
    """Bishan is OVERSTATED on almost everything. Target score 30-40."""
    origin = (1.3519, 103.8481)
    # MRT slightly farther than claimed (14 min vs claimed 5) → false or overstated
    bishan_mrt = _place("Bishan MRT", 1.3540, 103.8510)
    raffles = _place("Raffles Place", 1.2840, 103.8510)
    catholic_high = _place("Catholic High School", 1.3600, 103.8550)
    supermarket1 = _place("Sheng Siong Bishan", 1.3530, 103.8495)
    supermarket2 = _place("NTUC Bishan", 1.3540, 103.8470)
    prof = FakeProfile(
        origin=origin,
        search_responses={
            "Bishan MRT": [bishan_mrt],
            "Raffles Place": [raffles],
            "primary school": [catholic_high],
        },
        default_search=[bishan_mrt],
        durations={
            FakeGrabMaps._dest_key((bishan_mrt.lat, bishan_mrt.lng)): (10.0, 14.0),
            # Claimed 5 min, real 10 → ratio 2.0 → false
            FakeGrabMaps._dest_key((raffles.lat, raffles.lng)): (90.0, 20.0),
            # Claimed 12 drive → real 20 → ratio 1.67 → false (just over 1.6)
            FakeGrabMaps._dest_key((catholic_high.lat, catholic_high.lng)): (12.0, 3.0),
            # Claimed walking distance, real 12 → true (within 10-15 band = overstated)
        },
        nearby_responses={
            "supermarket": [supermarket1, supermarket2],
            "clinic": [_place("Clinic A", 1.3525, 103.8485)],
        },
        default_nearby=[supermarket1, supermarket2],
        incident_density=12,  # 20 > 12 > 5 → overstated for quiet
        photos=[_photo("p1", 1.3519, 103.8481), _photo("p2", 1.3520, 103.8482)],
    )
    return prof


def tampines_profile() -> FakeProfile:
    """Tampines is OUTRIGHT FALSE on most claims. Target score 10-25."""
    origin = (1.3541, 103.9433)
    tampines_mrt = _place("Tampines MRT", 1.3541, 103.9433)
    mbs = _place("Marina Bay Sands", 1.2836, 103.8607)
    poi_ching = _place("Poi Ching School", 1.3620, 103.9500)
    prof = FakeProfile(
        origin=origin,
        search_responses={
            "Tampines MRT": [tampines_mrt],
            "Marina Bay Sands": [mbs],
            "primary school": [poi_ching],
        },
        default_search=[tampines_mrt],
        durations={
            # Claimed 3 min → real 15 → ratio 5.0 → false
            FakeGrabMaps._dest_key((tampines_mrt.lat, tampines_mrt.lng)): (15.0, 6.0),
            # Claimed 15 min drive → real 40 → ratio 2.67 → false
            FakeGrabMaps._dest_key((mbs.lat, mbs.lng)): (200.0, 40.0),
            # Claimed "next door" → real 22 min walk → false
            FakeGrabMaps._dest_key((poi_ching.lat, poi_ching.lng)): (22.0, 5.0),
        },
        nearby_responses={
            # "at least 10 supermarkets" — we return zero → false
            "supermarket": [],
        },
        default_nearby=[],
        incident_density=35,  # > 20 → quiet claim false
        photos=[_photo("p1", 1.3541, 103.9433)],
    )
    return prof


def tiong_bahru_profile() -> FakeProfile:
    """Tiong Bahru is HONEST. Target score 75-90."""
    origin = (1.2870, 103.8289)
    tb_mrt = _place("Tiong Bahru MRT", 1.2860, 103.8270)
    raffles = _place("Raffles Place", 1.2840, 103.8510)
    zhangde = _place("Zhangde Primary School", 1.2830, 103.8210)
    cafe = _place("Tiong Bahru Bakery", 1.2865, 103.8275)
    market = _place("Tiong Bahru Market", 1.2850, 103.8280)
    prof = FakeProfile(
        origin=origin,
        search_responses={
            "Tiong Bahru MRT": [tb_mrt],
            "Raffles Place": [raffles],
            "primary school": [zhangde],
        },
        default_search=[tb_mrt],
        durations={
            # Claimed 10 min → real 10 → true
            FakeGrabMaps._dest_key((tb_mrt.lat, tb_mrt.lng)): (10.0, 3.0),
            # Claimed 14 drive → real 15 → ratio 1.07 → true
            FakeGrabMaps._dest_key((raffles.lat, raffles.lng)): (80.0, 15.0),
            # Claimed 12 walk → real 12 → true
            FakeGrabMaps._dest_key((zhangde.lat, zhangde.lng)): (12.0, 3.0),
        },
        nearby_responses={
            "cafe": [
                cafe,
                _place("Plain Vanilla", 1.2868, 103.8278),
                _place("40 Hands Coffee", 1.2871, 103.8283),
                _place("Merchants of Asia", 1.2869, 103.8285),
                _place("Flock Cafe", 1.2872, 103.8282),
                _place("Curious Palette", 1.2870, 103.8279),
            ],
            "wet market": [market],
            "bakery": [cafe],
        },
        default_nearby=[cafe, market, _place("Plain Vanilla", 1.2868, 103.8278),
                        _place("40 Hands Coffee", 1.2871, 103.8283),
                        _place("Merchants of Asia", 1.2869, 103.8285),
                        _place("Another Spot", 1.2870, 103.8280)],
        incident_density=3,  # <= 5 → true
        photos=[_photo("p1", 1.2870, 103.8289), _photo("p2", 1.2871, 103.8290)],
    )
    return prof

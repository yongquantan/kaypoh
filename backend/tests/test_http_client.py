"""
Parser regression tests — BUG territory.

The original scaffold returned `0.0` for every lat/lng because it tried
flat `latitude`/`lat` keys before the actual nested `location.latitude`.
These tests lock the correct parse path in place.
"""
from __future__ import annotations

from backend.maps.http_client import parse_photos, parse_place, parse_route


SEARCH_PAYLOAD = {
    "is_confident": True,
    "places": [
        {
            "name": "Bishan MRT",
            "formatted_address": "200 Bishan, Singapore, 579827",
            "location": {"latitude": 1.3518553, "longitude": 103.8481119},
            "category": "commercial building",
            "business_type": "station",
            "city": "Singapore City",
            "country_code": "SGP",
            "poi_id": "IT.2KBW91ETVY25Y",
            "postcode": "579827",
        }
    ],
    "uuid": "7d8ccaf6-...",
}


DIRECTION_PAYLOAD = {
    "code": "ok",
    "routes": [
        {
            "distance": 2349.465,
            "duration": 1901.1,
            "geometry": "wkopAsimaeE...",
            "legs": [{"distance": 2349.465, "duration": 1901.1}],
        }
    ],
}


PHOTO_PAYLOAD = {
    "status": {"httpCode": 200, "apiCode": 600},
    "result": {
        "data": [
            {
                "id": "1865261337",
                "lat": "1.351835",
                "lng": "103.848072",
                "heading": "192.12",
                "fieldOfView": "360",
                "fileurl": "https://storage13.openstreetcam.org/files/.../{{sizeprefix}}/8320233.jpg",
                "fileurlTh": "https://storage13.openstreetcam.org/files/.../th/8320233.jpg",
                "fileurlLTh": "https://storage13.openstreetcam.org/files/.../lth/8320233.jpg",
                "imageLthUrl": "https://cdn.kartaview.org/pr:sharp/abc",
                "dateAdded": "2023-11-28 07:06:18",
            }
        ]
    },
}


def test_parse_place_uses_nested_location():
    p = parse_place(SEARCH_PAYLOAD["places"][0])
    assert p.name == "Bishan MRT"
    assert p.lat != 0.0
    assert p.lng != 0.0
    assert abs(p.lat - 1.3518553) < 1e-6
    assert abs(p.lng - 103.8481119) < 1e-6
    assert p.address == "200 Bishan, Singapore, 579827"
    assert p.category == "commercial building"
    assert p.poi_id == "IT.2KBW91ETVY25Y"


def test_parse_route_metres_and_seconds():
    r = parse_route(DIRECTION_PAYLOAD, profile="walking")
    assert r.distance_m == 2349.465
    assert r.duration_s == 1901.1
    assert r.geometry == "wkopAsimaeE..."
    assert r.profile == "walking"


def test_parse_photos_string_floats_and_thumb_urls():
    photos = parse_photos(PHOTO_PAYLOAD)
    assert len(photos) == 1
    ph = photos[0]
    assert isinstance(ph.lat, float) and isinstance(ph.lng, float)
    assert abs(ph.lat - 1.351835) < 1e-6
    assert abs(ph.lng - 103.848072) < 1e-6
    assert abs(ph.heading - 192.12) < 1e-4
    assert "th/" in ph.thumb_url
    assert "lth/" in ph.full_url
    # Must NOT carry the raw {{sizeprefix}} placeholder
    assert "{{sizeprefix}}" not in ph.thumb_url


def test_parse_place_flat_fallback_does_not_return_zero_on_nested():
    """Regression guard: a nested payload must NOT fall through to 0.0."""
    p = parse_place({"name": "X", "location": {"latitude": 1.23, "longitude": 103.45}})
    assert p.lat == 1.23
    assert p.lng == 103.45


def test_parse_photos_empty_result_is_empty_list():
    assert parse_photos({"result": {"data": []}}) == []
    assert parse_photos({}) == []

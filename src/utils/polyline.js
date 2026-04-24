// Google-encoded polyline decoder, configurable precision.
// GrabMaps direction responses default to polyline6 (precision=6).
// Returns an array of [lat, lng] pairs.

export function decodePolyline(str, precision = 6) {
  if (!str || typeof str !== 'string') return []
  const factor = Math.pow(10, precision)
  const coordinates = []
  let index = 0
  let lat = 0
  let lng = 0

  while (index < str.length) {
    let result = 0
    let shift = 0
    let byte
    do {
      byte = str.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    const dlat = result & 1 ? ~(result >> 1) : result >> 1
    lat += dlat

    result = 0
    shift = 0
    do {
      byte = str.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    const dlng = result & 1 ? ~(result >> 1) : result >> 1
    lng += dlng

    coordinates.push([lat / factor, lng / factor])
  }

  return coordinates
}

// Helper: polyline6 decoded to GeoJSON LineString coords ([lng, lat] for MapLibre).
export function polyline6ToLngLat(str) {
  return decodePolyline(str, 6).map(([lat, lng]) => [lng, lat])
}

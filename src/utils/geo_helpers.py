"""
Geospatial and Coordinate Utility Functions.

Provides geodesic distance computations, navigation bearing calculations,
spatial bounds expansions, and geometry format conversions.
"""

import math
from typing import Any, Dict, List, Optional, Tuple


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate great-circle distance between two points on the WGS84 ellipsoid.

    Args:
        lat1, lon1: Coordinates of first point in decimal degrees.
        lat2, lon2: Coordinates of second point in decimal degrees.

    Returns:
        Great-circle distance in kilometers.
    """
    r_earth = 6371.0088  # Mean Earth radius in km

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


def calculate_bearing_deg(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate initial compass bearing from point 1 to point 2.

    Args:
        lat1, lon1: Origin coordinates.
        lat2, lon2: Destination coordinates.

    Returns:
        Bearing in degrees [0, 360).
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        delta_lambda
    )
    initial_bearing = math.degrees(math.atan2(y, x))
    return (initial_bearing + 360.0) % 360.0


def compute_bounding_box(
    coords: List[Tuple[float, float]],
    buffer_ratio: float = 0.1,
) -> Dict[str, float]:
    """
    Compute buffered bounding box for an array of (latitude, longitude) pairs.

    Args:
        coords: List of (lat, lon) coordinates.
        buffer_ratio: Expansion margin ratio.

    Returns:
        Dictionary with min_lat, max_lat, min_lon, max_lon.
    """
    if not coords:
        return {"min_lat": 0.0, "max_lat": 0.0, "min_lon": 0.0, "max_lon": 0.0}

    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    lat_buf = (max_lat - min_lat) * buffer_ratio
    lon_buf = (max_lon - min_lon) * buffer_ratio

    return {
        "min_lat": min_lat - lat_buf,
        "max_lat": max_lat + lat_buf,
        "min_lon": min_lon - lon_buf,
        "max_lon": max_lon + lon_buf,
    }


def polygon_to_geojson(
    coordinates: List[Tuple[float, float]],
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert a list of (lat, lon) vertices into a standard GeoJSON Feature dictionary.

    Args:
        coordinates: List of (latitude, longitude) vertices.
        properties: Optional metadata dictionary.

    Returns:
        GeoJSON Feature dictionary.
    """
    # GeoJSON coordinates format is [longitude, latitude]
    ring = [[lon, lat] for lat, lon in coordinates]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])  # Close polygon ring

    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring],
        },
        "properties": properties or {},
    }

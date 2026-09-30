"""Utilidades geométricas sin dependencias externas."""
from __future__ import annotations

import math

EARTH_R = 6371008.8  # metros


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def offset_point(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Desplaza un punto north_m hacia el norte y east_m hacia el este (aprox. local)."""
    dlat = math.degrees(north_m / EARTH_R)
    dlon = math.degrees(east_m / (EARTH_R * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def polyline_length_within(coords: list[tuple[float, float]], center: tuple[float, float], radius_m: float) -> float:
    """Suma la longitud de los tramos cuyos dos extremos están dentro del radio."""
    total = 0.0
    for (lat1, lon1), (lat2, lon2) in zip(coords, coords[1:]):
        if (
            haversine_m(lat1, lon1, center[0], center[1]) <= radius_m
            and haversine_m(lat2, lon2, center[0], center[1]) <= radius_m
        ):
            total += haversine_m(lat1, lon1, lat2, lon2)
    return total


def grid_points(center: tuple[float, float], radius_m: float, n: int) -> tuple[list[dict], float]:
    """Malla n x n que cubre el cuadrado [-R, R]. Marca qué puntos caen dentro del círculo."""
    if n < 2:
        raise ValueError("n debe ser >= 2")
    step = 2 * radius_m / (n - 1)
    pts = []
    for i in range(n):
        for j in range(n):
            north = -radius_m + i * step
            east = -radius_m + j * step
            lat, lon = offset_point(center[0], center[1], north, east)
            pts.append({"i": i, "j": j, "lat": lat, "lon": lon, "inside": math.hypot(north, east) <= radius_m})
    return pts, step


def percentile(values: list[float], q: float) -> float:
    """Percentil con interpolación lineal (q entre 0 y 100)."""
    if not values:
        raise ValueError("lista vacía")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)

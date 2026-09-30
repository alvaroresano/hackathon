"""Acceso a las fuentes de datos abiertos: Nominatim, Overpass (OpenStreetMap) y Open-Meteo."""
from __future__ import annotations

import requests

from .http import DataUnavailable, request_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

# Rectángulo aproximado de Gipuzkoa (izquierda, arriba, derecha, abajo) en grados.
GIPUZKOA_VIEWBOX = (-2.60, 43.45, -1.68, 42.85)

LICENSES = {
    "nominatim": "Datos © colaboradores de OpenStreetMap, licencia ODbL.",
    "overpass": "Datos © colaboradores de OpenStreetMap, licencia ODbL.",
    "open-meteo": "Elevación de Open-Meteo (basada en Copernicus DEM, ~90 m). Consulte sus condiciones de uso y atribución.",
}


def _inside_viewbox(lat: float, lon: float) -> bool:
    left, top, right, bottom = GIPUZKOA_VIEWBOX
    return left <= lon <= right and bottom <= lat <= top


def geocode(place: str) -> tuple[dict, dict]:
    """Resuelve un topónimo dentro de Gipuzkoa. Devuelve (resultado, meta)."""
    left, top, right, bottom = GIPUZKOA_VIEWBOX
    params = {
        "q": place,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "es",
        "viewbox": f"{left},{top},{right},{bottom}",
        "bounded": 1,
    }
    data, meta = request_json("GET", NOMINATIM_URL, params=params)
    if not data:
        raise LookupError(f"No se encontró '{place}' dentro de Gipuzkoa.")
    r = data[0]
    lat, lon = float(r["lat"]), float(r["lon"])
    if not _inside_viewbox(lat, lon):
        raise LookupError(f"'{place}' se resolvió fuera de Gipuzkoa ({lat:.4f}, {lon:.4f}).")
    return {"lat": lat, "lon": lon, "display_name": r.get("display_name", place)}, meta


def elevations(points: list[tuple[float, float]]) -> tuple[list[float | None], list[dict]]:
    """Elevaciones en metros para una lista de (lat, lon). Máx. 100 puntos por petición."""
    out: list[float | None] = []
    metas: list[dict] = []
    for i in range(0, len(points), 100):
        chunk = points[i : i + 100]
        params = {
            "latitude": ",".join(f"{la:.5f}" for la, _ in chunk),
            "longitude": ",".join(f"{lo:.5f}" for _, lo in chunk),
        }
        data, meta = request_json("GET", OPEN_METEO_ELEVATION_URL, params=params)
        vals = data.get("elevation") if isinstance(data, dict) else None
        if not isinstance(vals, list) or len(vals) != len(chunk):
            raise DataUnavailable("Open-Meteo devolvió una respuesta de elevación con formato inesperado.")
        out.extend(None if v is None else float(v) for v in vals)
        metas.append(meta)
    return out, metas


def overpass(query: str) -> tuple[dict, dict]:
    """Ejecuta una consulta Overpass QL probando varios servidores."""
    last: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            data, meta = request_json("POST", endpoint, data={"data": query}, timeout=150)
            if not isinstance(data, dict) or "elements" not in data:
                raise DataUnavailable("Respuesta de Overpass sin campo 'elements'.")
            return data, meta
        except (DataUnavailable, requests.RequestException) as exc:
            last = exc
    raise DataUnavailable(f"Overpass no disponible: {last}")

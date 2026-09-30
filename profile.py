"""Construcción del perfil de una zona: pendiente, infraestructura ciclista y proxies de demanda."""
from __future__ import annotations

import math
import statistics

from . import sources
from .geo import grid_points, haversine_m, percentile, polyline_length_within
from .http import DataUnavailable
from .session import Session

STREET_CLASSES = {"residential", "tertiary", "secondary", "primary", "unclassified", "living_street"}
CYCLE_VALUES = {"lane", "track", "opposite_lane", "opposite_track"}
CYCLE_KEYS = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")

COUNT_KEYS = ["buildings", "shops", "food_amenities", "offices", "bus_stops", "rail_stops"]

DEFINITION_NOTE = (
    "La 'zona' es un círculo alrededor del punto que devuelve el geocodificador, no el límite administrativo."
)


def infra_query(lat: float, lon: float, r: float) -> str:
    a = f"(around:{r:.0f},{lat:.6f},{lon:.6f})"
    return (
        "[out:json][timeout:90];\n"
        "(\n"
        f'  way["highway"~"^(cycleway|residential|tertiary|secondary|primary|unclassified|living_street|pedestrian)$"]{a};\n'
        f'  way["highway"~"^(path|footway)$"]["bicycle"="designated"]{a};\n'
        ");\n"
        "out tags geom;"
    )


def counts_query(lat: float, lon: float, r: float) -> str:
    a = f"(around:{r:.0f},{lat:.6f},{lon:.6f})"
    return (
        "[out:json][timeout:90];\n"
        f'nwr["building"]{a}; out count;\n'
        f'nwr["shop"]{a}; out count;\n'
        f'nwr["amenity"~"^(restaurant|cafe|bar|fast_food|pharmacy|bank|post_office|marketplace)$"]{a}; out count;\n'
        f'nwr["office"]{a}; out count;\n'
        f'node["highway"="bus_stop"]{a}; out count;\n'
        f'nwr["railway"~"^(station|halt|tram_stop)$"]{a}; out count;'
    )


def classify_way(tags: dict) -> tuple[bool, bool, bool]:
    """Devuelve (infra ciclista, peatonal, calle transitable)."""
    hw = tags.get("highway")
    cyc = (
        hw == "cycleway"
        or any(tags.get(k) in CYCLE_VALUES for k in CYCLE_KEYS)
        or (hw in ("path", "footway") and tags.get("bicycle") == "designated")
    )
    return cyc, hw == "pedestrian", hw in STREET_CLASSES


def parse_infra(data: dict, center: tuple[float, float], radius_m: float) -> dict:
    street = cycle = ped = network = 0.0
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
        length = polyline_length_within(coords, center, radius_m)
        if length <= 0:
            continue
        is_cyc, is_ped, is_street = classify_way(el.get("tags") or {})
        if is_street:
            street += length
        if is_cyc:
            cycle += length
        if is_ped:
            ped += length
        if is_street or is_cyc or is_ped:
            network += length
    return {
        "street_km": street / 1000,
        "cycle_km": cycle / 1000,
        "pedestrian_km": ped / 1000,
        "network_km": network / 1000,
    }


def parse_counts(data: dict) -> dict:
    totals = [int(e["tags"]["total"]) for e in data.get("elements", []) if e.get("type") == "count"]
    if len(totals) != len(COUNT_KEYS):
        raise DataUnavailable(
            f"Overpass devolvió {len(totals)} recuentos y se esperaban {len(COUNT_KEYS)}."
        )
    return dict(zip(COUNT_KEYS, totals))


def slope_stats(points: list[dict], elevs: list[float | None]) -> dict:
    grid = {(p["i"], p["j"]): (p, e) for p, e in zip(points, elevs)}
    slopes: list[float] = []
    for (i, j), (p, e) in grid.items():
        if not p["inside"] or e is None:
            continue
        for di, dj in ((0, 1), (1, 0)):
            q = grid.get((i + di, j + dj))
            if q and q[0]["inside"] and q[1] is not None:
                d = haversine_m(p["lat"], p["lon"], q[0]["lat"], q[0]["lon"])
                slopes.append(abs(e - q[1]) / d * 100)
    if len(slopes) < 5:
        raise DataUnavailable("No hay suficientes datos de elevación para estimar la pendiente.")
    valid = [e for (p, e) in grid.values() if p["inside"] and e is not None]
    return {
        "slope_median_pct": statistics.median(slopes),
        "slope_p90_pct": percentile(slopes, 90),
        "share_cells_over_6pct": sum(1 for s in slopes if s > 6) / len(slopes),
        "slope_pairs": len(slopes),
        "elev_min_m": min(valid),
        "elev_max_m": max(valid),
    }


def build_profile(place: str, session: Session, radius_m: int = 1500, grid_n: int = 9) -> dict:
    key = (place.strip().lower(), radius_m)
    if key in session.profiles:
        return session.profiles[key]

    geo, m_geo = sources.geocode(place)
    center = (geo["lat"], geo["lon"])
    ids = [
        session.prov.add(
            "geocodificación", "Nominatim (OpenStreetMap)", m_geo, f"Localiza '{place}'.", sources.LICENSES["nominatim"]
        )
    ]

    pts, _ = grid_points(center, radius_m, grid_n)
    elevs, m_elevs = sources.elevations([(p["lat"], p["lon"]) for p in pts])
    for m in m_elevs:
        ids.append(
            session.prov.add(
                "elevación", "Open-Meteo Elevation API", m, "Malla de puntos para estimar la pendiente.",
                sources.LICENSES["open-meteo"],
            )
        )
    slopes = slope_stats(pts, elevs)

    d_infra, m_infra = sources.overpass(infra_query(center[0], center[1], radius_m))
    ids.append(
        session.prov.add(
            "red viaria", "Overpass API (OpenStreetMap)", m_infra,
            "Calles, carriles bici y vías peatonales con geometría.", sources.LICENSES["overpass"],
        )
    )
    infra = parse_infra(d_infra, center, radius_m)

    d_counts, m_counts = sources.overpass(counts_query(center[0], center[1], radius_m))
    ids.append(
        session.prov.add(
            "recuentos", "Overpass API (OpenStreetMap)", m_counts,
            "Edificios, comercios, hostelería/servicios, oficinas y paradas.", sources.LICENSES["overpass"],
        )
    )
    counts = parse_counts(d_counts)

    area = math.pi * (radius_m / 1000) ** 2
    poi = counts["shops"] + counts["food_amenities"] + counts["offices"]
    network = infra["network_km"]
    metrics = {
        "area_km2": round(area, 2),
        **{k: round(v, 2) if isinstance(v, float) else v for k, v in slopes.items()},
        "street_km": round(infra["street_km"], 2),
        "cycle_km": round(infra["cycle_km"], 2),
        "pedestrian_km": round(infra["pedestrian_km"], 2),
        "network_km": round(network, 2),
        "cycle_share": round(infra["cycle_km"] / network, 3) if network > 0 else 0.0,
        **counts,
        "poi": poi,
        "buildings_per_km2": round(counts["buildings"] / area, 1),
        "poi_per_km2": round(poi / area, 1),
        "transit_stops_per_km2": round((counts["bus_stops"] + counts["rail_stops"]) / area, 1),
    }
    profile = {
        "place": place,
        "resolved_as": geo["display_name"],
        "center": {"lat": round(center[0], 5), "lon": round(center[1], 5)},
        "radius_m": radius_m,
        "metrics": metrics,
        "definition_note": DEFINITION_NOTE,
        "source_ids": ids,
    }
    session.profiles[key] = profile
    return profile

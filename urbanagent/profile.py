"""Construcción del perfil de una zona: pendiente, infraestructura ciclista y proxies de demanda."""
from __future__ import annotations

import math
import statistics

from . import local_data, sources
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


# Tramos de calle de al menos esta longitud para medir su pendiente con el MDT de 25 m.
STREET_SEGMENT_M = 50.0
STEEP_STREET_PCT = 6.0


def _is_elevated(tags: dict) -> bool:
    """Puentes y túneles: el MDT da la cota del terreno, no la de la vía."""
    return tags.get("bridge", "no") != "no" or tags.get("tunnel", "no") != "no"


def street_grades(data: dict, center: tuple[float, float], radius_m: float, elev_at) -> dict | None:
    """Pendiente de las calles y vías ciclistas dentro del radio, muestreando el MDT en sus vértices.

    Cada vía se recorre acumulando tramos hasta STREET_SEGMENT_M; la pendiente de cada tramo es
    |Δcota| / longitud y se pondera por su longitud. Se descartan puentes, túneles y agua.
    `elev_at(lats, lons)` devuelve la cota de cada punto (o None).
    """
    ways = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        is_cyc, _, is_street = classify_way(tags)
        if not (is_street or is_cyc) or _is_elevated(tags):
            continue
        coords = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
        coords = [c for c in coords if haversine_m(c[0], c[1], *center) <= radius_m]
        if len(coords) >= 2:
            ways.append(coords)
    if not ways:
        return None
    flat = [c for w in ways for c in w]
    elev_flat = elev_at([c[0] for c in flat], [c[1] for c in flat])
    grades: list[tuple[float, float]] = []  # (pendiente %, longitud m)
    k = 0
    for w in ways:
        zs = elev_flat[k : k + len(w)]
        k += len(w)
        start_z, acc = None, 0.0
        for i in range(len(w)):
            z = zs[i]
            if z is None or local_data.is_water(z):
                start_z, acc = None, 0.0
                continue
            if start_z is None:
                start_z, acc = z, 0.0
                continue
            acc += haversine_m(*w[i - 1], *w[i])
            if acc >= STREET_SEGMENT_M:
                grades.append((abs(z - start_z) / acc * 100, acc))
                start_z, acc = z, 0.0
    total = sum(length for _, length in grades)
    if total < 500:
        return None
    grades.sort()
    half, run, median = total / 2, 0.0, grades[-1][0]
    for g, length in grades:
        run += length
        if run >= half:
            median = g
            break
    return {
        "street_slope_median_pct": median,
        "street_share_over_6pct": sum(length for g, length in grades if g > STEEP_STREET_PCT) / total,
        "street_slope_km": total / 1000,
    }


def parse_counts(data: dict) -> dict:
    totals = [int(e["tags"]["total"]) for e in data.get("elements", []) if e.get("type") == "count"]
    if len(totals) != len(COUNT_KEYS):
        raise DataUnavailable(
            f"Overpass devolvió {len(totals)} recuentos y se esperaban {len(COUNT_KEYS)}."
        )
    return dict(zip(COUNT_KEYS, totals))


def slope_stats(points: list[dict], elevs: list[float | None]) -> dict:
    """Pendiente entre vecinos de la malla. Los puntos de agua (cota <= 0,5 m) se excluyen."""
    inside = [e for p, e in zip(points, elevs) if p["inside"]]
    water = sum(1 for e in inside if local_data.is_water(e))
    no_data = sum(1 for e in inside if e is None)
    elevs = [None if local_data.is_water(e) else e for e in elevs]
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
        "grid_points_inside": len(inside),
        "grid_points_water": water,
        "grid_points_no_data": no_data,
    }


def _elevations(pts: list[dict], session: Session) -> tuple[list[float | None], list[str], str]:
    """Elevaciones de la malla: MDT local de geoEuskadi si está disponible; si no, Open-Meteo."""
    if local_data.dem_status() is None:
        dem = local_data.dem()
        elevs = [dem.sample_xy(*local_data.to_utm(p["lat"], p["lon"])) for p in pts]
        m = local_data.source_meta("mdt")
        sid = session.prov.add("elevación", m["provider"], m, "Malla de puntos para estimar la pendiente.", m["license"])
        return elevs, [sid], "mdt_lidar_25m"
    elevs, metas = sources.elevations([(p["lat"], p["lon"]) for p in pts])
    ids = [
        session.prov.add(
            "elevación", "Open-Meteo Elevation API", m, "Malla de puntos para estimar la pendiente.",
            sources.LICENSES["open-meteo"],
        )
        for m in metas
    ]
    return elevs, ids, "open_meteo_90m"


def _population(center: tuple[float, float], radius_m: int, session: Session) -> tuple[dict | None, list[str]]:
    if local_data.sections_status() is not None:
        return None, []
    res = local_data.sections().in_circle(*local_data.to_utm(*center), radius_m)
    ids = []
    for key, note in (
        ("poblacion", "Habitantes por sección censal."),
        ("secciones", "Límites de sección para repartir la población en el círculo."),
    ):
        m = local_data.source_meta(key)
        ids.append(session.prov.add("población", m["provider"], m, note, m["license"]))
    return res, ids


def build_profile(place: str, session: Session, radius_m: int = 1500, grid_n: int | None = None) -> dict:
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

    # Con el MDT de 25 m (local, sin coste de API) la malla es de 100 m; con Open-Meteo, de 375 m.
    if grid_n is None:
        grid_n = int(2 * radius_m / 100) + 1 if local_data.dem_status() is None else 9
    pts, step = grid_points(center, radius_m, grid_n)
    elevs, elev_ids, elev_source = _elevations(pts, session)
    ids += elev_ids
    slopes = slope_stats(pts, elevs)

    d_infra, m_infra = sources.overpass(infra_query(center[0], center[1], radius_m))
    ids.append(
        session.prov.add(
            "red viaria", "Overpass API (OpenStreetMap)", m_infra,
            "Calles, carriles bici y vías peatonales con geometría.", sources.LICENSES["overpass"],
        )
    )
    infra = parse_infra(d_infra, center, radius_m)
    grades = None
    if elev_source == "mdt_lidar_25m":
        dem = local_data.dem()

        def elev_at(lats, lons):
            xs, ys = local_data.to_utm_many(lats, lons)
            return [dem.sample_xy(x, y) for x, y in zip(xs, ys)]

        grades = street_grades(d_infra, center, radius_m, elev_at)

    d_counts, m_counts = sources.overpass(counts_query(center[0], center[1], radius_m))
    ids.append(
        session.prov.add(
            "recuentos", "Overpass API (OpenStreetMap)", m_counts,
            "Edificios, comercios, hostelería/servicios, oficinas y paradas.", sources.LICENSES["overpass"],
        )
    )
    counts = parse_counts(d_counts)

    pop, pop_ids = _population(center, radius_m, session)
    ids += pop_ids

    circle_km2 = math.pi * (radius_m / 1000) ** 2
    # Con secciones censales, las densidades se calculan sobre la tierra del círculo (sin mar).
    area = pop["land_km2"] if pop and pop["land_km2"] > 0.05 else circle_km2
    poi = counts["shops"] + counts["food_amenities"] + counts["offices"]
    network = infra["network_km"]
    metrics = {
        "area_km2": round(circle_km2, 2),
        "density_area_km2": round(area, 2),
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
    if grades:
        metrics.update({k: round(v, 3 if "share" in k else 2) for k, v in grades.items()})
    if pop:
        metrics.update(
            {
                "population": round(pop["population"]),
                "pop_per_km2": round(pop["population"] / area, 1),
                "land_share": round(pop["circle_share_in_sections"], 3),
                "census_sections": pop["sections"],
            }
        )
    profile = {
        "place": place,
        "resolved_as": geo["display_name"],
        "center": {"lat": round(center[0], 5), "lon": round(center[1], 5)},
        "radius_m": radius_m,
        "metrics": metrics,
        "elevation_source": elev_source,
        "grid_step_m": round(step),
        "population_source": "eustat_secciones_2025" if pop else None,
        "definition_note": DEFINITION_NOTE,
        "source_ids": ids,
    }
    session.profiles[key] = profile
    return profile

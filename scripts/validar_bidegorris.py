"""Contraste de la infraestructura ciclista de OSM con la capa municipal de bidegorris de Donostia.

Uso (con la caché ya poblada por 'analyze'):
    URBAN_AGENT_OFFLINE=1 python scripts/validar_bidegorris.py

La capa municipal son polígonos (franjas de ~2 m); su longitud se estima como perímetro / 2.
Solo cubre el municipio de Donostia: por eso se indica qué parte de la tierra del círculo es de Donostia.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shapefile  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from urbanagent import local_data  # noqa: E402
from urbanagent.profile import build_profile  # noqa: E402
from urbanagent.session import Session  # noqa: E402

ZONES = ["Donostia", "Gros, Donostia", "Amara, Donostia", "Egia, Donostia", "Altza, Donostia"]
DONOSTIA_MUNI = "069"


def main() -> None:
    data = local_data.data_dir()
    with shapefile.Reader(str(data / "BIDEGORRIA" / "BIDEGORRIA")) as sf:
        lanes = [shape(s.__geo_interface__) for s in sf.shapes()]
    secs = local_data.sections()
    donostia = unary_union([g for c, g in zip(secs.codes, secs.geoms) if c.startswith(DONOSTIA_MUNI)])

    s = Session()
    print("| Zona | OSM: km con infraestructura ciclista | Ayuntamiento: km de bidegorri (estimado) | OSM / Ayto. | Tierra del círculo en Donostia |")
    print("|---|---:|---:|---:|---:|")
    for z in ZONES:
        p = build_profile(z, s)
        x, y = local_data.to_utm(p["center"]["lat"], p["center"]["lon"])
        circle = Point(x, y).buffer(p["radius_m"], 64)
        muni_km = sum(g.intersection(circle).length for g in lanes) / 2 / 1000
        land = secs.in_circle(x, y, p["radius_m"])["land_km2"]
        share = donostia.intersection(circle).area / 1e6 / land if land else 0
        osm_km = p["metrics"]["cycle_km"]
        ratio = f"{osm_km / muni_km:.2f}" if muni_km else "—"
        print(f"| {z} | {osm_km:.1f} | {muni_km:.1f} | {ratio} | {share:.0%} |")


if __name__ == "__main__":
    main()

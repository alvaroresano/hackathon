"""Herramientas que el agente puede llamar. Cada una devuelve datos verificables y ids de fuente."""
from __future__ import annotations

from . import scoring
from .http import DataUnavailable
from .profile import DEFINITION_NOTE, build_profile
from .session import Session

LIMITS = [
    "La zona es un círculo alrededor del punto que devuelve el geocodificador, no el límite administrativo.",
    "La pendiente se estima con una malla de 100 m sobre el MDT LiDAR 2017 de 25 m (geoEuskadi); sin él, con malla de 375 m sobre Open-Meteo (~90 m). No capta pendientes locales de una calle concreta.",
    "Los puntos de la malla con cota <= 0,5 m se tratan como agua y se excluyen de la pendiente.",
    "La población del círculo (Eustat, 01/01/2025) se reparte por secciones censales en proporción al área: supone población uniforme dentro de cada sección.",
    "Solo hay población de Gipuzkoa: la parte del círculo en Francia, Navarra o Bizkaia no cuenta (ni en población ni en superficie).",
    "OpenStreetMap tiene cobertura y etiquetado desiguales (sobre todo la infraestructura ciclista).",
    "Comercios y oficinas son proxies de demanda de reparto; no son pedidos reales.",
    "Los pesos y umbrales son supuestos heurísticos, no calibrados con datos de uso. La sensibilidad solo prueba variaciones de pesos.",
    "Drones: no se ha verificado normativa de espacio aéreo (AESA/ENAIRE), viento ni ruido.",
    "No se usan datos de movilidad real por zona (viajes, aforos, GTFS): la Encuesta de Movilidad 2021 solo da el reparto modal por territorio.",
]

USE_CASES = ["personas", "bienes"]

TOOL_SPECS = [
    {
        "name": "get_zone_profile",
        "description": (
            "Obtiene métricas reales de una zona de Gipuzkoa: pendiente (MDT LiDAR de geoEuskadi), población en el "
            "círculo (Eustat, secciones censales), infraestructura ciclista, edificios, comercios y paradas "
            "(OpenStreetMap). Devuelve también los ids de fuente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Municipio o barrio de Gipuzkoa, p. ej. 'Eibar' o 'Gros, Donostia'."},
                "radius_m": {"type": "integer", "description": "Radio de la zona en metros (por defecto 1500).", "default": 1500},
            },
            "required": ["place"],
        },
    },
    {
        "name": "rank_vehicles_for_zone",
        "description": (
            "Puntúa bicicleta, patinete eléctrico y dron en una zona para un caso de uso (personas o bienes). "
            "Devuelve ranking, margen, robustez ante cambios de pesos, confianza y alertas de calidad de datos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "use_case": {"type": "string", "enum": USE_CASES},
                "radius_m": {"type": "integer", "default": 1500},
            },
            "required": ["place", "use_case"],
        },
    },
    {
        "name": "compare_zones",
        "description": (
            "Compara varias zonas a la vez: vehículo recomendado, puntuación, confianza y alertas por zona. "
            "Si una zona falla, lo indica y continúa con las demás."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "places": {"type": "array", "items": {"type": "string"}},
                "use_case": {"type": "string", "enum": USE_CASES},
                "radius_m": {"type": "integer", "default": 1500},
            },
            "required": ["places", "use_case"],
        },
    },
    {
        "name": "explain_method",
        "description": "Devuelve los pesos, umbrales, definiciones de métricas y límites del modelo, para citarlos con exactitud.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_sources",
        "description": "Lista las fuentes consultadas en esta sesión (id, proveedor, URL, fecha y licencia).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _zone_result(place: str, use_case: str, radius_m: int, session: Session) -> dict:
    profile = build_profile(place, session, radius_m=radius_m)
    analysis = scoring.analyze(profile["metrics"], use_case, session.cfg)
    return {
        "place": place,
        "resolved_as": profile["resolved_as"],
        "radius_m": radius_m,
        "metrics": profile["metrics"],
        "elevation_source": profile.get("elevation_source"),
        **analysis,
        "source_ids": profile["source_ids"],
    }


def _tool_get_zone_profile(args: dict, session: Session) -> dict:
    return build_profile(args["place"], session, radius_m=int(args.get("radius_m", 1500)))


def _tool_rank(args: dict, session: Session) -> dict:
    if args["use_case"] not in USE_CASES:
        return {"error": f"use_case debe ser uno de {USE_CASES}", "kind": "invalid_input"}
    return _zone_result(args["place"], args["use_case"], int(args.get("radius_m", 1500)), session)


def _tool_compare(args: dict, session: Session) -> dict:
    if args["use_case"] not in USE_CASES:
        return {"error": f"use_case debe ser uno de {USE_CASES}", "kind": "invalid_input"}
    radius = int(args.get("radius_m", 1500))
    zones, errors = [], []
    for place in args["places"]:
        try:
            r = _zone_result(place, args["use_case"], radius, session)
            zones.append(
                {
                    "place": place,
                    "recommended": r["recommended"],
                    "suitable": r["suitable"],
                    "score": r["ranking"][0]["score"],
                    "runner_up": r["ranking"][1]["vehicle"] if len(r["ranking"]) > 1 else None,
                    "margin": r["margin"],
                    "robustness": r["robustness"],
                    "confidence": r["confidence"],
                    "quality_flags": r["quality_flags"],
                    "median_slope_pct": r["metrics"]["slope_median_pct"],
                    "street_slope_median_pct": r["metrics"].get("street_slope_median_pct"),
                    "slope_basis": r["slope_basis"],
                    "cycle_share": r["metrics"]["cycle_share"],
                    "buildings_per_km2": r["metrics"]["buildings_per_km2"],
                    "population": r["metrics"].get("population"),
                    "pop_per_km2": r["metrics"].get("pop_per_km2"),
                    "density_basis": r["density_basis"],
                    "land_share": r["metrics"].get("land_share"),
                    "poi_per_km2": r["metrics"]["poi_per_km2"],
                    "resolved_as": r["resolved_as"],
                    "source_ids": r["source_ids"],
                }
            )
        except (DataUnavailable, LookupError) as exc:
            errors.append({"place": place, "error": str(exc)})
    return {"use_case": args["use_case"], "radius_m": radius, "zones": zones, "errors": errors}


def _tool_explain_method(args: dict, session: Session) -> dict:
    cfg = session.cfg
    return {
        "note": "Modelo heurístico: pesos y umbrales son supuestos del equipo, editables en config/scoring.yaml.",
        "thresholds": cfg["thresholds"],
        "vehicles": {
            vid: {"label": v["label"], "slope_median_pct": v.get("slope_median_pct"), "weights_by_use_case": v["use_cases"]}
            for vid, v in cfg["vehicles"].items()
        },
        "sensitivity_delta": cfg["sensitivity"]["delta"],
        "min_suitable_score": cfg.get("min_suitable_score", 0),
        "definitions": {
            "cycle_share": "km con infraestructura ciclista en OSM / km de red (calles, ciclovías, peatonales) dentro del radio",
            "population": "habitantes estimados dentro del círculo: población de cada sección censal (Eustat, 01/01/2025) por la fracción de su área que cae dentro",
            "pop_per_km2": "population / km² de tierra del círculo cubierta por secciones censales de Gipuzkoa",
            "buildings_per_km2": "edificios etiquetados en OSM por km² de tierra del círculo (o del círculo entero si no hay secciones)",
            "poi_per_km2": "(comercios + hostelería/servicios + oficinas) por km² de tierra del círculo",
            "slope_median_pct": "pendiente del TERRENO: mediana entre puntos vecinos de la malla de elevación, sin puntos de agua (incluye laderas sin calles)",
            "slope_p90_pct": "percentil 90 de la pendiente del terreno: rugosidad del relieve (se usa para el dron)",
            "street_slope_median_pct": "pendiente de las CALLES: mediana ponderada por longitud de tramos de >= 50 m de calles y vías ciclistas de OSM, con cotas del MDT (sin puentes ni túneles). Es la que usan bici y patinete",
            "street_share_over_6pct": "fracción de la longitud de calles con tramos de más del 6 %",
            "land_share": "fracción del círculo cubierta por secciones censales de Gipuzkoa (el resto es mar o territorio vecino)",
            "suitable": "false si la mejor puntuación no llega a min_suitable_score: ningún vehículo encaja bien",
            "density": "característica de densidad: usa pop_per_km2 si existe; si no, buildings_per_km2",
        },
        "not_available": [
            "Población municipal total (la herramienta da la población dentro del círculo de la zona, no la del municipio).",
            "Viajes reales por modo en cada zona.",
            "Normativa de drones por zona (ENAIRE).",
        ],
        "zone_definition": DEFINITION_NOTE,
        "limits": LIMITS,
    }


def _tool_list_sources(args: dict, session: Session) -> dict:
    return {"sources": session.prov.all()}


_DISPATCH = {
    "get_zone_profile": _tool_get_zone_profile,
    "rank_vehicles_for_zone": _tool_rank,
    "compare_zones": _tool_compare,
    "explain_method": _tool_explain_method,
    "list_sources": _tool_list_sources,
}


def execute_tool(name: str, args: dict, session: Session) -> dict:
    """Ejecuta una herramienta. Nunca lanza: los errores vuelven como datos para que el agente los reporte."""
    fn = _DISPATCH.get(name)
    if fn is None:
        out = {"error": f"Herramienta desconocida: {name}", "kind": "unknown_tool"}
    else:
        try:
            out = fn(args or {}, session)
        except KeyError as exc:
            out = {"error": f"Falta el argumento {exc}", "kind": "invalid_input"}
        except LookupError as exc:
            out = {"error": str(exc), "kind": "not_found"}
        except DataUnavailable as exc:
            out = {"error": str(exc), "kind": "data_unavailable"}
        except ValueError as exc:
            out = {"error": str(exc), "kind": "invalid_input"}
    session.log("tool", name=name, args=args, ok="error" not in out)
    session.record_tool_output(out)
    return out

"""Herramientas que el agente puede llamar. Cada una devuelve datos verificables y ids de fuente."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from . import local_data, scoring
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
        "name": "get_municipal_population",
        "description": (
            "Población oficial de un municipio de Gipuzkoa a 01/01/2025 (Eustat, suma de sus secciones censales). "
            "Úsala cuando pregunten por los habitantes de un municipio: es distinta de la población del círculo de una zona."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"municipality": {"type": "string", "description": "Nombre del municipio, p. ej. 'Eibar'."}},
            "required": ["municipality"],
        },
    },
    {
        "name": "list_sources",
        "description": "Lista las fuentes consultadas en esta sesión (id, proveedor, URL, fecha y licencia).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


ZONES_FILE = Path(__file__).resolve().parent.parent / "config" / "zones.txt"


def known_zones() -> list[str]:
    if not ZONES_FILE.exists():
        return []
    lines = ZONES_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def canonical_place(place: str) -> str:
    """'Amara' -> 'Amara, Donostia' si es el nombre corto de una única zona conocida (config/zones.txt).

    Así el agente no geocodifica un barrio sin su municipio (caso real con qwen3:14b, 30-sep-2026).
    """
    p = place.strip()
    zones = known_zones()
    if p.lower() in (z.lower() for z in zones):
        return p
    matches = [z for z in zones if z.split(",")[0].strip().lower() == p.lower()]
    return matches[0] if len(matches) == 1 else p


def verdict_text(analysis: dict, cfg: dict) -> str:
    """Veredicto listo para citar: el vehículo recomendado o que ninguno encaja."""
    best = analysis["ranking"][0]
    label = cfg["vehicles"][best["vehicle"]]["label"]
    if analysis["suitable"]:
        return f"Recomendado: {label}"
    return (
        f"Ningún vehículo adecuado: el mejor puntuado ({label}) obtiene {best['score']} "
        f"y el mínimo es {analysis['min_suitable_score']}"
    )


def _zone_result(place: str, use_case: str, radius_m: int, session: Session) -> dict:
    place = canonical_place(place)
    profile = build_profile(place, session, radius_m=radius_m)
    analysis = scoring.analyze(profile["metrics"], use_case, session.cfg)
    best = analysis["recommended"]
    out = {
        "place": place,
        "resolved_as": profile["resolved_as"],
        "radius_m": radius_m,
        "verdict": verdict_text(analysis, session.cfg),
        "metrics": profile["metrics"],
        "elevation_source": profile.get("elevation_source"),
        **analysis,
        # Si ningún vehículo es adecuado, no hay recomendación: el primero va en best_scored.
        "recommended": best if analysis["suitable"] else None,
        "best_scored": best,
        "sources": profile.get("sources", {}),
        "source_ids": profile["source_ids"],
    }
    session.record_zone(place, out)
    return out


def _tool_get_zone_profile(args: dict, session: Session) -> dict:
    place = canonical_place(args["place"])
    p = build_profile(place, session, radius_m=int(args.get("radius_m", 1500)))
    session.record_zone(place, p)
    return p


def _tool_rank(args: dict, session: Session) -> dict:
    if args["use_case"] not in USE_CASES:
        return {"error": f"use_case debe ser uno de {USE_CASES}", "kind": "invalid_input"}
    return _zone_result(args["place"], args["use_case"], int(args.get("radius_m", 1500)), session)


def compact_zone(r: dict) -> dict:
    """Resumen de una zona para compare_zones y los informes. Los nombres dicen qué se mide."""
    m = r["metrics"]
    return {
        "place": r["place"],
        "resolved_as": r["resolved_as"],
        "verdict": r["verdict"],
        "recommended": r["recommended"],
        "best_scored": r["best_scored"],
        "suitable": r["suitable"],
        "score": r["ranking"][0]["score"],
        # Puntos que aporta cada característica al mejor puntuado: es la explicación del resultado.
        "score_breakdown": r["ranking"][0]["contributions"],
        "runner_up": r["ranking"][1]["vehicle"] if len(r["ranking"]) > 1 else None,
        "runner_up_score": r["ranking"][1]["score"] if len(r["ranking"]) > 1 else None,
        "margin": r["margin"],
        "robustness": r["robustness"],
        "confidence": r["confidence"],
        "confidence_reason": r["confidence_reason"],
        "quality_flags": r["quality_flags"],
        "street_slope_median_pct": m.get("street_slope_median_pct"),
        "terrain_slope_median_pct": m["slope_median_pct"],
        "terrain_slope_p90_pct": m["slope_p90_pct"],
        "slope_basis": r["slope_basis"],
        "cycle_share": m["cycle_share"],
        "population_in_circle": m.get("population"),
        "pop_per_km2": m.get("pop_per_km2"),
        "land_share": m.get("land_share"),
        "density_basis": r["density_basis"],
        "buildings_per_km2": m["buildings_per_km2"],
        "poi_per_km2": m["poi_per_km2"],
        "sources": r["sources"],
    }


def _tool_compare(args: dict, session: Session) -> dict:
    if args["use_case"] not in USE_CASES:
        return {"error": f"use_case debe ser uno de {USE_CASES}", "kind": "invalid_input"}
    radius = int(args.get("radius_m", 1500))
    zones, errors = [], []
    for place in args["places"]:
        try:
            zones.append(compact_zone(_zone_result(place, args["use_case"], radius, session)))
        except (DataUnavailable, LookupError) as exc:
            errors.append({"place": canonical_place(place), "error": str(exc)})
    return {"use_case": args["use_case"], "radius_m": radius, "zones": zones, "errors": errors}


def _norm(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def _tool_municipal_population(args: dict, session: Session) -> dict:
    status = local_data.population_status()
    if status:
        return {"error": status, "kind": "data_unavailable"}
    table = local_data.municipal_population()
    wanted = _norm(args["municipality"])
    # 'Donostia' casa con 'Donostia / San Sebastián'; 'Mondragón' con 'Arrasate/Mondragón'
    found = [n for n in table if wanted in [_norm(x) for x in re.split(r"\s*/\s*", n)] or _norm(n) == wanted]
    if not found:
        return {"error": f"'{args['municipality']}' no es un municipio de Gipuzkoa en la tabla de Eustat.", "kind": "not_found"}
    name = found[0]
    m = local_data.source_meta("poblacion")
    sid = session.prov.add("población", m["provider"], m, f"Población municipal de {name}.", m["license"])
    item = table[name]
    return {
        "municipality": name,
        "population": item["population"],
        "reference_date": "2025-01-01",
        "census_sections": item["sections"],
        "note": "Población de todo el municipio. No es la población del círculo de 1.500 m que usan las zonas.",
        "source_id": sid,
    }


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
            "verdict": "frase lista para citar con la recomendación, o con el aviso de que ningún vehículo es adecuado",
            "recommended": "vehículo recomendado; null si ningún vehículo es adecuado (el mejor puntuado va en best_scored)",
            "population_in_circle": "igual que population: habitantes dentro del círculo, no del municipio",
            "sources": "id de fuente (S#) que respalda cada tipo de dato de la zona",
            "score_breakdown": "puntos que aporta cada característica a la puntuación del mejor vehículo (suman la puntuación)",
            "features": {
                "flatness": "planitud: 1 si la pendiente de calles está por debajo del umbral inferior del vehículo",
                "infra": "infraestructura ciclista (cycle_share)",
                "density": "densidad de población (pop_per_km2) o, sin Eustat, de edificios",
                "goods_demand": "demanda de reparto: comercios, hostelería y oficinas por km² (poi_per_km2)",
                "openness": "espacio libre para el dron: inverso de la densidad",
                "steepness": "relieve abrupto (p90 de la pendiente del terreno): ventaja del dron",
                "low_infra": "poca infraestructura ciclista: ventaja relativa del dron",
            },
            "density": "característica de densidad: usa pop_per_km2 si existe; si no, buildings_per_km2",
        },
        "not_available": [
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
    "get_municipal_population": _tool_municipal_population,
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

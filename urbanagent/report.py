"""Informes en Markdown y HTML a partir de los resultados de compare_zones / rank_vehicles_for_zone."""
from __future__ import annotations

import html
from datetime import datetime

from .tools import LIMITS

VERIFY_CHECKLIST = [
    "Abrir en OpenStreetMap 2-3 zonas y comprobar que el carril bici etiquetado coincide con la realidad.",
    "Comprobar que el punto geocodificado de cada zona está donde se espera (columna 'Resuelto como').",
    "En zonas costeras o de frontera, tener en cuenta qué parte del círculo es tierra de Gipuzkoa (columna 'Tierra').",
    "Revisar las zonas con confianza 'baja' o con alertas de calidad de datos antes de sacar conclusiones.",
    "Si se considera el dron: consultar la normativa de espacio aéreo (AESA/ENAIRE) de la zona.",
    "Decidir si los pesos de config/scoring.yaml reflejan las prioridades reales antes de usar el resultado.",
]


def _vehicle_label(cfg: dict, vid: str) -> str:
    return cfg["vehicles"][vid]["label"]


def _verdict(cfg: dict, z: dict) -> str:
    """Recomendación, o aviso de que ningún vehículo alcanza la puntuación mínima."""
    if z.get("suitable", True):
        return _vehicle_label(cfg, z["recommended"])
    return f"Ninguno adecuado (mejor: {_vehicle_label(cfg, z['recommended'])})"


def _fmt(v) -> str:
    return "—" if v is None else f"{v}"


def render_markdown(results: dict, session, question: str = "") -> str:
    cfg = session.cfg
    zones, errors = results["zones"], results["errors"]
    lines = [
        "# ¿Qué vehículo encaja mejor en cada zona de Gipuzkoa?",
        "",
        f"- Caso de uso: **{results['use_case']}** · Radio de zona: **{results['radius_m']} m**",
        f"- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if question:
        lines.append(f"- Pregunta: {question}")
    lines += [
        "",
        "> El agente aporta evidencias; las personas interpretan y deciden. La puntuación es un modelo heurístico, no demanda real.",
        "",
        "## Resumen por zona",
        "",
        "| Zona | Recomendado | Puntuación | Margen | Robustez | Confianza | Alertas |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for z in sorted(zones, key=lambda x: -x["score"]):
        margin = "—" if z["margin"] is None else f"{z['margin']}"
        lines.append(
            f"| {z['place']} | {_verdict(cfg, z)} | {z['score']} | {margin} | "
            f"{z['robustness']} | {z['confidence']} | {len(z['quality_flags'])} |"
        )
    if errors:
        lines += ["", "### Zonas que no se pudieron analizar", ""]
        lines += [f"- **{e['place']}**: {e['error']}" for e in errors]

    min_score = cfg.get("min_suitable_score", 0)
    lines += [
        "",
        f"\"Ninguno adecuado\": la mejor puntuación no llega a {min_score} sobre 100.",
        "",
        "## Métricas medidas",
        "",
        "| Zona | Resuelto como | Pendiente calles % (mediana) | Pendiente terreno % (mediana) | Cuota infra. ciclista | Habitantes en el círculo | Hab./km² | Tierra | Edificios/km² | Comercios y servicios/km² |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for z in zones:
        lines.append(
            f"| {z['place']} | {z.get('resolved_as', '')} | {_fmt(z.get('street_slope_median_pct'))} | {z['median_slope_pct']} | {z['cycle_share']} | "
            f"{_fmt(z.get('population'))} | {_fmt(z.get('pop_per_km2'))} | {_fmt(z.get('land_share'))} | "
            f"{z['buildings_per_km2']} | {z['poi_per_km2']} |"
        )

    flagged = [z for z in zones if z["quality_flags"]]
    if flagged:
        lines += ["", "## Alertas de calidad de datos", ""]
        for z in flagged:
            lines.append(f"- **{z['place']}**: " + " ".join(z["quality_flags"]))

    lines += [
        "",
        "Bici y patinete usan la pendiente de las calles (MDT de 25 m muestreado sobre las calles de OSM). "
        "La del terreno incluye laderas sin calles y solo interviene en el dron (percentil 90). "
        "\"Tierra\" es la fracción del círculo con secciones censales de Gipuzkoa; las densidades se calculan sobre ella.",
    ]
    lines += ["", "## Método y supuestos", "", "Pesos por caso de uso (editables en `config/scoring.yaml`):", ""]
    for vid, v in cfg["vehicles"].items():
        w = v["use_cases"].get(results["use_case"])
        if w:
            lines.append(f"- **{v['label']}**: " + ", ".join(f"{k} {val}" for k, val in w.items()))
    lines.append(
        f"- Robustez = proporción de {2 * sum(len(v['use_cases'].get(results['use_case'], {})) for v in cfg['vehicles'].values())} "
        f"variaciones de ±{int(cfg['sensitivity']['delta'] * 100)} % en un peso que mantienen el mismo vehículo recomendado."
    )

    lines += ["", "## Fuentes consultadas", ""]
    for s in session.prov.all():
        cache = " (desde caché)" if s.get("from_cache") else ""
        lines.append(f"- **{s['id']}** {s['provider']} · {s['kind']} · {s.get('retrieved_at') or 'sin fecha'}{cache}. {s['license']}")

    lines += ["", "## Límites", ""] + [f"- {x}" for x in LIMITS]
    lines += ["", "## Qué debería verificar una persona", ""] + [f"- [ ] {x}" for x in VERIFY_CHECKLIST]
    return "\n".join(lines) + "\n"


def render_html(results: dict, session, question: str = "") -> str:
    cfg = session.cfg
    esc = html.escape
    zones = sorted(results["zones"], key=lambda x: -x["score"])
    rows = []
    for z in zones:
        width = max(2, min(100, z["score"]))
        rows.append(
            "<tr>"
            f"<td>{esc(z['place'])}</td><td>{esc(_verdict(cfg, z))}</td>"
            f"<td><div class='bar'><span style='width:{width}%'></span></div>{z['score']}</td>"
            f"<td>{'—' if z['margin'] is None else z['margin']}</td><td>{z['robustness']}</td>"
            f"<td class='c-{esc(z['confidence'])}'>{esc(z['confidence'])}</td>"
            f"<td>{esc(' '.join(z['quality_flags'])) or '—'}</td></tr>"
        )
    errs = "".join(f"<li><b>{esc(e['place'])}</b>: {esc(e['error'])}</li>" for e in results["errors"])
    srcs = "".join(
        f"<li><b>{esc(s['id'])}</b> {esc(s['provider'])} · {esc(s['kind'])} · {esc(str(s.get('retrieved_at') or ''))}</li>"
        for s in session.prov.all()
    )
    limits = "".join(f"<li>{esc(x)}</li>" for x in LIMITS)
    checks = "".join(f"<li>☐ {esc(x)}</li>" for x in VERIFY_CHECKLIST)
    q = f"<p><b>Pregunta:</b> {esc(question)}</p>" if question else ""
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vehículo por zona en Gipuzkoa</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1a2233;line-height:1.5}}
table{{border-collapse:collapse;width:100%;font-size:.92rem}}th,td{{border-bottom:1px solid #d8dde6;padding:.45rem .5rem;text-align:left;vertical-align:top}}
th{{background:#f2f5f9}}.bar{{background:#e6ebf2;height:8px;border-radius:4px;margin-bottom:3px}}.bar span{{display:block;height:8px;background:#1f6f8b;border-radius:4px}}
.c-alta{{color:#1b7f3b;font-weight:600}}.c-media{{color:#a06a00;font-weight:600}}.c-baja{{color:#b3261e;font-weight:600}}
blockquote{{border-left:4px solid #1f6f8b;margin:1rem 0;padding:.2rem 1rem;background:#f2f5f9}}
</style></head><body>
<h1>¿Qué vehículo encaja mejor en cada zona de Gipuzkoa?</h1>
<p>Caso de uso: <b>{esc(results['use_case'])}</b> · Radio: <b>{results['radius_m']} m</b> · Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>{q}
<blockquote>El agente aporta evidencias; las personas interpretan y deciden. La puntuación es un modelo heurístico, no demanda real.</blockquote>
<table><thead><tr><th>Zona</th><th>Recomendado</th><th>Puntuación</th><th>Margen</th><th>Robustez</th><th>Confianza</th><th>Alertas</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
{f'<h2>Zonas no analizadas</h2><ul>{errs}</ul>' if errs else ''}
<h2>Fuentes consultadas</h2><ul>{srcs}</ul>
<h2>Límites</h2><ul>{limits}</ul>
<h2>Qué debería verificar una persona</h2><ul style="list-style:none;padding-left:0">{checks}</ul>
</body></html>
"""

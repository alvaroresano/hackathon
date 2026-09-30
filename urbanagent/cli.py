"""Línea de comandos: doctor, analyze, ask, method."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

from . import local_data, sources
from .agent import OllamaBackend, ollama_model, ollama_url, run_agent
from .http import DataUnavailable
from .report import render_html, render_markdown
from .session import Session
from .tools import execute_tool

ROOT = Path(__file__).resolve().parent.parent


def _load_zones(args) -> list[str]:
    if args.zones:
        return args.zones
    path = Path(args.zones_file) if args.zones_file else ROOT / "config" / "zones.txt"
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def _new_session(out_dir: Path) -> Session:
    run_dir = out_dir / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    return Session(run_dir=run_dir)


def _ollama_status() -> str:
    """Estado de Ollama y del modelo configurado (no afecta al resultado de doctor: 'analyze' no lo necesita)."""
    model = ollama_model()
    try:
        tags = requests.get(f"{ollama_url()}/api/tags", timeout=5).json()
    except (requests.RequestException, ValueError):
        return f"AVISO Ollama: no responde en {ollama_url()} (arránquelo con 'ollama serve'; 'analyze' funciona sin él)"
    names = {m.get("name") for m in tags.get("models", [])}
    if model in names or f"{model}:latest" in names:
        return f"OK    Ollama: modelo {model} disponible"
    return f"AVISO Ollama: responde, pero falta el modelo {model} (ejecute 'ollama pull {model}')"


def cmd_doctor(args) -> int:
    print("Comprobando las fuentes de datos (necesita internet)...\n")
    ok_all = True

    def check(name, fn):
        nonlocal ok_all
        try:
            detail = fn()
            print(f"  OK    {name}: {detail}")
        except Exception as exc:  # noqa: BLE001 - queremos mostrar cualquier fallo
            ok_all = False
            print(f"  FALLO {name}: {exc}")

    check("Nominatim (geocodificación)", lambda: "Donostia -> %.4f, %.4f" % tuple(sources.geocode("Donostia")[0][k] for k in ("lat", "lon")))
    check("Open-Meteo (elevación)", lambda: "elevación de Donostia = %s m" % sources.elevations([(43.3183, -1.9812)])[0][0])
    check(
        "Overpass (OpenStreetMap)",
        lambda: "%s elementos de prueba" % len(sources.overpass('[out:json][timeout:25];node["amenity"="drinking_water"](around:500,43.3183,-1.9812);out count;')[0]["elements"]),
    )
    print()
    for name, status in (("MDT LiDAR 25 m (pendiente)", local_data.dem_status()), ("Secciones y población Eustat", local_data.sections_status())):
        print(f"  {'OK   ' if status is None else 'AVISO'} {name}: {'disponible en data/' if status is None else status + ' (se usará la alternativa)'}")
    print("  " + _ollama_status())
    print("\nTodo listo." if ok_all else "\nHay fallos: revise la conexión. Si trabaja sin internet, use URBAN_AGENT_OFFLINE=1 con la caché ya poblada.")
    return 0 if ok_all else 1


def cmd_analyze(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = _new_session(out)
    zones = _load_zones(args)
    print(f"Analizando {len(zones)} zonas ({args.use_case}, radio {args.radius} m). Puede tardar unos minutos la primera vez...")
    results = execute_tool("compare_zones", {"places": zones, "use_case": args.use_case, "radius_m": args.radius}, session)
    if "error" in results:
        print("Error:", results["error"])
        return 1
    md = render_markdown(results, session)
    (out / "informe.md").write_text(md, encoding="utf-8")
    (out / "informe.html").write_text(render_html(results, session), encoding="utf-8")
    (out / "resultados.json").write_text(json.dumps({"results": results, "sources": session.prov.all()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zonas analizadas: {len(results['zones'])} · con error: {len(results['errors'])}")
    for e in results["errors"]:
        print(f"  - {e['place']}: {e['error']}")
    if not results["zones"]:
        print("No se pudo analizar ninguna zona. Ejecute 'python -m urbanagent doctor'.")
        return 1
    print(f"Informe: {out / 'informe.md'} y {out / 'informe.html'}")
    return 0


def cmd_ask(args) -> int:
    out = Path(args.out)
    try:
        backend = OllamaBackend(model=args.model)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    session = _new_session(out)
    try:
        result = run_agent(args.question, backend, session)
    except (RuntimeError, DataUnavailable) as exc:
        print(f"Error: {exc}")
        return 1
    print(result["answer"])
    v = result["verification"]
    print("\n---")
    print(f"Pasos: {result['steps']} · Fuentes: {len(result['sources'])} · Cifras comprobadas: {v['checked']}")
    if v["unverified"]:
        print("AVISO: cifras sin respaldo en las herramientas:", ", ".join(v["unverified"]))
    for mis in v.get("misattributed", []):
        print(f"AVISO: la cifra {mis['value']} se atribuye a {mis['line_zone']} pero es de {', '.join(mis['belongs_to'])}")
    print("Estado: PENDIENTE DE REVISIÓN HUMANA (ver checklist en el informe).")
    (out / "respuesta.md").write_text(result["answer"] + "\n", encoding="utf-8")
    print(f"Traza completa: {session.run_dir / 'traza.jsonl'}")
    return 0


def cmd_method(args) -> int:
    session = Session()
    print(json.dumps(execute_tool("explain_method", {}, session), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="urbanagent", description="Agente: vehículo de micromovilidad por zona en Gipuzkoa.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Comprueba que las fuentes de datos responden.").set_defaults(fn=cmd_doctor)
    sub.add_parser("method", help="Muestra pesos, umbrales y límites del modelo.").set_defaults(fn=cmd_method)

    a = sub.add_parser("analyze", help="Análisis determinista de varias zonas (sin modelo de lenguaje).")
    a.add_argument("--zones", nargs="+", help="Zonas a analizar (por defecto config/zones.txt).")
    a.add_argument("--zones-file")
    a.add_argument("--use-case", choices=["personas", "bienes"], default="personas")
    a.add_argument("--radius", type=int, default=1500)
    a.add_argument("--out", default="outputs")
    a.set_defaults(fn=cmd_analyze)

    q = sub.add_parser("ask", help="Pregunta en lenguaje natural al agente (necesita Ollama con un modelo).")
    q.add_argument("question")
    q.add_argument("--model", help="Modelo de Ollama (por defecto URBAN_AGENT_MODEL o qwen3:14b).")
    q.add_argument("--out", default="outputs")
    q.set_defaults(fn=cmd_ask)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

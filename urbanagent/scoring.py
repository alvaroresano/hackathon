"""Modelo de puntuación (heurístico y transparente) y análisis de sensibilidad."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"


def load_config(path: str | Path | None = None) -> dict:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def lin(x: float, lo: float, hi: float) -> float:
    """Interpolación lineal recortada a [0, 1]: 0 en lo, 1 en hi."""
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def compute_features(m: dict, vcfg: dict, th: dict) -> dict[str, float]:
    lo, hi = vcfg.get("slope_median_pct", [3, 9])
    feats = {
        "flatness": 1 - lin(m["slope_median_pct"], lo, hi),
        "infra": lin(m["cycle_share"], *th["cycle_share"]),
        "density": lin(m["buildings_per_km2"], *th["buildings_per_km2"]),
        "goods_demand": lin(m["poi_per_km2"], *th["poi_per_km2"]),
        "openness": 1 - lin(m["buildings_per_km2"], *th["openness_buildings_per_km2"]),
        "steepness": lin(m["slope_p90_pct"], *th["steepness_p90_pct"]),
    }
    feats["low_infra"] = 1 - feats["infra"]
    return feats


def score_vehicle(features: dict[str, float], weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    total = sum(weights.values())
    contrib = {k: 100 * w / total * features[k] for k, w in weights.items()}
    return sum(contrib.values()), contrib


def _weights(cfg: dict, use_case: str) -> dict[str, dict[str, float]]:
    return {
        vid: dict(v["use_cases"][use_case])
        for vid, v in cfg["vehicles"].items()
        if use_case in v.get("use_cases", {})
    }


def _scores(metrics: dict, cfg: dict, weights_by_vehicle: dict) -> dict[str, tuple]:
    out = {}
    for vid, w in weights_by_vehicle.items():
        feats = compute_features(metrics, cfg["vehicles"][vid], cfg["thresholds"])
        s, contrib = score_vehicle(feats, w)
        out[vid] = (s, contrib, feats)
    return out


def quality_flags(m: dict) -> list[str]:
    flags = []
    if m.get("buildings", 0) < 100:
        flags.append("Menos de 100 edificios etiquetados en OSM: cobertura baja o zona poco urbana.")
    if m.get("network_km", 0) < 5:
        flags.append("Menos de 5 km de red viaria etiquetada en la zona.")
    if m.get("cycle_km", 0) == 0:
        flags.append("No hay infraestructura ciclista etiquetada en OSM: puede ser real o falta de etiquetado.")
    if m.get("slope_pairs", 0) < 20:
        flags.append("Pocos pares de puntos para estimar la pendiente (<20).")
    return flags


def confidence_label(robustness: float, margin: float | None, cfg: dict, flags: list[str]) -> str:
    c = cfg["confidence"]
    if margin is None:
        level = 1  # un solo vehículo: no hay comparación
    elif robustness >= c["high"]["min_robustness"] and margin >= c["high"]["min_margin"]:
        level = 2
    elif robustness >= c["medium"]["min_robustness"] and margin >= c["medium"]["min_margin"]:
        level = 1
    else:
        level = 0
    if flags:
        level = max(0, level - 1)
    return ["baja", "media", "alta"][level]


def analyze(metrics: dict, use_case: str, cfg: dict) -> dict:
    weights = _weights(cfg, use_case)
    if not weights:
        raise ValueError(f"Ningún vehículo admite el caso de uso '{use_case}'.")
    base = _scores(metrics, cfg, weights)
    ranking = sorted(base.items(), key=lambda kv: kv[1][0], reverse=True)
    top_id = ranking[0][0]
    margin = ranking[0][1][0] - ranking[1][1][0] if len(ranking) > 1 else None

    delta = cfg["sensitivity"]["delta"]
    same = total = 0
    for vid, w in weights.items():
        for feat in w:
            for sign in (+1, -1):
                w2 = copy.deepcopy(weights)
                w2[vid][feat] = w[feat] * (1 + sign * delta)
                s2 = _scores(metrics, cfg, w2)
                total += 1
                if max(s2, key=lambda k: s2[k][0]) == top_id:
                    same += 1
    robustness = same / total if total else 1.0

    flags = quality_flags(metrics)
    rows = []
    for vid, (s, contrib, feats) in ranking:
        rows.append(
            {
                "vehicle": vid,
                "label": cfg["vehicles"][vid]["label"],
                "score": round(s, 1),
                "contributions": {k: round(v, 1) for k, v in contrib.items()},
                "features": {k: round(v, 2) for k, v in feats.items() if k in weights[vid]},
                "caveats": cfg["vehicles"][vid].get("caveats", []),
            }
        )
    return {
        "use_case": use_case,
        "ranking": rows,
        "recommended": top_id,
        "margin": None if margin is None else round(margin, 1),
        "robustness": round(robustness, 2),
        "sensitivity_delta": delta,
        "sensitivity_runs": total,
        "confidence": confidence_label(robustness, margin, cfg, flags),
        "quality_flags": flags,
    }

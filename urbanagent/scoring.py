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


def density_basis(m: dict) -> str:
    """Qué métrica mide la densidad: población oficial si existe; si no, edificios de OSM."""
    return "pop_per_km2" if m.get("pop_per_km2") is not None else "buildings_per_km2"


def slope_basis(m: dict) -> str:
    """Pendiente para bici y patinete: la de las calles (MDT) si existe; si no, la del terreno."""
    return "street_slope_median_pct" if m.get("street_slope_median_pct") is not None else "slope_median_pct"


def compute_features(m: dict, vcfg: dict, th: dict) -> dict[str, float]:
    lo, hi = vcfg.get("slope_median_pct", [3, 9])
    basis = density_basis(m)
    feats = {
        "flatness": 1 - lin(m[slope_basis(m)], lo, hi),
        "infra": lin(m["cycle_share"], *th["cycle_share"]),
        "density": lin(m[basis], *th[basis]),
        "goods_demand": lin(m["poi_per_km2"], *th["poi_per_km2"]),
        "openness": 1 - lin(m[basis], *th[f"openness_{basis}"]),
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
    if m.get("land_share") is not None and m["land_share"] < 0.5:
        flags.append(
            "Menos de la mitad del círculo es tierra de Gipuzkoa (mar o territorio vecino): "
            "las densidades se calculan solo sobre la parte en tierra."
        )
    inside = m.get("grid_points_inside") or 0
    if inside and m.get("grid_points_no_data", 0) / inside > 0.2:
        flags.append("Más del 20 % de la malla de elevación no tiene dato (fuera de la cobertura del MDT).")
    if m.get("pop_per_km2") is None:
        flags.append("Sin población oficial: la densidad se aproxima con edificios de OpenStreetMap.")
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


def confidence_reason(robustness: float, margin: float | None, flags: list[str]) -> str:
    """Motivo de la etiqueta de confianza, calculado (el modelo de lenguaje no debe deducirlo)."""
    parts = []
    if margin is not None:
        parts.append(f"margen de {round(margin, 1)} puntos sobre el segundo vehículo")
    parts.append(f"la recomendación se mantiene en el {round(robustness * 100)} % de las variaciones de pesos")
    if flags:
        parts.append(f"{len(flags)} alerta(s) de calidad de datos (bajan un nivel)")
    else:
        parts.append("sin alertas de calidad de datos")
    return "; ".join(parts)


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
    min_score = cfg.get("min_suitable_score", 0)
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
        "suitable": ranking[0][1][0] >= min_score,
        "min_suitable_score": min_score,
        "density_basis": density_basis(metrics),
        "slope_basis": slope_basis(metrics),
        "margin": None if margin is None else round(margin, 1),
        "robustness": round(robustness, 2),
        "sensitivity_delta": delta,
        "sensitivity_runs": total,
        "confidence": confidence_label(robustness, margin, cfg, flags),
        "confidence_reason": confidence_reason(robustness, margin, flags),
        "quality_flags": flags,
    }

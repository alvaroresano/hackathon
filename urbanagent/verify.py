"""Comprobación heurística de trazabilidad: ¿las cifras de la respuesta salen de las herramientas?"""
from __future__ import annotations

import re

_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])")
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")


def _readings(token: str) -> list[tuple[float, int]]:
    """Posibles lecturas numéricas de un token: lista de (valor, decimales)."""
    out: list[tuple[float, int]] = []
    if _THOUSANDS.fullmatch(token):
        out.append((float(token.replace(".", "").replace(",", ".")), len(token.split(",")[1]) if "," in token else 0))
        if "," not in token and token.count(".") == 1:  # también podría ser un decimal con punto
            out.append((float(token), len(token.split(".")[1])))
    else:
        t = token.replace(",", ".")
        out.append((float(t), len(t.split(".")[1]) if "." in t else 0))
        if re.fullmatch(r"\d{1,3},\d{3}", token):  # separador de miles en formato inglés: 56,164
            out.append((float(token.replace(",", "")), 0))
    return out


def numbers_in_text(text: str) -> list[float]:
    """Todas las lecturas numéricas de las cifras de un texto."""
    return [v for tok in _NUM.findall(text) for v, _ in _readings(tok)]


def _matches(value: float, decimals: int, tool_numbers: list[float]) -> bool:
    tol_abs = 0.5 * 10 ** (-decimals)
    for t in tool_numbers:
        for cand in (t, t * 100):  # las proporciones (0,12) suelen escribirse como 12 %
            if abs(cand - value) <= max(tol_abs, 0.01 * abs(cand)):
                return True
    return False


# Frases que comparan zonas: pueden nombrar solo una y citar cifras de otra ("Gros: 84,3 vs. 78,6").
_COMPARISON = re.compile(r"\bvs\.?(?!\w)|\bfrente a\b|\brespecto a\b|\bmientras que\b|\bcompar", re.IGNORECASE)


def _zone_key(place: str) -> str:
    """Nombre corto con el que una zona aparece en el texto: 'Gros, Donostia' -> 'Gros'."""
    return re.split(r"[,/(]", place)[0].strip()


def _zones_in(line: str, zones: list[str]) -> list[str]:
    return [z for z in zones if re.search(rf"(?<!\w){re.escape(_zone_key(z))}(?!\w)", line, re.IGNORECASE)]


def _checkable(token: str, question_tokens: set[str]):
    if token in question_tokens:
        return None
    readings = _readings(token)
    value, decimals = readings[0]
    if decimals == 0 and (value < 100 or 1900 <= value <= 2100):
        return None  # enteros pequeños (listas, años) no se comprueban
    return readings


def verify_answer(
    answer: str, tool_numbers: list[float], question: str = "", zone_numbers: dict[str, list[float]] | None = None
) -> dict:
    """Marca cifras sin respaldo en las herramientas y cifras atribuidas a otra zona.

    Atribución: si una línea (fila de tabla, viñeta o frase) nombra una sola zona y contiene una cifra que
    coincide con datos de otra zona pero no con los de la nombrada, se marca como mal atribuida.
    """
    question_tokens = set(_NUM.findall(question))
    unverified: list[str] = []
    misattributed: list[dict] = []
    checked = 0
    zone_numbers = zone_numbers or {}
    zones = list(zone_numbers)
    for line in answer.splitlines():
        named = _zones_in(line, zones) if zones else []
        # "Gros, Donostia" nombra también "Donostia": nos quedamos con la zona más específica
        named = [z for z in named if not any(z != o and _zone_key(z) in o for o in named)]
        for m in _NUM.finditer(line):
            token = m.group(1)
            readings = _checkable(token, question_tokens)
            if readings is None:
                continue
            checked += 1
            if not any(_matches(v, d, tool_numbers) for v, d in readings):
                unverified.append(token)
                continue
            if len(named) != 1 or _COMPARISON.search(line):
                continue
            zone = named[0]
            if any(_matches(v, d, zone_numbers[zone]) for v, d in readings):
                continue
            owners = [z for z in zones if z != zone and any(_matches(v, d, zone_numbers[z]) for v, d in readings)]
            if owners:
                misattributed.append({"value": token, "line_zone": zone, "belongs_to": owners})
    return {
        "checked": checked,
        "unverified": sorted(set(unverified)),
        "misattributed": misattributed,
        "ok": not unverified and not misattributed,
        "note": (
            "Comprobación heurística: detecta cifras sin respaldo en las herramientas y cifras de una zona "
            "atribuidas a otra en la misma línea. No valida el razonamiento."
        ),
    }

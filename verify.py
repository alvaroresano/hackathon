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
    return out


def _matches(value: float, decimals: int, tool_numbers: list[float]) -> bool:
    tol_abs = 0.5 * 10 ** (-decimals)
    for t in tool_numbers:
        for cand in (t, t * 100):  # las proporciones (0,12) suelen escribirse como 12 %
            if abs(cand - value) <= max(tol_abs, 0.01 * abs(cand)):
                return True
    return False


def verify_answer(answer: str, tool_numbers: list[float], question: str = "") -> dict:
    """Marca cifras de la respuesta que no aparecen en ningún resultado de herramienta."""
    question_tokens = set(_NUM.findall(question))
    unverified: list[str] = []
    checked = 0
    for m in _NUM.finditer(answer):
        token = m.group(1)
        if token in question_tokens:
            continue
        readings = _readings(token)
        value, decimals = readings[0]
        if decimals == 0 and (value < 100 or 1900 <= value <= 2100):
            continue  # enteros pequeños (listas, años) no se comprueban
        checked += 1
        if not any(_matches(v, d, tool_numbers) for v, d in readings):
            unverified.append(token)
    return {
        "checked": checked,
        "unverified": sorted(set(unverified)),
        "ok": not unverified,
        "note": "Comprobación heurística: detecta cifras sin respaldo en las herramientas, no valida el razonamiento.",
    }

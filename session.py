"""Sesión de trabajo: procedencia de datos, caché de perfiles y traza de ejecución."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .scoring import load_config


class Provenance:
    """Registro de fuentes consultadas. Cada consulta recibe un id (S1, S2, ...)."""

    def __init__(self) -> None:
        self._items: list[dict] = []
        self._index: dict[tuple, str] = {}

    def add(self, kind: str, provider: str, meta: dict, note: str = "", license_note: str = "") -> str:
        sig = (meta.get("url"), meta.get("query"))
        if sig in self._index:
            return self._index[sig]
        sid = f"S{len(self._items) + 1}"
        self._items.append(
            {
                "id": sid,
                "kind": kind,
                "provider": provider,
                "url": meta.get("url"),
                "query": meta.get("query"),
                "retrieved_at": meta.get("retrieved_at"),
                "from_cache": meta.get("from_cache"),
                "note": note,
                "license": license_note,
            }
        )
        self._index[sig] = sid
        return sid

    def all(self) -> list[dict]:
        return list(self._items)


def _collect_numbers(obj, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, acc)


class Session:
    def __init__(self, run_dir: str | Path | None = None, cfg: dict | None = None) -> None:
        self.cfg = cfg or load_config()
        self.prov = Provenance()
        self.profiles: dict[tuple, dict] = {}
        self.tool_numbers: list[float] = []
        self.events: list[dict] = []
        self.run_dir = Path(run_dir) if run_dir else None
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data) -> None:
        rec = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **data}
        self.events.append(rec)
        if self.run_dir:
            with open(self.run_dir / "traza.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def record_tool_output(self, output: dict) -> None:
        _collect_numbers(output, self.tool_numbers)

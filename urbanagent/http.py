"""Cliente HTTP con caché en disco, límite de frecuencia y metadatos de procedencia.

Cada respuesta se guarda en .cache/ (o en URBAN_AGENT_CACHE). Así una ejecución es
reproducible y, una vez poblada la caché, funciona sin conexión.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

DEFAULT_UA = "gipuzkoa-vehicle-agent/0.1 (proyecto universitario; defina URBAN_AGENT_UA con su contacto)"

MIN_INTERVAL = {
    "nominatim.openstreetmap.org": 1.1,  # política de uso: máx. 1 petición/segundo
    "overpass-api.de": 1.0,
    "overpass.kumi.systems": 1.0,
    "api.open-meteo.com": 0.3,
}

RETRY_STATUS = {429, 502, 503, 504}


class DataUnavailable(RuntimeError):
    """No se pudo obtener un dato (sin conexión, límite de uso, servicio caído)."""


_lock = threading.Lock()
_last_call: dict[str, float] = {}


def cache_dir() -> Path:
    return Path(os.environ.get("URBAN_AGENT_CACHE", ".cache"))


def offline() -> bool:
    return os.environ.get("URBAN_AGENT_OFFLINE", "").strip().lower() in {"1", "true", "yes", "si", "sí"}


def _key(method: str, url: str, params: dict | None, data: dict | None) -> str:
    raw = json.dumps({"m": method, "u": url, "p": params, "d": data}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _throttle(host: str) -> None:
    gap = MIN_INTERVAL.get(host, 0.0)
    if gap <= 0:
        return
    with _lock:
        wait = _last_call.get(host, 0.0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    timeout: int = 120,
    retries: int = 3,
    use_cache: bool = True,
) -> tuple[object, dict]:
    """Devuelve (json, meta). meta incluye url, consulta, fecha y si vino de caché."""
    key = _key(method, url, params, data)
    path = cache_dir() / f"{key}.json"
    if use_cache and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = dict(payload["meta"])
        meta["from_cache"] = True
        return payload["data"], meta

    if offline():
        raise DataUnavailable(
            "Modo sin conexión (URBAN_AGENT_OFFLINE=1) y no hay una respuesta en caché para esta consulta."
        )

    host = urlparse(url).netloc
    headers = {"User-Agent": os.environ.get("URBAN_AGENT_UA", DEFAULT_UA), "Accept": "application/json"}
    last_error: Exception | None = None
    for attempt in range(retries):
        _throttle(host)
        try:
            resp = requests.request(method, url, params=params, data=data, headers=headers, timeout=timeout)
            if resp.status_code in RETRY_STATUS:
                last_error = DataUnavailable(f"{host} respondió {resp.status_code}")
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            body = resp.json()
            meta = {
                "method": method,
                "url": resp.url if method == "GET" else url,
                "host": host,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "from_cache": False,
            }
            if data is not None:
                meta["query"] = data.get("data", json.dumps(data, ensure_ascii=False))
            cache_dir().mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"meta": meta, "data": body}, ensure_ascii=False), encoding="utf-8")
            return body, meta
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
        except ValueError as exc:  # JSON inválido
            last_error = exc
            break
    raise DataUnavailable(f"No se pudo consultar {host}: {last_error}")

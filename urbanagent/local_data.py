"""Datos oficiales descargados a data/: MDT LiDAR (geoEuskadi) y población por sección censal (Eustat).

Son opcionales: si faltan los archivos o las dependencias, `available()` lo explica y el perfil
de zona vuelve a Open-Meteo y a los proxies de OpenStreetMap. Las rutas y la procedencia de cada
archivo están en data/fuentes.yaml.
"""
from __future__ import annotations

import csv
import io
import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Por debajo de esta cota un punto del MDT se trata como agua (el MDT da 0 m en el mar).
WATER_MAX_ELEV_M = 0.5


def data_dir() -> Path:
    return Path(os.environ.get("URBAN_AGENT_DATA", ROOT / "data"))


def manifest() -> dict:
    path = data_dir() / "fuentes.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def source_meta(key: str) -> dict:
    """Metadatos de procedencia de un archivo local, en el formato que espera Provenance.add."""
    s = manifest().get(key, {})
    return {
        "url": s.get("url"),
        "query": s.get("file"),
        "retrieved_at": s.get("downloaded"),
        "from_cache": False,
        "provider": s.get("provider", key),
        "license": s.get("license", ""),
    }


def _path(key: str) -> Path | None:
    s = manifest().get(key)
    if not s or not s.get("file"):
        return None
    return data_dir() / s["file"]


# --- Coordenadas ----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _transformer():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True)


def to_utm(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 -> ETRS89 / UTM 30N (EPSG:25830), el sistema del MDT y de las secciones."""
    return _transformer().transform(lon, lat)


def to_utm_many(lats: list[float], lons: list[float]) -> tuple[list[float], list[float]]:
    xs, ys = _transformer().transform(lons, lats)
    return list(xs), list(ys)


# --- MDT ------------------------------------------------------------------------------------

class Dem:
    """Ráster de elevación con georreferencia tipo world file (centro del píxel superior izquierdo)."""

    def __init__(self, array, x0: float, y0: float, dx: float, dy: float, nodata_below: float = -1e30) -> None:
        self.a = array
        self.x0, self.y0, self.dx, self.dy = x0, y0, dx, dy
        self.nodata_below = nodata_below

    @classmethod
    def load(cls, tif: Path) -> "Dem":
        import logging

        import tifffile

        # El TIFF declara nodata = -3.4e38, que tifffile avisa que no puede leer; lo tratamos con nodata_below.
        logging.getLogger("tifffile").setLevel(logging.ERROR)
        tfw = tif.with_suffix(".tfw")
        dx, _, _, dy, x0, y0 = (float(v) for v in tfw.read_text().split())
        return cls(tifffile.imread(tif), x0, y0, dx, dy)

    def sample_xy(self, x: float, y: float) -> float | None:
        col = round((x - self.x0) / self.dx)
        row = round((y - self.y0) / self.dy)
        if not (0 <= row < self.a.shape[0] and 0 <= col < self.a.shape[1]):
            return None
        v = float(self.a[row, col])
        return None if v < self.nodata_below else v


def is_water(elev: float | None) -> bool:
    return elev is not None and elev <= WATER_MAX_ELEV_M


# --- Población por sección censal ------------------------------------------------------------

def section_code(muni: int, dist: int, secc: int) -> str:
    return f"{muni:03d}{dist:02d}{secc:03d}"


def parse_population_csv(text: str) -> dict[str, int]:
    """CSV de Eustat 'Población de Gipuzkoa por distritos y secciones censales'.

    Filas con código de municipio abren municipio; filas con distrito y sección 000 son totales de
    distrito; el resto son secciones. Devuelve {código municipio+distrito+sección: habitantes}.
    """
    out: dict[str, int] = {}
    muni = dist = None
    for r in csv.reader(io.StringIO(text), delimiter=";"):
        if len(r) < 5 or not r[3].strip().isdigit() or not r[4].strip():
            continue
        if r[0].strip():
            muni = int(r[0])
        if r[2].strip():
            dist = int(r[2])
        secc = int(r[3])
        if secc > 0 and muni is not None and dist is not None:
            out[section_code(muni, dist, secc)] = int(r[4].replace(".", ""))
    return out


def parse_municipal_population(text: str) -> dict[str, dict]:
    """Población de cada municipio: suma de sus secciones. Devuelve {nombre: {"code", "population", "sections"}}."""
    names: dict[int, str] = {}
    for r in csv.reader(io.StringIO(text), delimiter=";"):
        if len(r) >= 2 and r[0].strip().isdigit() and r[1].strip():
            names[int(r[0])] = r[1].strip()
    out: dict[str, dict] = {}
    for code, pop in parse_population_csv(text).items():
        muni = int(code[:3])
        item = out.setdefault(names.get(muni, code[:3]), {"code": f"{muni:03d}", "population": 0, "sections": 0})
        item["population"] += pop
        item["sections"] += 1
    return out


@lru_cache(maxsize=1)
def municipal_population() -> dict[str, dict]:
    return parse_municipal_population(_path("poblacion").read_text(encoding="utf-8-sig"))


def population_status() -> str | None:
    p = _path("poblacion")
    if p is None or not p.exists():
        return "no está la tabla de población de Eustat; ver data/fuentes.yaml"
    return None


class Sections:
    """Polígonos de sección censal (UTM) con su población."""

    def __init__(self, geoms: dict[str, object], population: dict[str, int]) -> None:
        from shapely.strtree import STRtree

        self.codes = list(geoms)
        self.geoms = [geoms[c] for c in self.codes]
        self.population = population
        self.tree = STRtree(self.geoms)

    @classmethod
    def load(cls, shp: Path, csv_path: Path, province: str = "20") -> "Sections":
        import shapefile
        from shapely.geometry import shape
        from shapely.ops import unary_union

        parts: dict[str, list] = {}
        with shapefile.Reader(str(shp.with_suffix("")), encoding="latin1") as sf:
            for rec, shp_ in zip(sf.iterRecords(), sf.iterShapes()):
                if rec["SEC_PROV"] != province:
                    continue
                g = shape(shp_.__geo_interface__)
                if not g.is_valid:
                    g = g.buffer(0)
                code = section_code(int(rec["SEC_MUNI"]), int(rec["SEC_DIST"]), int(rec["SEC_SECC"]))
                parts.setdefault(code, []).append(g)
        geoms = {c: unary_union(gs) for c, gs in parts.items()}
        pop = parse_population_csv(csv_path.read_text(encoding="utf-8-sig"))
        return cls(geoms, pop)

    def in_circle(self, x: float, y: float, radius_m: float) -> dict:
        """Superficie de tierra con sección y población dentro del círculo (reparto proporcional al área)."""
        from shapely.geometry import Point

        circle = Point(x, y).buffer(radius_m, 64)
        land = pop = 0.0
        n = missing = 0
        for i in self.tree.query(circle):
            g = self.geoms[i]
            inter = g.intersection(circle).area
            if inter <= 0:
                continue
            n += 1
            land += inter
            code = self.codes[i]
            if code not in self.population:
                missing += 1
                continue
            pop += self.population[code] * inter / g.area
        return {
            "land_km2": land / 1e6,
            "population": pop,
            "sections": n,
            "sections_without_population": missing,
            "circle_share_in_sections": land / circle.area,
        }


# --- Carga perezosa ---------------------------------------------------------------------------

def _missing_deps() -> list[str]:
    missing = []
    for mod in ("numpy", "tifffile", "imagecodecs", "pyproj", "shapefile", "shapely"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


def dem_status() -> str | None:
    """None si el MDT se puede usar; si no, el motivo."""
    if os.environ.get("URBAN_AGENT_NO_LOCAL", "").strip() in {"1", "true", "yes"}:
        return "desactivado con URBAN_AGENT_NO_LOCAL"
    miss = [m for m in _missing_deps() if m in ("numpy", "tifffile", "imagecodecs", "pyproj")]
    if miss:
        return "faltan dependencias: " + ", ".join(miss)
    p = _path("mdt")
    if p is None or not p.exists():
        return f"no está el MDT ({p or 'sin entrada mdt en data/fuentes.yaml'}); ejecute scripts/descargar_datos.sh"
    return None


def sections_status() -> str | None:
    if os.environ.get("URBAN_AGENT_NO_LOCAL", "").strip() in {"1", "true", "yes"}:
        return "desactivado con URBAN_AGENT_NO_LOCAL"
    miss = [m for m in _missing_deps() if m in ("pyproj", "shapefile", "shapely")]
    if miss:
        return "faltan dependencias: " + ", ".join(miss)
    for key in ("secciones", "poblacion"):
        p = _path(key)
        if p is None or not p.exists():
            return f"no está {p or key}; ver data/fuentes.yaml y scripts/descargar_datos.sh"
    return None


@lru_cache(maxsize=1)
def dem() -> Dem:
    return Dem.load(_path("mdt"))


@lru_cache(maxsize=1)
def sections() -> Sections:
    return Sections.load(_path("secciones"), _path("poblacion"))

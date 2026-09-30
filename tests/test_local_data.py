"""Pruebas de los datos locales con un MDT y unas secciones SINTÉTICOS (no leen data/)."""
import numpy as np
import pytest
from shapely.geometry import box

from urbanagent import local_data, profile, sources
from urbanagent.session import Session

CSV_EUSTAT = (
    '"Población de Gipuzkoa por distritos y secciones censales"\r\n\r\n\r\n'
    ';;;;"Población según el sexo"\r\n;;;;"Total";"Hombres"\r\n"Cod";"Municipio";"Dist";"Secc"\r\n'
    '001;"Uno";01;000;1.300;650\r\n;;;001;1.000;500\r\n;;;002;300;150\r\n'
    ';;02;000;200;100\r\n;;;001;200;100\r\n'
    '71;"Dos";1;0;50;25\r\n;;;1;50;25\r\n'
)


def test_parse_population_csv_reads_sections_not_district_totals():
    pop = local_data.parse_population_csv(CSV_EUSTAT)
    assert pop == {"00101001": 1000, "00101002": 300, "00102001": 200, "07101001": 50}


def test_dem_sampling_and_nodata():
    a = np.array([[10.0, 20.0], [30.0, -3.4e38]], dtype=np.float32)
    dem = local_data.Dem(a, x0=100.0, y0=200.0, dx=25.0, dy=-25.0)
    assert dem.sample_xy(100, 200) == 10.0
    assert dem.sample_xy(126, 199) == 20.0
    assert dem.sample_xy(100, 175) == 30.0
    assert dem.sample_xy(125, 175) is None  # nodata
    assert dem.sample_xy(0, 0) is None  # fuera del ráster


def test_water_threshold():
    assert local_data.is_water(0.0) and local_data.is_water(0.4)
    assert not local_data.is_water(0.6) and not local_data.is_water(None)


def test_population_in_circle_is_area_weighted():
    # sección A: cuadrado de 2x2 km centrado en el origen, 4000 hab; B: lejos, fuera del círculo
    geoms = {"00101001": box(-1000, -1000, 1000, 1000), "00101002": box(5000, 5000, 6000, 6000)}
    s = local_data.Sections(geoms, {"00101001": 4000, "00101002": 999})
    r = s.in_circle(0, 0, 500)  # círculo de ~0,785 km² dentro de A
    assert r["sections"] == 1
    assert r["land_km2"] == pytest.approx(0.785, abs=0.01)
    assert r["population"] == pytest.approx(4000 * 0.785 / 4, rel=0.01)
    assert r["circle_share_in_sections"] == pytest.approx(1.0, abs=0.01)
    half = s.in_circle(1000, 0, 500)  # medio círculo fuera (como mar)
    assert half["circle_share_in_sections"] == pytest.approx(0.5, abs=0.01)


def test_slope_excludes_water_points():
    pts = [{"i": i, "j": j, "lat": i * 0.001, "lon": j * 0.001, "inside": True} for i in range(3) for j in range(4)]
    # columnas 0-1 en el agua (0 m); columnas 2-3 en tierra con un escalón de 10 m
    elevs = [0.0 if p["j"] < 2 else (10.0 if p["j"] == 2 else 20.0) for p in pts]
    st = profile.slope_stats(pts, elevs)
    assert st["grid_points_water"] == 6
    assert st["slope_pairs"] == 7  # 3 pares horizontales + 4 verticales, todos en tierra
    assert st["elev_min_m"] == 10.0


def test_profile_uses_local_data_when_available(monkeypatch):
    monkeypatch.delenv("URBAN_AGENT_NO_LOCAL")
    center = (43.3, -1.98)
    cx, cy = local_data.to_utm(*center)
    # MDT sintético: plano con 5 % de pendiente hacia el norte; al sur del centro, mar (0 m)
    n = 200
    x0, y0 = cx - 2500, cy + 2500
    rows = np.arange(n)
    ys = y0 - rows * 25.0
    col = np.where(ys < cy - 500, 0.0, (ys - (cy - 500)) * 0.05 + 1)
    a = np.repeat(col[:, None], n, axis=1).astype(np.float32)
    dem = local_data.Dem(a, x0, y0, 25.0, -25.0)
    secs = local_data.Sections({"00101001": box(cx - 3000, cy - 500, cx + 3000, cy + 3000)}, {"00101001": 35000})
    monkeypatch.setattr(local_data, "dem_status", lambda: None)
    monkeypatch.setattr(local_data, "sections_status", lambda: None)
    monkeypatch.setattr(local_data, "dem", lambda: dem)
    monkeypatch.setattr(local_data, "sections", lambda: secs)
    monkeypatch.setattr(local_data, "source_meta", lambda k: {"url": f"file://{k}", "query": k, "retrieved_at": "2026-09-30", "from_cache": False, "provider": k, "license": ""})
    monkeypatch.setattr(sources, "geocode", lambda p: ({"lat": center[0], "lon": center[1], "display_name": p}, {"url": "https://nominatim.test"}))
    monkeypatch.setattr(sources, "elevations", lambda pts: (_ for _ in ()).throw(AssertionError("no debe usar Open-Meteo")))

    def overpass(q):
        meta = {"url": "https://overpass.test", "query": q}
        if "out tags geom" in q:
            return {"elements": []}, meta
        return {"elements": [{"type": "count", "tags": {"total": "10"}} for _ in range(6)]}, meta

    monkeypatch.setattr(sources, "overpass", overpass)
    p = profile.build_profile("Costa sintética", Session(), radius_m=1500)
    m = p["metrics"]
    assert p["elevation_source"] == "mdt_lidar_25m" and p["grid_step_m"] == 100
    assert m["grid_points_water"] > 0
    # sin los puntos de agua, la pendiente norte-sur es la del plano (5 %) y no hay saltos costa-mar
    assert m["slope_p90_pct"] == pytest.approx(5.0, abs=0.3)
    assert m["elev_min_m"] >= 1.0
    assert 0.5 < m["land_share"] < 0.9
    assert m["density_area_km2"] == pytest.approx(m["area_km2"] * m["land_share"], rel=0.02)
    assert m["pop_per_km2"] == pytest.approx(35000 / (6 * 3.5), rel=0.02)  # densidad de la sección
    assert len(p["source_ids"]) == 6


def test_municipal_population_sums_sections():
    t = local_data.parse_municipal_population(CSV_EUSTAT)
    assert t["Uno"] == {"code": "001", "population": 1500, "sections": 3}
    assert t["Dos"]["population"] == 50

import pytest

from urbanagent import http


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Cada test usa su propia caché y nunca toca la red."""
    monkeypatch.setenv("URBAN_AGENT_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("URBAN_AGENT_OFFLINE", raising=False)
    # Los datos locales (MDT, secciones) no se usan salvo en los tests que los simulan.
    monkeypatch.setenv("URBAN_AGENT_NO_LOCAL", "1")
    http._last_call.clear()


def synthetic_metrics(**over):
    """Métricas SINTÉTICAS solo para probar la lógica (no son datos reales de ninguna zona)."""
    m = {
        "area_km2": 7.07,
        "slope_median_pct": 1.0,
        "slope_p90_pct": 3.0,
        "share_cells_over_6pct": 0.0,
        "slope_pairs": 100,
        "elev_min_m": 0.0,
        "elev_max_m": 30.0,
        "street_km": 24.0,
        "cycle_km": 6.0,
        "pedestrian_km": 2.0,
        "network_km": 30.0,
        "cycle_share": 0.2,
        "buildings": 3000,
        "shops": 400,
        "food_amenities": 300,
        "offices": 50,
        "bus_stops": 40,
        "rail_stops": 1,
        "poi": 750,
        "buildings_per_km2": 3500.0,
        "poi_per_km2": 250.0,
        "transit_stops_per_km2": 5.8,
    }
    m.update(over)
    return m

"""Pruebas del perfil de zona con respuestas SIMULADAS (formato según la documentación de cada API).

No verifican las APIs reales: para eso está `python -m urbanagent doctor`.
"""
import pytest

from urbanagent import profile, sources
from urbanagent.geo import offset_point
from urbanagent.http import DataUnavailable
from urbanagent.session import Session

CENTER = (43.3, -1.98)


def _way(coords, **tags):
    return {"type": "way", "id": 1, "tags": tags, "geometry": [{"lat": la, "lon": lo} for la, lo in coords]}


@pytest.fixture
def fake_sources(monkeypatch):
    def geocode(place):
        return (
            {"lat": CENTER[0], "lon": CENTER[1], "display_name": f"{place} (simulado)"},
            {"url": "https://nominatim.test/search?q=" + place, "retrieved_at": "2026-09-30T10:00:00+00:00", "from_cache": False},
        )

    def elevations(points):
        # plano inclinado 5 % hacia el norte
        vals = [(la - CENTER[0]) * 111195 * 0.05 for la, _ in points]
        return vals, [{"url": "https://elev.test/1", "retrieved_at": "2026-09-30T10:00:00+00:00", "from_cache": False}]

    def overpass(query):
        meta = {"url": "https://overpass.test/api", "query": query, "retrieved_at": "2026-09-30T10:00:00+00:00", "from_cache": False}
        if "out tags geom" in query:
            north1 = offset_point(*CENTER, 1000, 0)
            west = offset_point(*CENTER, 0, -1000)
            east = offset_point(*CENTER, 0, 1000)
            n2 = offset_point(*CENTER, 500, 1000)  # 500 m al norte de 'east'
            far = offset_point(*CENTER, 3000, 0)
            data = {"elements": [
                _way([CENTER, north1], highway="cycleway"),                       # 1000 m ciclovía
                _way([west, east], highway="residential"),                        # 2000 m calle
                _way([east, n2], highway="secondary", cycleway="lane"),           # calle con carril bici
                _way([far, offset_point(*CENTER, 3500, 0)], highway="residential"),  # fuera del radio
            ]}
            return data, meta
        counts = [3000, 400, 300, 50, 40, 1]
        data = {"elements": [{"type": "count", "id": 0, "tags": {"total": str(c)}} for c in counts]}
        return data, meta

    monkeypatch.setattr(sources, "geocode", geocode)
    monkeypatch.setattr(sources, "elevations", elevations)
    monkeypatch.setattr(sources, "overpass", overpass)


def test_classify_way():
    assert profile.classify_way({"highway": "cycleway"}) == (True, False, False)
    assert profile.classify_way({"highway": "residential"}) == (False, False, True)
    assert profile.classify_way({"highway": "secondary", "cycleway:right": "track"}) == (True, False, True)
    assert profile.classify_way({"highway": "pedestrian"}) == (False, True, False)
    assert profile.classify_way({"highway": "footway", "bicycle": "designated"})[0] is True
    assert profile.classify_way({"highway": "footway"}) == (False, False, False)


def test_parse_counts_requires_all_counts():
    with pytest.raises(DataUnavailable):
        profile.parse_counts({"elements": [{"type": "count", "tags": {"total": "1"}}]})


def test_queries_are_well_formed():
    q = profile.counts_query(43.3, -1.98, 1500)
    assert q.count("out count;") == len(profile.COUNT_KEYS)
    assert "(around:1500,43.300000,-1.980000)" in q
    assert profile.infra_query(43.3, -1.98, 1500).rstrip().endswith("out tags geom;")


def test_build_profile_metrics(fake_sources):
    s = Session()
    p = profile.build_profile("Zona simulada", s, radius_m=1500)
    m = p["metrics"]
    # la vía fuera del radio no cuenta; el tramo residencial este-oeste sí (2 km)
    assert m["cycle_km"] == pytest.approx(1.0 + 0.5, abs=0.05)
    assert m["street_km"] == pytest.approx(2.0 + 0.5, abs=0.05)
    assert m["network_km"] == pytest.approx(3.5, abs=0.05)
    assert m["cycle_share"] == pytest.approx(1.5 / 3.5, abs=0.02)
    assert m["buildings"] == 3000 and m["poi"] == 750
    assert m["buildings_per_km2"] == pytest.approx(3000 / 7.07, rel=0.01)
    assert m["slope_p90_pct"] == pytest.approx(5.0, abs=0.2)
    assert m["share_cells_over_6pct"] == 0
    assert len(p["source_ids"]) == 4 and p["source_ids"][0] == "S1"


def test_profile_is_cached_within_session(fake_sources, monkeypatch):
    s = Session()
    profile.build_profile("Zona simulada", s)
    monkeypatch.setattr(sources, "geocode", lambda place: (_ for _ in ()).throw(AssertionError("no debería volver a consultar")))
    again = profile.build_profile("Zona simulada", s)
    assert again["metrics"]["buildings"] == 3000


def test_slope_needs_enough_points():
    pts = [{"i": 0, "j": 0, "lat": 0, "lon": 0, "inside": True}]
    with pytest.raises(DataUnavailable):
        profile.slope_stats(pts, [1.0])

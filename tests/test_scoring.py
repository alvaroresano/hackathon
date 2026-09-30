import pytest

from urbanagent import scoring

from conftest import synthetic_metrics

CFG = scoring.load_config()


def test_personas_excludes_drone():
    r = scoring.analyze(synthetic_metrics(), "personas", CFG)
    ids = [row["vehicle"] for row in r["ranking"]]
    assert "dron" not in ids
    assert r["recommended"] in {"bicicleta", "patinete"}


def test_scores_within_range_and_contributions_add_up():
    r = scoring.analyze(synthetic_metrics(), "bienes", CFG)
    for row in r["ranking"]:
        assert 0 <= row["score"] <= 100
        assert sum(row["contributions"].values()) == pytest.approx(row["score"], abs=0.3)


def test_steeper_zone_lowers_wheeled_vehicle_scores():
    flat = scoring.analyze(synthetic_metrics(slope_median_pct=3.0), "personas", CFG)
    steep = scoring.analyze(synthetic_metrics(slope_median_pct=8.0), "personas", CFG)
    by = lambda r: {x["vehicle"]: x["score"] for x in r["ranking"]}
    for v in ("bicicleta", "patinete"):
        assert by(flat)[v] > by(steep)[v]


def test_drone_wins_steep_sparse_low_infra_high_demand():
    m = synthetic_metrics(
        slope_median_pct=9.0, slope_p90_pct=14.0, cycle_share=0.0, cycle_km=0.0,
        buildings_per_km2=800.0, poi_per_km2=300.0,
    )
    r = scoring.analyze(m, "bienes", CFG)
    assert r["recommended"] == "dron"
    assert r["robustness"] == 1.0
    assert any("infraestructura ciclista" in f for f in r["quality_flags"])
    # margen alto y robustez alta -> "alta", pero la alerta de calidad la rebaja un nivel
    assert r["confidence"] == "media"


def test_unknown_use_case_raises():
    with pytest.raises(ValueError):
        scoring.analyze(synthetic_metrics(), "turismo", CFG)


def test_robustness_is_a_proportion_and_counts_runs():
    r = scoring.analyze(synthetic_metrics(), "personas", CFG)
    assert 0.0 <= r["robustness"] <= 1.0
    # 2 vehículos x 3 pesos x 2 signos
    assert r["sensitivity_runs"] == 12


def test_close_call_lowers_confidence():
    # patinete y bici muy parecidos en zona llana: margen pequeño -> confianza no alta
    r = scoring.analyze(synthetic_metrics(), "personas", CFG)
    assert r["margin"] is not None and r["margin"] < 10
    assert r["confidence"] in {"baja", "media"}


def test_quality_flags_for_sparse_data():
    flags = scoring.quality_flags(synthetic_metrics(buildings=20, network_km=2.0, slope_pairs=10))
    assert len(flags) == 3

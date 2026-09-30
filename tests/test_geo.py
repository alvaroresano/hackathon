import math

import pytest

from urbanagent.geo import grid_points, haversine_m, offset_point, percentile, polyline_length_within


def test_haversine_one_degree_latitude():
    assert haversine_m(0, 0, 1, 0) == pytest.approx(111195, abs=150)


def test_offset_roundtrip():
    lat, lon = offset_point(43.3, -1.98, 1000, 0)
    assert haversine_m(43.3, -1.98, lat, lon) == pytest.approx(1000, abs=1)
    lat, lon = offset_point(43.3, -1.98, 0, 1000)
    assert haversine_m(43.3, -1.98, lat, lon) == pytest.approx(1000, abs=1)


def test_polyline_length_only_counts_segments_inside_radius():
    center = (43.3, -1.98)
    a = center
    b = offset_point(*center, 1000, 0)
    c = offset_point(*center, 5000, 0)  # fuera del radio de 1500 m
    assert polyline_length_within([a, b], center, 1500) == pytest.approx(1000, abs=1)
    assert polyline_length_within([a, b, c], center, 1500) == pytest.approx(1000, abs=1)
    assert polyline_length_within([b, c], center, 1500) == 0.0


def test_grid_points_marks_inside_circle():
    pts, step = grid_points((43.3, -1.98), 1500, 9)
    assert len(pts) == 81
    assert step == pytest.approx(375)
    corners = [p for p in pts if p["i"] in (0, 8) and p["j"] in (0, 8)]
    assert all(not p["inside"] for p in corners)
    center = next(p for p in pts if p["i"] == 4 and p["j"] == 4)
    assert center["inside"]


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([0, 10], 90) == pytest.approx(9)
    assert percentile([7], 90) == 7
    with pytest.raises(ValueError):
        percentile([], 50)

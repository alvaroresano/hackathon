"""Bucle del agente con un modelo SIMULADO (guion fijo) y perfiles sintéticos. No usa red."""
import json

import pytest

from urbanagent import tools
from urbanagent.agent import Backend, ToolCall, Turn, run_agent
from urbanagent.cli import main
from urbanagent.report import render_html, render_markdown
from urbanagent.session import Session

from conftest import synthetic_metrics


class ScriptedBackend(Backend):
    def __init__(self, first_calls, final_text):
        self.first_calls, self.final_text = first_calls, final_text
        self.seen_results = None

    def start(self, system, user, tools_):
        assert "compare_zones" in [t["name"] for t in tools_]
        return Turn("", self.first_calls)

    def next(self, results):
        self.seen_results = results
        return Turn(self.final_text, [])


@pytest.fixture
def fake_profiles(monkeypatch):
    def fake_build(place, session, radius_m=1500, grid_n=9):
        if place == "Fallida":
            from urbanagent.http import DataUnavailable
            raise DataUnavailable("Overpass no disponible (simulado)")
        sid = session.prov.add("simulado", "Proveedor de prueba", {"url": f"https://test/{place}", "retrieved_at": "2026-09-30T10:00:00+00:00"})
        return {"place": place, "resolved_as": place, "center": {"lat": 43.3, "lon": -1.98}, "radius_m": radius_m,
                "metrics": synthetic_metrics(), "definition_note": "", "source_ids": [sid]}

    monkeypatch.setattr(tools, "build_profile", fake_build)


def test_agent_runs_tools_and_verifies_numbers(fake_profiles):
    s = Session()
    call = ToolCall("t1", "compare_zones", {"places": ["Alfa", "Beta"], "use_case": "personas"})
    backend = ScriptedBackend([call], "Zona Alfa: pendiente mediana 1,0 % y 3500 edificios/km² [S1].")
    result = run_agent("¿Qué vehículo va mejor en Alfa y Beta?", backend, s)
    payload = json.loads(backend.seen_results[0].content)
    assert len(payload["zones"]) == 2 and payload["errors"] == []
    assert result["steps"] == 1
    assert result["verification"]["ok"], result["verification"]
    assert [e["event"] for e in s.events].count("tool") == 1


def test_agent_flags_invented_numbers(fake_profiles):
    s = Session()
    call = ToolCall("t1", "compare_zones", {"places": ["Alfa"], "use_case": "personas"})
    result = run_agent("¿Y en Alfa?", ScriptedBackend([call], "Hay 98765 habitantes en Alfa."), s)
    assert not result["verification"]["ok"]
    assert "98765" in result["verification"]["unverified"]


def test_tool_errors_come_back_as_data(fake_profiles):
    s = Session()
    out = tools.execute_tool("compare_zones", {"places": ["Alfa", "Fallida"], "use_case": "bienes"}, s)
    assert [z["place"] for z in out["zones"]] == ["Alfa"]
    assert out["errors"][0]["place"] == "Fallida"
    bad = tools.execute_tool("rank_vehicles_for_zone", {"place": "Alfa", "use_case": "turismo"}, s)
    assert bad["kind"] == "invalid_input"
    assert tools.execute_tool("no_existe", {}, s)["kind"] == "unknown_tool"
    assert tools.execute_tool("rank_vehicles_for_zone", {}, s)["kind"] == "invalid_input"


def test_max_steps_truncates_with_notice(fake_profiles):
    class Loop(Backend):
        def start(self, system, user, tools_):
            return Turn("", [ToolCall("t", "list_sources", {})])

        def next(self, results):
            return Turn("", [ToolCall("t", "list_sources", {})])

    result = run_agent("bucle", Loop(), Session(), max_steps=3)
    assert result["steps"] == 3 and "máximo de 3 pasos" in result["answer"]


def test_reports_render(fake_profiles):
    s = Session()
    res = tools.execute_tool("compare_zones", {"places": ["Alfa", "Fallida"], "use_case": "personas"}, s)
    md = render_markdown(res, s, "pregunta de prueba")
    html_out = render_html(res, s, "pregunta de prueba")
    for text in (md, html_out):
        assert "Alfa" in text and "Fallida" in text
        assert "Límites" in text and "verificar una persona" in text
    assert "S1" in md and "| Zona |" in md


def test_cli_analyze_without_connection_fails_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("URBAN_AGENT_OFFLINE", "1")
    code = main(["analyze", "--zones", "Donostia", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert code == 1
    assert "No se pudo analizar ninguna zona" in out


def test_cli_method_prints_limits(capsys):
    assert main(["method"]) == 0
    assert "limits" in capsys.readouterr().out

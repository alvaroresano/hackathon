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


def test_strip_thinking_removes_qwen_reasoning():
    from urbanagent.agent import strip_thinking

    assert strip_thinking("<think>\nrazono...\n</think>\n\nRespuesta final.") == "Respuesta final."
    assert strip_thinking("Sin razonamiento.") == "Sin razonamiento."


def test_ollama_backend_parses_tool_calls_and_answer(monkeypatch):
    """Respuestas SIMULADAS con el formato de /api/chat de Ollama (no llama a ningún servidor)."""
    import copy

    from urbanagent import agent

    replies = iter([
        {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "explain_method", "arguments": {}}}]}, "prompt_eval_count": 900},
        {"message": {"role": "assistant", "content": "<think>x</think>Listo [S1].", "thinking": "..."}, "prompt_eval_count": 1200},
    ])
    sent = []

    class Resp:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def fake_post(url, json, timeout):
        sent.append((url, copy.deepcopy(json)))
        return Resp(next(replies))

    monkeypatch.setattr(agent.requests, "post", fake_post)
    b = agent.OllamaBackend(model="qwen3:14b", base_url="http://ollama.test")
    t1 = b.start("sistema", "pregunta", [{"name": "explain_method", "description": "d", "input_schema": {"type": "object"}}])
    assert [c.name for c in t1.tool_calls] == ["explain_method"] and t1.tool_calls[0].args == {}
    t2 = b.next([agent.ToolResult(t1.tool_calls[0].id, "explain_method", "{}")])
    assert t2.text == "Listo [S1]." and not t2.tool_calls
    url, first = sent[0]
    assert url == "http://ollama.test/api/chat"
    assert first["model"] == "qwen3:14b" and first["stream"] is False and first["think"] is True
    assert first["options"]["num_ctx"] == 16384
    assert sent[1][1]["messages"][-1] == {"role": "tool", "tool_name": "explain_method", "content": "{}"}
    assert "thinking" not in b.messages[-1]


def test_ollama_backend_fails_loudly_when_context_is_full(monkeypatch):
    from urbanagent import agent

    class Resp:
        status_code = 200

        def json(self):
            return {"message": {"role": "assistant", "content": ""}, "prompt_eval_count": 4096}

    monkeypatch.setenv("URBAN_AGENT_NUM_CTX", "4096")
    monkeypatch.setattr(agent.requests, "post", lambda url, json, timeout: Resp())
    with pytest.raises(RuntimeError, match="contexto"):
        agent.OllamaBackend(base_url="http://ollama.test").start("s", "u", [])


def test_agent_asks_again_when_final_answer_is_empty(fake_profiles):
    class EmptyThenAnswer(ScriptedBackend):
        def __init__(self):
            super().__init__([ToolCall("t1", "compare_zones", {"places": ["Alfa"], "use_case": "personas"})], "")
            self.follow_ups = []

        def follow_up(self, text):
            self.follow_ups.append(text)
            return Turn("Respuesta final [S1].", [])

    s = Session()
    b = EmptyThenAnswer()
    result = run_agent("¿Y en Alfa?", b, s)
    assert result["answer"] == "Respuesta final [S1]."
    assert len(b.follow_ups) == 1
    assert "follow_up" in [e["event"] for e in s.events]


def test_compare_zones_gives_verdict_and_null_recommendation_when_unsuitable(monkeypatch):
    def fake_build(place, session, radius_m=1500, grid_n=None):
        steep = place == "Empinada"
        m = synthetic_metrics(slope_median_pct=15.0 if steep else 1.0, cycle_share=0.0 if steep else 0.2,
                              buildings_per_km2=100.0 if steep else 3500.0)
        return {"place": place, "resolved_as": place, "center": {"lat": 43.3, "lon": -1.98}, "radius_m": radius_m,
                "metrics": m, "definition_note": "", "source_ids": ["S1"], "sources": {"ubicación de la zona": "S1"}}

    monkeypatch.setattr(tools, "build_profile", fake_build)
    s = Session()
    out = tools.execute_tool("compare_zones", {"places": ["Empinada", "Llana"], "use_case": "personas"}, s)
    z = {x["place"]: x for x in out["zones"]}
    assert z["Empinada"]["recommended"] is None and z["Empinada"]["best_scored"] == "bicicleta"
    assert z["Empinada"]["verdict"].startswith("Ningún vehículo adecuado")
    assert z["Llana"]["recommended"] in {"bicicleta", "patinete"}
    assert z["Llana"]["verdict"].startswith("Recomendado:")
    assert z["Llana"]["sources"] == {"ubicación de la zona": "S1"}
    assert set(s.zone_numbers) == {"Empinada", "Llana"}


def test_short_zone_names_resolve_to_known_zones():
    # caso real: qwen3:14b pidió "Amara" en vez de "Amara, Donostia"
    assert tools.canonical_place("Amara") == "Amara, Donostia"
    assert tools.canonical_place("gros") == "Gros, Donostia"
    assert tools.canonical_place("Eibar") == "Eibar"
    assert tools.canonical_place("Zumaia") == "Zumaia"  # no está en zones.txt: se deja igual


def test_municipal_population_tool(monkeypatch):
    from urbanagent import local_data

    table = {"Donostia / San Sebastián": {"code": "069", "population": 183388, "sections": 141},
             "Arrasate/Mondragón": {"code": "055", "population": 22251, "sections": 18}}
    monkeypatch.setattr(local_data, "population_status", lambda: None)
    monkeypatch.setattr(local_data, "municipal_population", lambda: table)
    monkeypatch.setattr(local_data, "source_meta", lambda k: {"url": "https://eustat.test", "query": k, "retrieved_at": "2026-09-30", "provider": "Eustat", "license": ""})
    s = Session()
    r = tools.execute_tool("get_municipal_population", {"municipality": "donostia"}, s)
    assert r["population"] == 183388 and r["source_id"] == "S1"
    assert tools.execute_tool("get_municipal_population", {"municipality": "Mondragon"}, s)["population"] == 22251
    assert tools.execute_tool("get_municipal_population", {"municipality": "Madrid"}, s)["kind"] == "not_found"


def test_agent_self_corrects_unverified_numbers(fake_profiles):
    # caso real (P3, 30-sep-2026): el modelo dio de memoria "~55.000 habitantes" para Eibar
    class Invents(ScriptedBackend):
        def __init__(self):
            super().__init__([ToolCall("t1", "compare_zones", {"places": ["Alfa"], "use_case": "personas"})],
                             "Alfa tiene ~55.000 habitantes.")
            self.follow_ups = []

        def follow_up(self, text):
            self.follow_ups.append(text)
            return Turn("No tengo la población municipal de Alfa [S1].", [])

    s = Session()
    b = Invents()
    result = run_agent("¿Cuántos habitantes tiene Alfa?", b, s)
    assert "55.000" in b.follow_ups[0]
    assert result["answer"].startswith("No tengo")
    assert result["verification"]["ok"] and result["verification"]["self_corrected"]

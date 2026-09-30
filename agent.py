"""Bucle del agente con llamadas a herramientas. Admite Anthropic y cualquier API compatible con OpenAI (p. ej. Ollama)."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

from .session import Session
from .tools import TOOL_SPECS, execute_tool
from .verify import verify_answer

SYSTEM_PROMPT = """Eres un analista urbano de Gipuzkoa. Respondes preguntas sobre qué vehículo de micromovilidad \
(bicicleta, patinete eléctrico, dron de reparto) encaja mejor en distintas zonas.

Reglas:
1. Toda cifra que des debe salir de una herramienta. No inventes datos ni uses cifras de memoria. Si falta un dato, dilo.
2. Llama a las herramientas antes de responder. Para varias zonas usa compare_zones; para el detalle de una zona, \
rank_vehicles_for_zone y get_zone_profile. Usa explain_method si citas pesos, umbrales o definiciones.
3. Cita las fuentes con sus ids (S1, S2...) tal como las devuelven las herramientas.
4. Separa evidencias (lo medido) de interpretación (lo que crees que significa). La puntuación es un modelo \
heurístico, no demanda real.
5. Informa de la confianza y de las alertas de calidad de datos de cada zona. Si una zona falla, dilo.
6. Si mencionas drones, avisa de que no se ha verificado la normativa de espacio aéreo.
7. El agente aporta evidencias; las personas interpretan y deciden.

Formato (español, conciso): Respuesta breve; Evidencias (tabla); Fuentes; Límites; Qué debería verificar una persona."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ToolResult:
    id: str
    name: str
    content: str


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class Backend(ABC):
    @abstractmethod
    def start(self, system: str, user: str, tools: list[dict]) -> Turn: ...

    @abstractmethod
    def next(self, results: list[ToolResult]) -> Turn: ...


class AnthropicBackend(Backend):
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 2048) -> None:
        self.model = model or os.environ.get("URBAN_AGENT_MODEL", "claude-sonnet-5-5")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta ANTHROPIC_API_KEY.")
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self.system = ""
        self.tools: list[dict] = []

    def start(self, system, user, tools):
        self.system, self.tools = system, tools
        self.messages = [{"role": "user", "content": user}]
        return self._call()

    def next(self, results):
        self.messages.append(
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": r.id, "content": r.content} for r in results],
            }
        )
        return self._call()

    def _call(self) -> Turn:
        resp = requests.post(
            self.URL,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": self.system,
                "tools": self.tools,
                "messages": self.messages,
            },
            timeout=180,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Error de la API de Anthropic ({resp.status_code}): {resp.text[:300]}")
        body = resp.json()
        self.messages.append({"role": "assistant", "content": body["content"]})
        text = "".join(b.get("text", "") for b in body["content"] if b.get("type") == "text")
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in body["content"] if b.get("type") == "tool_use"]
        return Turn(text, calls)


class OpenAICompatBackend(Backend):
    """Para Ollama (http://localhost:11434/v1), vLLM u otros servidores con /chat/completions y herramientas."""

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("URBAN_AGENT_MODEL", "llama3.1")
        self.base_url = (base_url or os.environ.get("URBAN_AGENT_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "ollama")
        self.messages: list[dict] = []
        self.tools: list[dict] = []

    def start(self, system, user, tools):
        self.tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]
        self.messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._call()

    def next(self, results):
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r.id, "content": r.content})
        return self._call()

    def _call(self) -> Turn:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": self.messages, "tools": self.tools, "temperature": 0},
            timeout=300,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Error del servidor de modelos ({resp.status_code}): {resp.text[:300]}")
        msg = resp.json()["choices"][0]["message"]
        self.messages.append(msg)
        calls = []
        for tc in msg.get("tool_calls") or []:
            raw = tc["function"].get("arguments") or "{}"
            args = json.loads(raw) if isinstance(raw, str) else raw
            calls.append(ToolCall(tc["id"], tc["function"]["name"], args))
        return Turn(msg.get("content") or "", calls)


def run_agent(question: str, backend: Backend, session: Session, max_steps: int = 12) -> dict:
    """Ejecuta el bucle pregunta → herramientas → respuesta y verifica las cifras."""
    session.log("question", text=question)
    turn = backend.start(SYSTEM_PROMPT, question, TOOL_SPECS)
    steps = 0
    truncated = False
    while turn.tool_calls:
        session.log("assistant", text=turn.text, tool_calls=[{"name": c.name, "args": c.args} for c in turn.tool_calls])
        if steps >= max_steps:
            truncated = True
            break
        steps += 1
        results = []
        for call in turn.tool_calls:
            out = execute_tool(call.name, call.args, session)
            results.append(ToolResult(call.id, call.name, json.dumps(out, ensure_ascii=False)))
        turn = backend.next(results)

    answer = turn.text
    if truncated:
        answer = (answer + "\n\n" if answer else "") + (
            f"[El agente alcanzó el máximo de {max_steps} pasos sin cerrar la respuesta. Reformule o acote la pregunta.]"
        )
    verification = verify_answer(answer, session.tool_numbers, question)
    session.log("final", answer=answer, verification=verification, steps=steps)
    return {"answer": answer, "verification": verification, "steps": steps, "sources": session.prov.all()}

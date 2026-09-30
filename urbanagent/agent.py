"""Bucle del agente con llamadas a herramientas, sobre un modelo local servido por Ollama (por defecto qwen3:14b)."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

from .session import Session
from .tools import TOOL_SPECS, execute_tool
from .verify import verify_answer

SYSTEM_PROMPT = """Eres un analista urbano de Gipuzkoa. Respondes preguntas sobre qué vehículo de micromovilidad \
(bicicleta, patinete eléctrico, dron de reparto) encaja mejor en distintas zonas.

Reglas:
1. Toda cifra que des debe salir de una herramienta. No inventes datos ni uses cifras de memoria. No hagas \
cálculos propios. Si falta un dato, dilo.
2. Llama a las herramientas antes de responder. Para varias zonas usa compare_zones; para el detalle de una zona, \
rank_vehicles_for_zone y get_zone_profile. Usa explain_method si citas pesos, umbrales o definiciones.
3. Cada cifra va con la zona a la que pertenece: en cada fila o frase, usa solo datos de la zona que nombras.
4. Fuentes: cada zona trae un campo "sources" que dice qué id (S#) respalda cada tipo de dato (pendiente, \
población, infraestructura ciclista...). Cita el id del dato concreto; no asignes ids por tu cuenta.
5. Recomendación: usa el campo "verdict" de cada zona tal cual. Si "recommended" es null (suitable=false), ningún \
vehículo encaja bien allí: no presentes el mejor puntuado como recomendación, ni en el texto ni en las tablas.
6. Pendiente: para bici y patinete usa street_slope_median_pct (mediana de la pendiente de las calles); no la \
llames "media". La pendiente del terreno (terrain_slope_*) incluye laderas sin calles.
7. Población: population_in_circle es la población del círculo de la zona (Eustat, secciones censales), no la del \
municipio. Si te piden la población de un municipio, usa get_municipal_population. Nunca des cifras de memoria.
8. Para explicar por qué sale un resultado o por qué una zona puntúa más que otra, usa solo "score_breakdown" \
(puntos por característica) y los valores medidos. No afirmes que una zona tiene "más" o "mejor" algo sin \
comprobar que sus cifras lo dicen.
9. Separa evidencias (lo medido) de interpretación. La puntuación es un modelo heurístico, no demanda real. \
Informa de la confianza de cada zona explicándola con su campo "confidence_reason" (no inventes otros \
motivos) y de sus alertas de calidad. Si una zona falla, dilo.
10. Drones: solo se evalúan para reparto de bienes. Si hablas de drones, avisa de que no se ha verificado la \
normativa de espacio aéreo (AESA/ENAIRE). En preguntas sobre personas, no los menciones salvo que te pregunten.
11. El agente aporta evidencias; las personas interpretan y deciden.

Formato (español, conciso): Respuesta breve; Evidencias (tabla con la zona en cada fila); Fuentes (id y qué \
dato respalda); Límites; Qué debería verificar una persona."""

FOLLOW_UP_UNVERIFIED = (
    "Estas cifras de tu respuesta no salen de ninguna herramienta: {nums}. Reescribe la respuesta completa: "
    "quítalas o consulta antes la herramienta que las respalde. No uses datos de memoria."
)

FOLLOW_UP_EMPTY = (
    "No has escrito la respuesta final. Redáctala ahora en español con el formato indicado, "
    "usando solo los datos que ya han devuelto las herramientas."
)


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

    def follow_up(self, text: str) -> Turn:
        """Añade un mensaje del usuario a la conversación (para pedir la respuesta final si salió vacía)."""
        return Turn("", [])


DEFAULT_MODEL = "qwen3:14b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def ollama_url() -> str:
    return os.environ.get("URBAN_AGENT_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def ollama_model() -> str:
    return os.environ.get("URBAN_AGENT_MODEL", DEFAULT_MODEL)


def thinking_enabled() -> bool:
    """Razonamiento interno de qwen3, activado por defecto: en GPU cuesta ~26 s frente a ~17 s por respuesta,
    y sin él el modelo explica mal las comparaciones entre zonas (docs/validacion.md). URBAN_AGENT_THINK=0 lo quita."""
    return os.environ.get("URBAN_AGENT_THINK", "1").strip().lower() not in {"0", "false", "no"}


def strip_thinking(text: str) -> str:
    """Quita el razonamiento <think>...</think> que algunos modelos (qwen3) incluyen en la respuesta."""
    return _THINK.sub("", text or "").strip()


def num_ctx() -> int:
    """Ventana de contexto. El valor por defecto de Ollama (4096) no cabe: el prompt, las herramientas y los
    resultados de compare_zones lo superan y Ollama recorta el principio de la conversación sin avisar."""
    return int(os.environ.get("URBAN_AGENT_NUM_CTX", "16384"))


class OllamaBackend(Backend):
    """Modelo local de Ollama a través de su API nativa (/api/chat) con herramientas."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or ollama_model()
        self.base_url = (base_url or ollama_url()).rstrip("/")
        self.messages: list[dict] = []
        self.tools: list[dict] = []
        self._n_calls = 0

    def start(self, system, user, tools):
        self.tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]
        self.messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._call()

    def next(self, results):
        for r in results:
            self.messages.append({"role": "tool", "tool_name": r.name, "content": r.content})
        return self._call()

    def follow_up(self, text):
        self.messages.append({"role": "user", "content": text})
        return self._call()

    def _call(self) -> Turn:
        body = {
            "model": self.model,
            "messages": self.messages,
            "tools": self.tools,
            "stream": False,
            "think": thinking_enabled(),
            "options": {"temperature": 0, "num_ctx": num_ctx()},
        }
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=body, timeout=900)
        except requests.ConnectionError as exc:
            raise RuntimeError(f"No se pudo conectar con Ollama en {self.base_url}. ¿Está arrancado ('ollama serve')?") from exc
        if resp.status_code >= 400:
            raise RuntimeError(f"Error de Ollama ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        msg = data["message"]
        # Se guarda sin el razonamiento para no gastar contexto en los turnos siguientes.
        self.messages.append({k: v for k, v in msg.items() if k != "thinking"})
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc["function"]
            raw = fn.get("arguments") or {}
            args = json.loads(raw) if isinstance(raw, str) else raw
            self._n_calls += 1
            calls.append(ToolCall(tc.get("id") or f"call_{self._n_calls}", fn["name"], args))
        prompt_tokens = data.get("prompt_eval_count")
        if prompt_tokens and prompt_tokens >= num_ctx():
            raise RuntimeError(
                f"La conversación ({prompt_tokens} tokens) llena el contexto ({num_ctx()}). "
                "Aumente URBAN_AGENT_NUM_CTX o haga una pregunta con menos zonas."
            )
        return Turn(strip_thinking(msg.get("content") or ""), calls)


def run_agent(question: str, backend: Backend, session: Session, max_steps: int = 12) -> dict:
    """Ejecuta el bucle pregunta → herramientas → respuesta y verifica las cifras."""
    session.log("question", text=question)
    turn = backend.start(SYSTEM_PROMPT, question, TOOL_SPECS)
    steps = 0
    truncated = False
    asked_again = False
    while True:
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
        # Algunos modelos (qwen3) a veces terminan sin texto final: se pide una vez más.
        if truncated or turn.text.strip() or asked_again:
            break
        asked_again = True
        session.log("follow_up", reason="respuesta vacía")
        turn = backend.follow_up(FOLLOW_UP_EMPTY)

    answer = turn.text
    if truncated:
        answer = (answer + "\n\n" if answer else "") + (
            f"[El agente alcanzó el máximo de {max_steps} pasos sin cerrar la respuesta. Reformule o acote la pregunta.]"
        )
    if not answer.strip():
        answer = "[El modelo no produjo una respuesta final. Repita la pregunta o use 'analyze'.]"
    verification = verify_answer(answer, session.tool_numbers, question, session.zone_numbers)
    # Autocorrección (una vez): si hay cifras sin respaldo, se devuelven al modelo para que las quite o las consulte.
    if verification["unverified"] and not truncated:
        session.log("follow_up", reason="cifras sin respaldo", numbers=verification["unverified"])
        turn = backend.follow_up(FOLLOW_UP_UNVERIFIED.format(nums=", ".join(verification["unverified"])))
        while turn.tool_calls and steps < max_steps:
            session.log("assistant", text=turn.text, tool_calls=[{"name": c.name, "args": c.args} for c in turn.tool_calls])
            steps += 1
            results = [
                ToolResult(c.id, c.name, json.dumps(execute_tool(c.name, c.args, session), ensure_ascii=False))
                for c in turn.tool_calls
            ]
            turn = backend.next(results)
        if turn.text.strip():
            answer = turn.text
            verification = verify_answer(answer, session.tool_numbers, question, session.zone_numbers)
            verification["self_corrected"] = True
    session.log("final", answer=answer, verification=verification, steps=steps)
    return {"answer": answer, "verification": verification, "steps": steps, "sources": session.prov.all()}

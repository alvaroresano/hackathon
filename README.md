# Agente de micromovilidad para Gipuzkoa

Gipuzkoa AI Hackathon 2026 · Urban Challenge

**Pregunta urbana:** ¿qué tipo de vehículo (bicicleta, patinete eléctrico o dron de reparto) encaja mejor en cada zona de Gipuzkoa?

El agente consulta fuentes abiertas reales (OpenStreetMap y Open-Meteo), mide cada zona (pendiente, infraestructura ciclista, densidad de edificios y comercios), puntúa los vehículos con un modelo transparente, comprueba si la recomendación aguanta cambios en los pesos y explica sus límites. **El agente aporta evidencias; las personas interpretan y deciden.**

## Estado honesto: qué está probado y qué no

| Parte | Estado |
|---|---|
| Lógica de análisis, puntuación, sensibilidad, verificación de cifras, caché, bucle del agente, informes | Probado: 36 pruebas automáticas con datos **simulados** |
| Consultas reales a Nominatim, Overpass y Open-Meteo | **No probado en vivo.** Se escribió según la documentación de cada API, pero el entorno donde se desarrolló no tenía acceso a ellas |
| Llamada al modelo de lenguaje (Anthropic u Ollama) | **No probado con un modelo real**; el bucle se probó con un modelo simulado |

Por eso el primer paso es `python -m urbanagent doctor`: en 10 segundos dice si las fuentes responden. Si algo falla con datos reales (por ejemplo, un formato de respuesta distinto), el error aparece con mensaje claro y el arreglo suele estar en `urbanagent/sources.py` o `urbanagent/profile.py`.

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Nominatim exige identificarse: ponga su contacto
export URBAN_AGENT_UA="gipuzkoa-vehicle-agent (nombre-equipo; correo@universidad.es)"

python -m urbanagent doctor                              # 1) comprobar fuentes
python -m urbanagent analyze --use-case personas         # 2) informe de 18 zonas (rellena la caché)
python -m urbanagent analyze --use-case bienes --out outputs_bienes

export ANTHROPIC_API_KEY=...                             # 3) agente en lenguaje natural
python -m urbanagent ask "Compara Eibar, Tolosa y Zarautz para mover personas. ¿Qué vehículo y por qué?"
```

Con Ollama (sin clave de pago): `ollama serve`, un modelo con soporte de herramientas y
`python -m urbanagent ask "..." --backend openai --model <modelo>`.

La primera ejecución tarda unos minutos (respeta los límites de uso de las APIs). Después todo queda en `.cache/` y puede repetirse sin conexión con `URBAN_AGENT_OFFLINE=1`.

## Cómo funciona

```
pregunta ─► agente (LLM) ─► herramientas ──► OpenStreetMap (Nominatim, Overpass)
                │              │           └► Open-Meteo (elevación)
                │              ▼
                │        perfil de zona ─► puntuación por vehículo ─► sensibilidad
                ▼                                   │
        respuesta + fuentes S1..Sn ◄── caché + procedencia
                │
                ▼
     verificación de cifras ─► "pendiente de revisión humana"
```

Herramientas del agente (`urbanagent/tools.py`):

| Herramienta | Qué hace |
|---|---|
| `get_zone_profile` | Métricas reales de una zona, con ids de fuente |
| `rank_vehicles_for_zone` | Ranking, margen, robustez, confianza y alertas de datos |
| `compare_zones` | Varias zonas a la vez; si una falla, lo dice y sigue |
| `explain_method` | Pesos, umbrales, definiciones y límites, para citarlos |
| `list_sources` | Fuentes consultadas (proveedor, URL, fecha, licencia) |

## Trazabilidad y fiabilidad

- Cada dato lleva un id de fuente (S1, S2...) con proveedor, consulta, fecha y licencia.
- Cada ejecución guarda `runs/<fecha>/traza.jsonl` con preguntas, herramientas llamadas y respuesta.
- **Verificación de cifras:** tras la respuesta, `urbanagent/verify.py` comprueba que cada cifra aparece en algún resultado de herramienta y avisa de las que no. Es una comprobación heurística: detecta cifras inventadas, no valida el razonamiento.
- **Sensibilidad:** se varía ±30 % cada peso, uno a uno, y se mide cuántas veces cambia el vehículo recomendado (robustez). Si el margen es pequeño o hay alertas de calidad de datos, la confianza baja.
- **Supervisión humana:** todo informe termina con una lista de comprobaciones para una persona y el estado "pendiente de revisión humana".

## Ajustar el modelo

`config/scoring.yaml` contiene pesos y umbrales. **Son supuestos del equipo, no parámetros calibrados con datos reales de uso.** Cámbienlos según sus criterios y expliquen el cambio en la documentación.

## Estructura

```
urbanagent/   http.py (caché) · sources.py (APIs) · profile.py (métricas) · scoring.py (modelo)
              tools.py · agent.py (bucle LLM) · verify.py · report.py · cli.py
config/       scoring.yaml · zones.txt
tests/        36 pruebas (datos simulados)
docs/         ficha_sistema.md · explicacion_criterios.md · limites.md · guion_demo.md · plan_4_dias.md
```

Pruebas: `python -m pytest -q`.

## Variables de entorno

| Variable | Uso |
|---|---|
| `URBAN_AGENT_UA` | Identificación ante Nominatim/Overpass (obligatoria en la práctica) |
| `URBAN_AGENT_CACHE` | Carpeta de caché (por defecto `.cache`) |
| `URBAN_AGENT_OFFLINE` | `1` = solo caché, sin red |
| `ANTHROPIC_API_KEY`, `URBAN_AGENT_MODEL` | Modelo Anthropic (por defecto `claude-sonnet-5-5`) |
| `URBAN_AGENT_BASE_URL`, `OPENAI_API_KEY` | Servidor compatible con OpenAI (por defecto Ollama local) |

## Uso responsable de los datos

Nominatim permite como máximo 1 petición por segundo y exige identificarse; el código lo respeta. Los datos de OpenStreetMap son © colaboradores de OpenStreetMap (ODbL): citen la fuente en la presentación. Revisen las condiciones de uso y atribución de Open-Meteo antes de publicar resultados.

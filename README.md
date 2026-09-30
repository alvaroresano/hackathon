# Agente de micromovilidad para Gipuzkoa

Gipuzkoa AI Hackathon 2026 · Urban Challenge

**Pregunta urbana:** ¿qué tipo de vehículo (bicicleta, patinete eléctrico o dron de reparto) encaja mejor en cada zona de Gipuzkoa?

El agente consulta fuentes abiertas reales (OpenStreetMap, el MDT LiDAR de geoEuskadi y la población por sección censal de Eustat), mide cada zona (pendiente de las calles, infraestructura ciclista, habitantes y comercios por km²), puntúa los vehículos con un modelo transparente, comprueba si la recomendación aguanta cambios en los pesos y explica sus límites. **El agente aporta evidencias; las personas interpretan y deciden.**

## Estado honesto: qué está probado y qué no

| Parte | Estado |
|---|---|
| Consultas reales a Nominatim, Overpass y Open-Meteo | **Probado el 30-sep-2026**: `doctor` sin fallos; `analyze` completa las 18 zonas en los dos casos de uso |
| Datos oficiales locales (MDT de geoEuskadi, secciones y población de Eustat) | **Probado con los archivos reales**: las 544 secciones de Gipuzkoa cruzan con la tabla de población (724.797 habitantes) |
| Umbrales del modelo | **Recalibrados con datos reales** para que ninguna métrica se sature: ver [docs/calibracion.md](docs/calibracion.md) |
| Lógica de análisis, puntuación, sensibilidad, verificación de cifras, caché, informes | 47 pruebas automáticas con datos **sintéticos** (no tocan la red ni `data/`) |
| Llamada al modelo de lenguaje (Anthropic u Ollama) | **No probado con un modelo real**; el bucle se probó con un modelo simulado |
| Calidad de las recomendaciones frente a la realidad | **Sin validar**: requiere revisión humana con conocimiento local |

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
bash scripts/descargar_datos.sh                          # MDT (~41 MB) y secciones censales (~6 MB)

# Nominatim exige identificarse: ponga su contacto
export URBAN_AGENT_UA="gipuzkoa-vehicle-agent (nombre-equipo; correo@universidad.es)"

python -m urbanagent doctor                              # 1) comprobar fuentes y datos locales
python -m urbanagent analyze --use-case personas         # 2) informe de 18 zonas (rellena la caché)
python -m urbanagent analyze --use-case bienes --out outputs_bienes

export ANTHROPIC_API_KEY=...                             # 3) agente en lenguaje natural
python -m urbanagent ask "Compara Eibar, Tolosa y Zarautz para mover personas. ¿Qué vehículo y por qué?"
```

Con Ollama (sin clave de pago): `ollama serve`, un modelo con soporte de herramientas y
`python -m urbanagent ask "..." --backend openai --model <modelo>`.

La primera ejecución tarda unos minutos (respeta los límites de uso de las APIs; Overpass puede agotar el tiempo en alguna zona: basta con repetir). Después todo queda en `.cache/` y puede repetirse sin conexión con `URBAN_AGENT_OFFLINE=1`.

## Datos

| Dato | Fuente | Dónde | Para qué |
|---|---|---|---|
| Geocodificación | Nominatim (OSM) | API, en caché | Centro de cada zona (prefiere el nodo del núcleo, `place`) |
| Calles, carril bici, edificios, comercios, paradas | Overpass (OSM) | API, en caché | Infraestructura y demanda de reparto |
| Elevación | **MDT LiDAR 2017, 25 m** (geoEuskadi) | `data/mdt25/` (script) | Pendiente de las calles y del terreno |
| Límites de sección censal | geoEuskadi / Eustat | `data/secciones_eustat/` (script) | Repartir la población en el círculo; superficie de tierra |
| Población por sección, 01/01/2025 | Eustat | `data/xls0011434_c.csv` (en git) | Habitantes y habitantes/km² |
| Elevación (alternativa) | Open-Meteo (~90 m) | API | Solo si falta el MDT |
| Validación manual | Bidegorris y dBizi (Donostia), Encuesta de Movilidad 2021 | `data/` (en git) | Contrastar resultados; el agente no los usa |

La procedencia de cada archivo local (URL, fecha de descarga y licencia) está en [data/fuentes.yaml](data/fuentes.yaml), y el agente la cita con su id de fuente. Los archivos grandes no se suben a git: se descargan con `scripts/descargar_datos.sh`. **Sin `data/` el agente sigue funcionando**, pero con Open-Meteo y edificios de OSM en lugar de la población, y lo avisa en cada zona.

### Qué se mide en cada zona

- **Pendiente de las calles** (bici y patinete): mediana ponderada por longitud de tramos de al menos 50 m de las calles de OSM, con cotas del MDT y sin puentes ni túneles.
- **Pendiente del terreno** (dron): percentil 90 sobre una malla de 100 m. Los puntos de agua (cota ≤ 0,5 m) se excluyen.
- **Habitantes en el círculo**: la población de cada sección censal, multiplicada por la fracción de su área que cae dentro. Las densidades se calculan sobre la tierra del círculo, sin el mar.
- **Ningún vehículo adecuado**: si la mejor puntuación no llega a `min_suitable_score` (25), el informe no presenta al primero como recomendación.

## Cómo funciona

```
pregunta ─► agente (LLM) ─► herramientas ──► OpenStreetMap (Nominatim, Overpass)
                │              │           ├► MDT LiDAR 25 m (geoEuskadi) · Open-Meteo como alternativa
                │              │           └► población por sección censal (Eustat)
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

`config/scoring.yaml` contiene pesos, umbrales y la puntuación mínima. **Son supuestos del equipo, no parámetros calibrados con datos reales de uso.** Los umbrales se reajustaron con las 18 zonas reales para que ninguna métrica se sature; el razonamiento y las cifras están en [docs/calibracion.md](docs/calibracion.md). Si los cambian, documenten el motivo allí.

## Estructura

```
urbanagent/   http.py (caché) · sources.py (APIs) · local_data.py (MDT y población) · profile.py (métricas)
              scoring.py (modelo) · tools.py · agent.py (bucle LLM) · verify.py · report.py · cli.py
config/       scoring.yaml · zones.txt
data/         fuentes.yaml (procedencia) · población Eustat · datos de validación · MDT y secciones (descargados)
scripts/      descargar_datos.sh
tests/        47 pruebas (datos sintéticos; no tocan la red ni data/)
docs/         calibracion.md · limites.md · ficha_sistema.md · explicacion_criterios.md · guion_demo.md · plan_4_dias.md
```

Pruebas: `python -m pytest -q`.

## Variables de entorno

| Variable | Uso |
|---|---|
| `URBAN_AGENT_UA` | Identificación ante Nominatim/Overpass (obligatoria en la práctica) |
| `URBAN_AGENT_CACHE` | Carpeta de caché (por defecto `.cache`) |
| `URBAN_AGENT_OFFLINE` | `1` = solo caché, sin red |
| `URBAN_AGENT_DATA` | Carpeta de datos locales (por defecto `data/`) |
| `URBAN_AGENT_NO_LOCAL` | `1` = no usar MDT ni población aunque estén (Open-Meteo y edificios de OSM) |
| `ANTHROPIC_API_KEY`, `URBAN_AGENT_MODEL` | Modelo Anthropic (por defecto `claude-sonnet-5-5`) |
| `URBAN_AGENT_BASE_URL`, `OPENAI_API_KEY` | Servidor compatible con OpenAI (por defecto Ollama local) |

## Uso responsable de los datos

Nominatim permite como máximo 1 petición por segundo y exige identificarse; el código lo respeta. Los datos de OpenStreetMap son © colaboradores de OpenStreetMap (ODbL): citen la fuente en la presentación. Revisen las condiciones de uso y atribución de Open-Meteo, geoEuskadi y Eustat antes de publicar resultados, y citen las tres fuentes.

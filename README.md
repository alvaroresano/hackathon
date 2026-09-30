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
| Lógica de análisis, puntuación, sensibilidad, verificación de cifras, caché, informes | 62 pruebas automáticas con datos **sintéticos** (no tocan la red ni `data/`) |
| Agente con modelo de lenguaje local (Ollama + `qwen3:14b`) | **Probado con el modelo real en GPU**: 5 de las 6 preguntas del guion correctas y 1 con matices, todas con las cifras verificadas. Detalle en [docs/validacion.md](docs/validacion.md) |
| Calidad de las recomendaciones frente a la realidad | **Sin validar**: requiere revisión humana con conocimiento local |

## Cómo ejecutar el agente

Todos los comandos se ejecutan desde la raíz del repositorio. Probado en Linux (WSL2) con Python 3.12.

### 1. Preparación (solo la primera vez)

```bash
python3 -m venv .venv
source .venv/bin/activate                 # en Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
bash scripts/descargar_datos.sh           # MDT (~41 MB) y secciones censales (~6 MB); no están en git
```

Si `scripts/descargar_datos.sh` falla al bajar el MDT por FTP (algunas redes lo bloquean), descárguelo a mano desde la URL que aparece en `data/fuentes.yaml` y descomprímalo en `data/mdt25/`. Sin estos datos el agente funciona igualmente, pero con una elevación menos precisa (Open-Meteo) y sin población oficial.

### 2. En cada terminal nueva

```bash
source .venv/bin/activate
export URBAN_AGENT_UA="gipuzkoa-vehicle-agent (nombre-equipo; correo@universidad.es)"   # Nominatim exige un contacto real
```

### 3. Comprobar que todo funciona

```bash
python -m pytest -q            # 62 passed
python -m urbanagent doctor    # las 3 fuentes en OK y "MDT" y "Secciones y población" disponibles en data/
```

### 4. Informes deterministas (no necesitan modelo de lenguaje)

```bash
python -m urbanagent analyze --use-case personas                       # -> outputs/informe.html
python -m urbanagent analyze --use-case bienes --out outputs_bienes    # -> outputs_bienes/informe.html
python -m urbanagent analyze --zones Eibar "Gros, Donostia" --use-case bienes --out outputs_prueba
```

- Abra el informe en el navegador (desde WSL: `explorer.exe outputs/informe.html`). También se generan `informe.md` y `resultados.json`.
- La primera ejecución tarda unos 5 minutos (se respetan los límites de uso de las APIs). Si Overpass agota el tiempo en alguna zona, basta con repetir el comando.
- Después, todo queda en `.cache/` y se puede repetir sin internet: `URBAN_AGENT_OFFLINE=1 python -m urbanagent analyze ...`.

### 5. El agente con preguntas en lenguaje natural (Ollama + Qwen)

El agente usa un modelo de lenguaje **local**, servido por [Ollama](https://ollama.com). No necesita claves de API ni conexión con ningún proveedor de modelos. El modelo por defecto es **`qwen3:14b`**, que admite herramientas (*tool calling*): el modelo decide qué herramientas llamar y redacta la respuesta, pero todas las cifras salen de las herramientas.

1. **Instale Ollama** (solo la primera vez). En Linux/WSL: `curl -fsSL https://ollama.com/install.sh | sh`. En Windows o macOS, con el instalador de su web.
   - **En WSL no use la versión snap** (`snap install ollama`): no ve la GPU y el modelo va en CPU, unas 10 veces más lento. Si la tiene, quítela con `sudo snap remove ollama` e instale con el script anterior (después vuelva a descargar el modelo).
2. **Arranque el servidor** si no está en marcha y compruebe que responde:
   ```bash
   ollama serve                                   # en otra terminal (en muchas instalaciones ya arranca solo)
   curl http://localhost:11434/api/version
   ```
3. **Descargue el modelo** (solo la primera vez, unos 9 GB):
   ```bash
   ollama pull qwen3:14b
   ```
   Necesita unos 12 GB de memoria de GPU para ir fluido. Con menos memoria, use `qwen3:8b` (unos 5 GB) y defina `export URBAN_AGENT_MODEL=qwen3:8b`.
4. **Compruebe que el agente lo encuentra:** `python -m urbanagent doctor` debe mostrar `OK    Ollama: modelo qwen3:14b disponible`. Tras una pregunta, `ollama ps` debe indicar `100% GPU` en la columna `PROCESSOR`; si dice `CPU`, revise el paso 1.
5. **Pregunte:**
   ```bash
   python -m urbanagent ask "Compara Eibar, Tolosa y Zarautz para mover personas. ¿Qué vehículo y por qué?"
   python -m urbanagent ask "¿Qué vehículo encaja mejor para reparto en Gros, Donostia?" --model qwen3:8b   # otro modelo puntual
   ```

La respuesta se imprime con el número de pasos, las fuentes y las cifras comprobadas (incluidos avisos si una cifra no sale de las herramientas o si se atribuye a una zona que no es la suya), y se guarda en `outputs/respuesta.md`. La traza completa queda en `outputs/runs/<fecha>/traza.jsonl`. La primera pregunta tarda más porque Ollama carga el modelo en memoria. Hay más preguntas de prueba en [docs/guion_demo.md](docs/guion_demo.md).

Detalles de configuración del agente:
- Usa la API nativa de Ollama (`/api/chat`) con una ventana de contexto de 16.384 tokens (`URBAN_AGENT_NUM_CTX`). La de Ollama por defecto, 4.096, no basta: la conversación no cabe y Ollama recorta el principio sin avisar.
- El razonamiento interno de Qwen3 (*thinking*) está activado: sin él, el modelo explica mal las comparaciones entre zonas. En GPU cada respuesta tarda unos 15-25 s. Se puede quitar con `URBAN_AGENT_THINK=0`.
- Si el modelo termina sin escribir la respuesta final, el agente se la pide una vez más.
- Si la respuesta tiene cifras que no salen de ninguna herramienta, el agente se la devuelve una vez al modelo para que las quite o las consulte (autocorrección).

> Estado: probado con `qwen3:14b` real en las preguntas de [docs/validacion.md](docs/validacion.md). Las respuestas siguen necesitando revisión humana.

### 6. Consultar el método

```bash
python -m urbanagent method     # pesos, umbrales, definiciones de métricas y límites, en JSON
```

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
| `get_municipal_population` | Población oficial de un municipio (Eustat, 01/01/2025), distinta de la del círculo de una zona |
| `explain_method` | Pesos, umbrales, definiciones y límites, para citarlos |
| `list_sources` | Fuentes consultadas (proveedor, URL, fecha, licencia) |

## Trazabilidad y fiabilidad

- Cada dato lleva un id de fuente (S1, S2...) con proveedor, consulta, fecha y licencia.
- Cada ejecución guarda `runs/<fecha>/traza.jsonl` con preguntas, herramientas llamadas y respuesta.
- **Verificación de cifras:** tras la respuesta, `urbanagent/verify.py` comprueba que cada cifra aparece en algún resultado de herramienta y que, si la línea nombra una sola zona, la cifra es de esa zona y no de otra. Es una comprobación heurística: detecta cifras inventadas o mal atribuidas, no valida el razonamiento.
- **Fuentes por dato:** cada zona indica qué id (S#) respalda cada tipo de dato (pendiente, población, infraestructura ciclista...), para que el agente cite la fuente correcta.
- **Veredicto calculado:** la recomendación ("Recomendado: ..." o "Ningún vehículo adecuado ...") y el motivo de la confianza los calcula la herramienta, no el modelo de lenguaje.
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
scripts/      descargar_datos.sh · validar_bidegorris.py (OSM frente a la capa municipal de Donostia)
tests/        62 pruebas (datos sintéticos; no tocan la red ni data/)
docs/         resultados/ (informes y respuestas reales) · calibracion.md · validacion.md · limites.md · ficha_sistema.md · explicacion_criterios.md · guion_demo.md · plan_4_dias.md
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
| `URBAN_AGENT_MODEL` | Modelo de Ollama (por defecto `qwen3:14b`) |
| `URBAN_AGENT_OLLAMA_URL` | Dirección del servidor de Ollama (por defecto `http://localhost:11434`) |
| `URBAN_AGENT_NUM_CTX` | Ventana de contexto del modelo en tokens (por defecto 16384) |
| `URBAN_AGENT_THINK` | `0` = desactivar el razonamiento interno de Qwen3 (más rápido, peores explicaciones) |

## Uso responsable de los datos

Nominatim permite como máximo 1 petición por segundo y exige identificarse; el código lo respeta. Los datos de OpenStreetMap son © colaboradores de OpenStreetMap (ODbL): citen la fuente en la presentación. Revisen las condiciones de uso y atribución de Open-Meteo, geoEuskadi y Eustat antes de publicar resultados, y citen las tres fuentes.

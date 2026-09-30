# Validación con datos y modelo reales (30-sep-2026)

## 1. Infraestructura ciclista: OSM frente a la capa municipal de Donostia

Script: `URBAN_AGENT_OFFLINE=1 python scripts/validar_bidegorris.py`. La capa municipal (`data/BIDEGORRIA/`) está formada por 719 polígonos de unos 2 m de ancho (mediana). Su longitud se estima como perímetro / 2 y se compara con los km de infraestructura ciclista de OSM que usa el agente (`cycle_km`), dentro del mismo círculo de 1.500 m.

| Zona | OSM: km con infraestructura ciclista | Ayuntamiento: km de bidegorri (estimado) | OSM / Ayto. | Tierra del círculo en Donostia |
|---|---:|---:|---:|---:|
| Donostia | 16,5 | 13,8 | 1,19 | 100 % |
| Gros, Donostia | 18,5 | 15,3 | 1,21 | 100 % |
| Amara, Donostia | 29,2 | 23,3 | 1,25 | 100 % |
| Egia, Donostia | 29,5 | 25,4 | 1,16 | 100 % |
| Altza, Donostia | 6,2 | 4,4 | 1,40 | 84 % |

**Lectura:** OSM da entre un 16 % y un 40 % más kilómetros que la capa municipal. Posibles causas: OSM cuenta aparte los carriles de cada lado de la calle y las sendas peatonales con bici autorizada, y la estimación perímetro / 2 no es exacta. Lo importante para el modelo, que compara zonas entre sí, es que **las dos fuentes ordenan las 5 zonas igual** (Altza < Donostia < Gros < Amara < Egia). En Altza, el 16 % del círculo cae fuera de Donostia (Pasaia), donde no hay capa municipal, y eso explica parte de su diferencia. Fuera de Donostia no hay capa oficial con la que contrastar.

## 2. El agente con `qwen3:14b` (Ollama) en las preguntas del guion

Configuración final: Ollama en **GPU** (RTX 5080, 16 GB), contexto de 16.384 tokens, razonamiento interno activado y sin conexión (caché y datos locales). Las respuestas completas están en `docs/resultados/respuestas_agente.md` y las trazas en `docs/resultados/trazas/`.

| # | Pregunta | Herramientas | Cifras verificadas | Tiempo | Valoración |
|---|---|---|---:|---:|---|
| 1 | ¿Qué vehículo encaja mejor para mover personas en Donostia, Irun y Eibar? | `compare_zones` | 16, sin avisos | 22 s | ✅ Patinete en Donostia e Irun, ningún vehículo en Eibar; fuentes correctas por dato |
| 2 | Compara Gros y Amara para reparto de bienes. ¿Por qué sale ese resultado? | `compare_zones` | 19, sin avisos | 23 s | ✅ Explica bien la diferencia: Gros gana por demanda de reparto (33,7 frente a 25,5 puntos), aunque Amara tiene más densidad |
| 3 | ¿Cuántos habitantes tiene Eibar? | `get_municipal_population` | 2, sin avisos | 6 s | ✅ "27.118 habitantes (censo de 2025, S1)" y aclara que no es la población del círculo |
| 4 | ¿Qué vehículo recomiendas para personas en Eibar? | `rank_vehicles_for_zone` | 9, sin avisos | 17 s | ✅ Ningún vehículo adecuado (bicicleta con 17,2 < 25) |
| 5 | ¿Puedo usar drones de reparto en Tolosa? | `rank_vehicles_for_zone` | 5, sin avisos | 13 s | ⚠️ Avisa de AESA/ENAIRE, el viento y el ruido, pero dice "se recomiendan" cuando solo es idoneidad geográfica |
| 6 | ¿Y si la pendiente pesara más? | `explain_method` | 6, sin avisos | 19 s | ✅ Explica qué pendiente usa cada vehículo, los umbrales y cómo cambiarlos |

**Evolución:**
- En la primera prueba, en CPU y con un contexto de 4.096 tokens, una respuesta salió vacía tras 4 minutos, las fuentes estaban mal citadas y había una cifra atribuida a otra zona.
- Sin razonamiento interno, el modelo explicó mal P2 ("Gros gana por más densidad e infraestructura", cuando Amara tiene más de ambas).
- Sin la herramienta de población municipal, respondió P3 de memoria con "~55.000 habitantes (2023)", más del doble del dato oficial. La verificación lo detectó.

### Fallos detectados en pruebas anteriores y corrección aplicada

| Fallo observado con `qwen3:14b` | Corrección |
|---|---|
| Respuesta final vacía tras 4 minutos | Ventana de contexto de 16.384 tokens (la de Ollama por defecto, 4.096, se desbordaba sin aviso) y una segunda petición si la respuesta sale vacía |
| Fuentes inventadas ("S1 (pendiente)", cuando S1 es la geocodificación) | Cada zona trae `sources`: qué id respalda cada tipo de dato |
| Cifra de Eibar atribuida a Tolosa | `verify.py` comprueba que la cifra de una línea es de la zona que esa línea nombra |
| "Recomendado: Bicicleta" en una zona sin vehículo adecuado | `recommended` es `null` y la herramienta da el `verdict` ya redactado |
| Confianza baja explicada por "mala calidad de datos" | La herramienta da `confidence_reason` calculado (margen, robustez y alertas) |
| Pidió "Amara" en vez de "Amara, Donostia" | Los nombres cortos de zonas conocidas se resuelven al nombre de `config/zones.txt` |
| Explicaciones comparativas falsas | `score_breakdown` (puntos por característica), una regla del prompt y el razonamiento interno de qwen3 activado (en GPU, unos 26 s frente a 17 s). Con las tres cosas, P2 sale bien |
| Cifras de memoria ("~55.000 habitantes" para Eibar) | Herramienta `get_municipal_population` (Eustat) y **autocorrección**: si hay cifras sin respaldo, se devuelven al modelo una vez para que las quite o las consulte |

### Límites de la verificación automática

- Detecta cifras inventadas y cifras de otra zona en una línea que nombra **una sola** zona. No detecta **afirmaciones comparativas falsas** como la de P2, cuyas cifras son todas correctas.
- En las frases que comparan zonas ("vs.", "frente a", "mientras que") no se comprueba la zona, para evitar falsos positivos; un error dentro de una comparación puede pasar sin detectar.
- Por eso toda respuesta termina como **"pendiente de revisión humana"**.

### Próximas pruebas

- Repetir las preguntas con otras zonas y formulaciones: estas 6 ya se han usado para ajustar el prompt.
- En la demo, avisar de que la respuesta 5 muestra el límite del sistema: el dron sale por el relieve, no porque sea legal volar.

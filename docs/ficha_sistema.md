# Ficha del sistema

Texto para el formulario de "Resumen" de la plataforma del Gipuzkoa AI Hackathon 2026 (Urban Challenge).

**Nombre:** Agente de micromovilidad para Gipuzkoa
**Equipo:** Hat triki · **Integrantes:** Mattin Arluciaga, Álvaro Resano & Aritz Ryan San Sebastián

## Objetivo
Ayudar a entender qué tipo de vehículo (bicicleta, patinete eléctrico, dron de reparto) encaja mejor en cada zona de Gipuzkoa, para personas o para reparto de bienes.

## Usuarios previstos
Personas técnicas o responsables de movilidad que quieren una primera comparación de zonas con evidencias y fuentes. No sustituye un estudio de movilidad.

## Qué hace el agente
1. Localiza la zona (Nominatim) y mide un círculo de radio configurable a su alrededor.
2. Mide la pendiente de las calles y del terreno con el MDT LiDAR de 25 m de geoEuskadi (sin él, con Open-Meteo), excluyendo el mar.
3. Estima los habitantes del círculo con la población por sección censal de Eustat (01/01/2025).
4. Cuenta km de calles e infraestructura ciclista, edificios, comercios, oficinas y paradas (Overpass/OpenStreetMap).
5. Puntúa cada vehículo con un modelo de pesos editable. Si ninguno llega a la puntuación mínima, lo dice.
6. Prueba la robustez de la recomendación variando los pesos ±30 %.
7. Responde citando la fuente de cada dato, la confianza (con su motivo calculado), las alertas y los límites.
8. Comprueba las cifras de la respuesta contra los resultados de las herramientas y, si alguna no tiene respaldo, pide al modelo que la corrija.

## Datos y fuentes
OpenStreetMap vía Nominatim y Overpass (ODbL) · MDT LiDAR 2017 de 25 m (geoEuskadi) · Secciones censales (geoEuskadi/Eustat) y población por sección a 01/01/2025 (Eustat) · Open-Meteo Elevation API como alternativa (Copernicus DEM, ~90 m). Procedencia y fechas en `data/fuentes.yaml`; calibración en `docs/calibracion.md`.

## Modelo de lenguaje
`qwen3:14b` (Qwen 3, 14.000 millones de parámetros) ejecutado en local con Ollama, sin servicios externos de modelos, con razonamiento interno activado y contexto de 16.384 tokens. El modelo decide qué herramientas llamar y redacta la respuesta; **no calcula**: todas las cifras, el veredicto y el motivo de la confianza salen de las herramientas. En una GPU de 16 GB cada respuesta tarda entre 6 y 23 s.

## Herramientas
| Herramienta | Qué hace |
|---|---|
| `get_zone_profile` | Métricas de una zona (pendiente, población, infraestructura ciclista, comercios) con la fuente de cada dato |
| `rank_vehicles_for_zone` | Ranking de vehículos, veredicto, margen, robustez, confianza y desglose de la puntuación |
| `compare_zones` | Varias zonas a la vez; si una falla, lo indica y sigue |
| `get_municipal_population` | Población oficial de un municipio (Eustat, 01/01/2025) |
| `explain_method` | Pesos, umbrales, definiciones y límites del modelo |
| `list_sources` | Fuentes consultadas: proveedor, URL, fecha y licencia |

Sin modelo de lenguaje, `python -m urbanagent analyze` genera un informe determinista de las 18 zonas.

## Supervisión humana
- El agente no toma decisiones: presenta evidencias, confianza y límites.
- Cada informe termina con una lista de comprobaciones para una persona y el estado "pendiente de revisión humana".
- Verificación automática de cifras: se avisa de las que no aparecen en ninguna herramienta y de las atribuidas a una zona que no es la suya. Si hay cifras sin respaldo, el agente pide una vez al modelo que las corrija (autocorrección).
- Cada ejecución guarda una traza completa (pregunta, herramientas llamadas, respuesta y verificación).

## Riesgos conocidos y mitigaciones
| Riesgo | Mitigación |
|---|---|
| El modelo inventa una cifra | Comprobación de cifras contra resultados de herramientas, autocorrección y prompt que prohíbe cifras de memoria. Caso real: respondió "~55.000 habitantes" para Eibar; con la herramienta de Eustat responde 27.118 |
| El modelo cita mal la fuente o mezcla datos de dos zonas | Cada zona indica qué id respalda cada dato; la verificación detecta cifras de otra zona |
| El modelo explica mal por qué gana un vehículo | Desglose de la puntuación por característica calculado por la herramienta; razonamiento interno activado |
| Datos de OpenStreetMap incompletos | Alertas de calidad de datos; confianza rebajada; contraste con la capa municipal de bidegorris de Donostia (OSM da un 16-40 % más de km, pero ordena las zonas igual) |
| Umbrales que no distinguen entre zonas | Recalibrados con las 18 zonas reales para que ninguna característica se sature (`docs/calibracion.md`) |
| Pesos arbitrarios condicionan el resultado | Pesos públicos y editables; análisis de sensibilidad; se declara que son supuestos |
| Confundir el modelo con demanda real | Aviso en cada informe y en la respuesta |
| Recomendar drones sin viabilidad legal | Aviso obligatorio: no se ha verificado normativa de espacio aéreo |

## Evidencias
- `docs/resultados/`: informes de las 18 zonas (personas y bienes) y 6 respuestas reales del agente.
- `docs/validacion.md`: evaluación de esas respuestas y contraste con datos municipales.
- `docs/calibracion.md`: problemas detectados con datos reales y cómo se corrigieron.

## Limitaciones
Ver `docs/limites.md`.

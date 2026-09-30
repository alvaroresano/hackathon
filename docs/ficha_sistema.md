# Ficha del sistema (borrador)

Adapten los campos al formulario de "Resumen" de la plataforma. Los apartados entre corchetes los tiene que rellenar el equipo.

**Nombre:** Agente de micromovilidad para Gipuzkoa
**Equipo:** [nombre del equipo y universidad] · **Integrantes:** [3-4 personas]

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
7. Responde citando fuentes, confianza, alertas y límites.

## Datos y fuentes
OpenStreetMap vía Nominatim y Overpass (ODbL) · MDT LiDAR 2017 de 25 m (geoEuskadi) · Secciones censales (geoEuskadi/Eustat) y población por sección a 01/01/2025 (Eustat) · Open-Meteo Elevation API como alternativa (Copernicus DEM, ~90 m). Procedencia y fechas en `data/fuentes.yaml`; calibración en `docs/calibracion.md`.

## Modelo de lenguaje
[modelo usado: p. ej. Claude Sonnet 5.5 vía API, o modelo local con Ollama]. El modelo decide qué herramientas llamar y redacta la respuesta; **no calcula**: todas las cifras salen de las herramientas.

## Herramientas
get_zone_profile · rank_vehicles_for_zone · compare_zones · explain_method · list_sources.

## Supervisión humana
- El agente no toma decisiones: presenta evidencias, confianza y límites.
- Cada informe termina con una lista de comprobaciones para una persona y el estado "pendiente de revisión humana".
- Verificación automática de cifras: se avisa de las que no aparecen en ninguna herramienta.

## Riesgos conocidos y mitigaciones
| Riesgo | Mitigación |
|---|---|
| El modelo inventa una cifra | Comprobación de cifras contra resultados de herramientas; prompt que prohíbe cifras de memoria |
| Datos de OpenStreetMap incompletos | Alertas de calidad de datos; confianza rebajada; aviso explícito |
| Pesos arbitrarios condicionan el resultado | Pesos públicos y editables; análisis de sensibilidad; se declara que son supuestos |
| Confundir el modelo con demanda real | Aviso en cada informe y en la respuesta |
| Recomendar drones sin viabilidad legal | Aviso obligatorio: no se ha verificado normativa de espacio aéreo |

## Limitaciones
Ver `docs/limites.md`.

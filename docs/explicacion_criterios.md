# Cómo cubre cada criterio de evaluación

Criterios publicados en la web del hackathon (Urban Challenge). Los pesos son los oficiales; la columna "Dónde" apunta al código o documento que lo demuestra.

| Criterio | Peso | Cómo lo cubre este proyecto | Dónde |
|---|---:|---|---|
| Utilidad para comprender el problema urbano | 25 % | Responde a una pregunta concreta (qué vehículo encaja en cada zona) con métricas comparables por zona y explica qué factor pesa más en cada recomendación (contribuciones por característica). Alimenta decisiones de qué fabricar y dónde desplegar. | `scoring.py`, `report.py` |
| Calidad del análisis, fuentes y trazabilidad | 25 % | Datos abiertos reales; cada dato con id de fuente, fecha y licencia; caché reproducible; traza JSONL de cada ejecución; el método (pesos y umbrales) es público y editable. | `sources.py`, `session.py`, `http.py`, `config/scoring.yaml` |
| Funcionamiento del agente y uso de herramientas | 25 % | Agente con 5 herramientas que decide cuáles llamar según la pregunta; gestiona fallos de una zona sin abortar; el modo `analyze` sirve de respaldo determinista. | `agent.py`, `tools.py` |
| Claridad de las respuestas y artefactos | 15 % | Respuesta con formato fijo (respuesta, evidencias, fuentes, límites, qué verificar) e informe en Markdown y HTML. | `agent.py` (prompt), `report.py` |
| Fiabilidad, límites y supervisión humana | 10 % | Verificación automática de cifras; sensibilidad ante cambios de pesos; etiqueta de confianza; alertas de calidad de datos; lista de límites; checklist de revisión humana. | `verify.py`, `scoring.py`, `docs/limites.md` |

## Requisito clave de la convocatoria

La web indica que el agente debe consultar fuentes reales, hacer análisis verificables y explicar sus límites ante nuevas preguntas, sin devolver una visualización preconfigurada. Para la demo, usen **`ask`** (el agente decide qué consultar), no solo `analyze` (informe fijo). `analyze` sirve para poblar la caché y como respaldo si falla el modelo.

## Entregables que pide la plataforma

- **Prototipo funcional:** este repositorio. Comprueben en la plataforma cómo se sube (archivo, repositorio o enlace); esa parte no aparece en la información pública.
- **Documentación en formato libre:** este README, `ficha_sistema.md` y un informe generado con `analyze`. La ficha del sistema se completa desde "Resumen" en la plataforma: pueden copiar el borrador de `docs/ficha_sistema.md`.
- No puntúan la cantidad de documentación ni una tecnología concreta: prioricen que funcione y que las cifras sean trazables.

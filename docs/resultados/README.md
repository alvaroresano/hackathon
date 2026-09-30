# Resultados

Resultados reales generados el 30-sep-2026 con los datos descritos en `data/fuentes.yaml`. Se guardan aquí porque las carpetas `outputs*` no se suben a git.

| Archivo | Contenido | Cómo se generó |
|---|---|---|
| `informe_personas.html` / `.md` | Vehículo recomendado en las 18 zonas para mover personas: puntuación, margen, robustez, confianza, métricas, fuentes, límites y checklist de revisión | `python -m urbanagent analyze --use-case personas` |
| `informe_bienes.html` / `.md` | Lo mismo para reparto de bienes (incluye el dron) | `python -m urbanagent analyze --use-case bienes` |
| `resultados_personas.json` / `resultados_bienes.json` | Datos completos de los informes con la lista de fuentes (id, proveedor, URL, fecha, licencia) | Los mismos comandos |
| `respuestas_agente.md` | 6 respuestas del agente en lenguaje natural (`qwen3:14b`), copiadas sin editar | `python -m urbanagent ask "..."` |
| `trazas/p1.jsonl` … `p6.jsonl` | Traza de cada respuesta: pregunta, herramientas llamadas con sus argumentos, respuesta y verificación de cifras | Se guardan automáticamente con cada `ask` |

Los informes HTML se abren con cualquier navegador y no necesitan conexión. Para regenerarlo todo, siga el README principal.

La evaluación de las respuestas y el contraste con datos municipales están en `docs/validacion.md`; la calibración, en `docs/calibracion.md`.

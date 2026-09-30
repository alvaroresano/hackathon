# Cómo cubre cada criterio de evaluación

Criterios publicados en la web del hackathon (Urban Challenge). Los pesos son los oficiales. La columna "Dónde" apunta al código o documento que lo demuestra.

| Criterio | Peso | Cómo lo cubre este proyecto | Dónde |
|---|---:|---|---|
| Utilidad para comprender el problema urbano | 25 % | Responde a una pregunta concreta (qué vehículo encaja en cada zona, para personas o para bienes) con métricas comparables: pendiente de las calles, población, infraestructura ciclista y demanda de reparto. Explica qué característica pesa más en cada resultado (desglose de la puntuación) y dice cuándo **ningún** vehículo encaja (Eibar para personas). Sirve para decidir qué fabricar y dónde desplegarlo. | `scoring.py`, `tools.py`, `docs/resultados/` |
| Calidad del análisis, fuentes y trazabilidad | 25 % | Datos oficiales y abiertos: MDT LiDAR de 25 m (geoEuskadi), población por sección censal (Eustat), OpenStreetMap. Cada dato lleva su id de fuente, con fecha y licencia, y cada zona dice qué fuente respalda cada dato. Umbrales recalibrados con las 18 zonas reales. Contraste de OSM con la capa municipal de bidegorris de Donostia. Caché reproducible y traza de cada ejecución. | `data/fuentes.yaml`, `docs/calibracion.md`, `docs/validacion.md`, `local_data.py`, `session.py` |
| Funcionamiento del agente y uso de herramientas | 25 % | Agente con 6 herramientas y un modelo local (`qwen3:14b` con Ollama) que decide cuáles llamar según la pregunta. Probado con 6 preguntas reales (5 correctas y 1 con matices, todas con las cifras verificadas, entre 6 y 23 s). Gestiona fallos de una zona sin abortar y reintenta si la respuesta sale vacía. `analyze` sirve de respaldo determinista sin modelo. | `agent.py`, `tools.py`, `docs/validacion.md`, `docs/resultados/respuestas_agente.md` |
| Claridad de las respuestas y artefactos | 15 % | Respuesta con formato fijo (respuesta breve, evidencias en tabla, fuentes, límites, qué verificar). Veredicto ya redactado por la herramienta. Informes HTML y Markdown de las 18 zonas. | `agent.py` (prompt), `report.py`, `docs/resultados/` |
| Fiabilidad, límites y supervisión humana | 10 % | Verificación automática de cifras (sin respaldo o atribuidas a otra zona) con autocorrección. Sensibilidad ante cambios de pesos. Confianza con su motivo calculado. Alertas de calidad de datos. Puntuación mínima para no recomendar por defecto. Lista de límites y checklist de revisión humana. Los fallos reales del modelo y cómo se mitigaron están documentados. | `verify.py`, `scoring.py`, `docs/limites.md`, `docs/validacion.md` |

## Requisito clave de la convocatoria

La web pide que el agente consulte fuentes reales, haga análisis verificables y explique sus límites ante nuevas preguntas, sin devolver una visualización preconfigurada. En la demo usen **`ask`** (el agente decide qué consultar), no solo `analyze` (informe fijo). `analyze` sirve para poblar la caché y como respaldo si el modelo no está disponible.

## Entregables que pide la plataforma

- **Prototipo funcional:** este repositorio. Hay que confirmar en la plataforma cómo se sube (archivo, repositorio o enlace) y si el jurado lo ejecutará. El agente necesita Ollama y una GPU; sin ellos, `analyze` funciona igual y las respuestas reales del agente están guardadas en `docs/resultados/`.
- **Documentación en formato libre:** el README, `docs/` (ficha, límites, calibración, validación) y los informes de `docs/resultados/`. La ficha del sistema se completa desde "Resumen" en la plataforma; se puede copiar de `docs/ficha_sistema.md`.
- No puntúan la cantidad de documentación ni una tecnología concreta: lo que cuenta es que funcione y que las cifras sean trazables.

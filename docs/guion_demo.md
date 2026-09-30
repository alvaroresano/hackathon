# Guion de demo

Objetivo: enseñar que el agente decide qué consultar, cita fuentes, admite límites y necesita supervisión humana. Antes de grabar o presentar, ejecuten `analyze` para poblar la caché y evitar esperas.

## Preguntas de prueba

| Pregunta | Qué debería ocurrir | Qué demuestra |
|---|---|---|
| "¿Qué vehículo encaja mejor para mover personas en Donostia, Irun y Eibar?" | Llama a `compare_zones`, resume por zona, cita S1..Sn, indica confianza y alertas | Uso de herramientas y trazabilidad |
| "Compara Gros y Amara para reparto de bienes. ¿Por qué sale ese resultado?" | Usa `rank_vehicles_for_zone`; explica contribuciones por característica | Explicabilidad |
| "¿Cuántos habitantes tiene Eibar?" | Usa `get_municipal_population`: 27.118 habitantes (Eustat, 01/01/2025), y aclara que no es la población del círculo | Fuente oficial en lugar de memoria del modelo |
| "¿Qué vehículo recomiendas para personas en Eibar?" | Debería decir que ninguno encaja bien (puntuación por debajo del mínimo) y explicar la pendiente de sus calles | Honestidad ante resultados pobres |
| "¿Puedo usar drones de reparto en Tolosa?" | Debería avisar de que no se ha verificado la normativa de espacio aéreo | Límites y supervisión humana |
| "¿Y si la pendiente pesara más?" | Debería consultar `explain_method` y explicar cómo se cambia `config/scoring.yaml` | Transparencia del método |

Estos comportamientos dependen del modelo de lenguaje. Los resultados reales con `qwen3:14b` están en `docs/validacion.md`. Si cambian de modelo, repítanlos y ajusten `SYSTEM_PROMPT` en `urbanagent/agent.py` si hace falta.

Antes de la demo: compruebe con `ollama ps` que el modelo corre en GPU (en CPU cada respuesta tarda varios minutos) y haga una pregunta de calentamiento para que el modelo quede cargado en memoria.

## Qué enseñar en pantalla
1. La respuesta del agente y el pie con pasos, fuentes y cifras comprobadas (y los avisos si una cifra no tiene respaldo o se atribuye a otra zona).
2. Una cifra concreta rastreada hasta su fuente (id S# → URL/consulta en `resultados.json` o en la traza).
3. Una zona con confianza baja o alertas y cómo el agente lo comunica.
4. El informe HTML de `analyze` como artefacto.
5. `config/scoring.yaml` y cómo un cambio de pesos altera la robustez.

## Antes de entregar
- [ ] `python -m urbanagent doctor` sin fallos
- [ ] `python -m pytest -q` en verde
- [ ] Revisadas a mano 2-3 zonas en OpenStreetMap
- [ ] Rellenados los datos del equipo y el modelo en `docs/ficha_sistema.md`
- [ ] Un integrante distinto al autor ha reproducido la instalación desde cero

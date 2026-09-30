# Respuestas reales del agente

Seis preguntas del guion de demo (`docs/guion_demo.md`) respondidas por el agente con `qwen3:14b` (Ollama, GPU RTX 5080), razonamiento interno activado, sin conexión (caché y datos locales), el 30-sep-2026. Las respuestas se copian tal cual, sin editar. La evaluación de cada una está en `docs/validacion.md`; la traza completa (herramientas, argumentos y verificación) en `trazas/`.

> El agente aporta evidencias; las personas interpretan y deciden. Todas las respuestas quedan pendientes de revisión humana.

## P1. ¿Qué vehículo encaja mejor para mover personas en Donostia, Irun y Eibar?

- Herramientas: `compare_zones` · Cifras comprobadas: 16 (sin avisos) · Tiempo: 22 s · Traza: `trazas/p1.jsonl`

**Respuesta breve:**  
En Donostia y Irun, el patinete eléctrico es recomendado, mientras que en Eibar, ningún vehículo encaja bien.  

---

**Evidencias**  
| Zona       | Recomendado       | Puntuación | Pendiente calles (%) | Población en círculo | Infraestructura ciclista (%) |  
|------------|-------------------|------------|----------------------|----------------------|-----------------------------|  
| **Donostia** | Patinete eléctrico | 88.0       | 1.07                 | 56,164               | 16.7                        |  
| **Irun**     | Patinete eléctrico | 60.1       | 2.35                 | 45,784               | 10.0                        |  
| **Eibar**    | Ninguno           | 17.2       | 7.25                 | 23,469               | 2.8                         |  

---

**Fuentes**  
- Pendiente calles: S2, S3 (LiDAR geoEuskadi).  
- Población: S5, S6 (Eustat, secciones censales).  
- Infraestructura ciclista: S3 (OpenStreetMap).  

---

**Límites**  
- En Eibar, la pendiente media de calles (7.25%) y baja infraestructura ciclista (2.8%) hacen que ningún vehículo sea adecuado.  
- En Donostia, la alta densidad poblacional (14,469 hab/km²) y buena infraestructura ciclista (16.7%) favorecen al patinete.  
- Para drones de reparto, no se ha verificado la normativa de espacio aéreo (AESA/ENAIRE).  

---

**Qué debería verificar una persona**  
- En Donostia e Irun, comprobar la disponibilidad de puntos de carga para patinetes.  
- En Eibar, evaluar alternativas como transporte público o camiones eléctricos.  
- Consultar fuentes S5 y S6 para confirmar datos demográficos.

---

## P2. Compara Gros y Amara para reparto de bienes. ¿Por qué sale ese resultado?

- Herramientas: `compare_zones` · Cifras comprobadas: 19 (sin avisos) · Tiempo: 23 s · Traza: `trazas/p2.jsonl`

**Respuesta breve:** En Gros, la bicicleta obtiene una puntuación más alta (84.3 vs 78.6 en Amara) debido a una mayor demanda de reparto (33.7 vs 25.5) y una infraestructura ciclista adecuada (15.7 puntos). En Amara, aunque la densidad poblacional es mayor (12,523 hab/km² vs 10,968), la demanda de reparto es menor, lo que reduce su puntuación.

---

**Evidencias**  
| Zona         | Puntuación | Demanda de reparto | Infraestructura ciclista | Pendiente mediana (calles) |  
|--------------|------------|--------------------|--------------------------|----------------------------|  
| Gros         | 84.3       | 33.7               | 15.7                     | 1.49%                      |  
| Amara        | 78.6       | 25.5               | 18.2                     | 1.19%                      |  

---

**Fuentes**  
- **Demanda de reparto:** Calculada a partir de densidad poblacional (S5, S6) y puntos de interés (S4).  
- **Infraestructura ciclista:** Datos de OpenStreetMap (S3, S8).  
- **Pendiente:** MDT LiDAR de geoEuskadi (S2).  

---

**Límites**  
- La puntuación no refleja la normativa aérea para drones (no verificada).  
- La "demanda de reparto" es un modelo heurístico, no datos reales de entregas.  

---

**Qué debería verificar una persona**  
1. Confirmar si la densidad de comercios en Gros (338.3 POI/km²) supera a Amara (258.3), lo que justificaría mayor demanda.  
2. Evaluar si la pendiente del terreno (6.2% en Gros) afecta la viabilidad de drones, aunque el modelo no lo considera.  
3. Verificar si la infraestructura ciclista en Amara (18.7% de calles ciclistas) es suficiente para bicicletas de carga.

---

## P3. ¿Cuántos habitantes tiene Eibar?

- Herramientas: `get_municipal_population` · Cifras comprobadas: 2 (sin avisos) · Tiempo: 6 s · Traza: `trazas/p3.jsonl`

Eibar tiene **27.118 habitantes** según el censo de 2025 (S1).  
Este dato corresponde a toda la población del municipio, no al círculo de 1.500 m que se usa para evaluar zonas.

---

## P4. ¿Qué vehículo recomiendas para personas en Eibar?

- Herramientas: `rank_vehicles_for_zone` · Cifras comprobadas: 9 (sin avisos) · Tiempo: 17 s · Traza: `trazas/p4.jsonl`

**Respuesta breve:**  
En Eibar, ningún vehículo de micromovilidad (bicicleta o patinete eléctrico) es adecuado para personas, ya que el mejor puntuado (bicicleta) obtiene 17.2 puntos, por debajo del umbral mínimo de 25 puntos.  

---

**Evidencias**  
| Zona         | Pendiente mediana de calles (%) | Infraestructura ciclista (km) | Población en el círculo | Población por km² |  
|--------------|-------------------------------|-----------------------------|------------------------|------------------|  
| Eibar        | 7.25                          | 1.58                        | 23.469                 | 3.392            |  

---

**Fuentes**  
- Pendiente mediana de calles: **S2, S3** (MDT LiDAR de geoEuskadi).  
- Infraestructura ciclista: **S3** (OpenStreetMap).  
- Población: **S5, S6** (Eustat, secciones censales).  

---

**Límites**  
- La pendiente media de calles (7.25%) y el 58.4% de calles con pendiente >6% (S2, S3) penalizan a la bicicleta.  
- La infraestructura ciclista es muy limitada (1.58 km, S3).  
- La alta densidad de población (3.392 hab/km²) no compensa la falta de infraestructura.  

---

**Qué debería verificar una persona**  
1. Confirmar la precisión de los datos de pendiente y infraestructura en Eibar (S2, S3).  
2. Evaluar si existen rutas alternativas no incluidas en OpenStreetMap.  
3. Considerar mejoras en la infraestructura ciclista como prioridad para permitir bicicletas.  
4. Verificar la normativa de drones (AESA/ENAIRE) si se considera su uso futuro.

---

## P5. ¿Puedo usar drones de reparto en Tolosa?

- Herramientas: `rank_vehicles_for_zone` · Cifras comprobadas: 5 (sin avisos) · Tiempo: 13 s · Traza: `trazas/p5.jsonl`

**Respuesta breve:**  
Los drones de reparto se recomiendan para Tolosa, pero se debe verificar la normativa de espacio aéreo (AESA/ENAIRE), el viento y el ruido, ya que no están incluidos en la evaluación.

---

**Evidencias (Tolosa, radio 1500 m):**  
| **Zona**       | **Puntuación dron** | **Pendiente mediana de calles (%)** | **Densidad poblacional (hab/km²)** | **Confianza** |  
|----------------|---------------------|------------------------------------|-----------------------------------|---------------|  
| Tolosa         | 52.3                | 3.49                               | 2554.2                            | Media         |  

---

**Fuentes:**  
- **Pendiente de calles:** S2, S3 (MDT LiDAR de geoEuskadi).  
- **Densidad poblacional:** S5, S6 (Eustat, secciones censales).  
- **Recomendación:** S1 (OpenStreetMap para infraestructura).  

---

**Límites:**  
- La puntuación no incluye verificación legal (normativa aérea, ruido) ni factores operativos (viento, obstáculos).  
- La confianza es "media" por el margen de 8.2 puntos sobre la bicicleta, pero no hay alertas de calidad de datos.  

---

**Qué debería verificar una persona:**  
1. Consultar con AESA/ENAIRE sobre normas de espacio aéreo en Tolosa.  
2. Evaluar impacto de ruido y condiciones climáticas (viento) en zonas densas.  
3. Comprobar si existen restricciones locales para drones en áreas urbanas.

---

## P6. ¿Y si la pendiente pesara más?

- Herramientas: `explain_method` · Cifras comprobadas: 6 (sin avisos) · Tiempo: 19 s · Traza: `trazas/p6.jsonl`

**Respuesta breve:**  
Si la pendiente (street_slope_median_pct) pesara más, bicicleta y patinete perderían puntos en zonas con pendiente elevada, mientras que el dron podría mejorar su puntuación en terrenos abruptos. Los pesos actuales para "flatness" en bicicleta y patinete son 0.35 y 0.4 (respectivamente) para uso de personas, y el dron tiene un peso de 0.25 para "steepness" en reparto de bienes.

---

**Evidencias**  
| Zona | Pendiente mediana (street_slope_median_pct) | Peso de planitud ("flatness") para bicicleta | Peso de planitud para patinete | Peso de rugosidad ("steepness") para dron |
|------|---------------------------------------------|-----------------------------------------------|----------------------------------|-------------------------------------------|
| Cualquier zona | Según datos de MDT LiDAR (S1) | 0.35 (personas) | 0.4 (personas) | 0.25 (bienes) |

---

**Fuentes**  
- **S1**: MDT LiDAR de geoEuskadi (pendiente de calles).  
- **S2**: Definiciones de métricas en `explain_method` (pesos y umbrales).  

---

**Límites**  
- Los pesos son supuestos heurísticos, no calibrados con datos reales de uso.  
- La sensibilidad al cambio de pesos es del 30% (`sensitivity_delta`).  
- No se considera la normativa de drones (AESA/ENAIRE).  

---

**Qué debería verificar una persona**  
1. Ajustar manualmente los pesos en `config/scoring.yaml` para probar escenarios.  
2. Validar con datos reales de movilidad (ej.: Encuesta de Movilidad 2021) si se requiere precisión.  
3. Consultar normativa de drones para zonas específicas.

---

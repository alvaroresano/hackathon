# Calibración con datos reales (30-sep-2026)

Primera ejecución con datos reales de las 18 zonas de `config/zones.txt`, radio de 1.500 m. Todas las cifras de este documento salen de esa ejecución. Fuentes: Nominatim, Overpass (OSM), MDT LiDAR 2017 de 25 m (geoEuskadi) y población por sección censal a 01/01/2025 (Eustat). Para reproducirlo:

```bash
bash scripts/descargar_datos.sh
python -m urbanagent analyze --use-case personas
python -m urbanagent analyze --use-case bienes --out outputs_bienes
```

## 1. Problemas detectados en la primera ejecución real

Configuración original: Open-Meteo para la elevación y edificios de OSM para la densidad.

| Problema | Evidencia | Corrección |
|---|---|---|
| La densidad valía 0 en todas las zonas | El máximo de `buildings_per_km2` era 367 (Egia) y el umbral empezaba en 500. OSM mapea manzanas enteras como un solo edificio | Densidad con **población de Eustat** repartida por secciones censales |
| Los puntos del mar leían 0 m y aplanaban la costa | 38 de 81 puntos de la malla de Donostia estaban a 0 m, 34 en Gros, 25 en Zarautz y 22 en Hondarribia | Los puntos con cota ≤ 0,5 m se excluyen. El MDT de geoEuskadi también da 0 m en el mar, así que el filtro sigue haciendo falta |
| Egia mal geocodificada | Nominatim devolvía primero la estación de Atotxa | Se piden 5 candidatos y se prefiere `place`, luego `boundary` |
| Bergara descentrada | El punto del límite municipal (43,1249; −2,4295) está a unos 1,5 km del nodo `place=town` del casco (43,1175; −2,4133). En su círculo solo había 3.847 habitantes y 7,4 comercios/km² | La misma preferencia por `place`. Ahora tiene 8.916 habitantes en el círculo |
| En zonas muy empinadas se "recomendaba" con 1 punto sobre 100 | Eibar: bicicleta con 1,0 | Nuevo `min_suitable_score: 25`: por debajo, la zona se marca como "ningún vehículo adecuado" |
| Hernani y Lasarte-Oria fallaban | Los dos servidores de Overpass agotaron el tiempo | Se resolvió al reintentar. No se tocó el código |

## 2. Cambios de método

- **Pendiente de las calles.** Con el MDT de 25 m y una malla de 100 m, la pendiente del **terreno** incluye laderas sin calles: la mediana de Eibar es del 25,6 %. Para bici y patinete se usa ahora la pendiente de las **calles**: se muestrea el MDT en los vértices de las calles y vías ciclistas de OSM, en tramos de al menos 50 m, sin puentes ni túneles, y se toma la mediana ponderada por longitud. Eibar pasa a 7,25 %, Donostia a 1,07 % y Zarautz a 0,93 %. La pendiente del terreno (p90) se mantiene para el dron, porque mide lo abrupto del relieve.
- **Densidades sobre tierra.** Habitantes, edificios y comercios por km² se dividen por la parte del círculo cubierta por secciones censales de Gipuzkoa, y no por el círculo entero. Así el mar no diluye las densidades de la costa: en Donostia solo el 54,9 % del círculo es tierra.
- **Alternativa sin datos locales.** Sin `data/` se vuelve a Open-Meteo (malla de 375 m) y a los edificios de OSM, con una alerta de calidad.

## 3. Distribución de las métricas (18 zonas)

| Métrica | Mínimo | Mediana | Máximo |
|---|---:|---:|---:|
| Pendiente de calles, mediana % | 0,93 | 2,80 | 7,25 |
| Pendiente del terreno, p90 % | 12,75 | 28,68 | 53,83 |
| Cuota de infraestructura ciclista | 0,028 | 0,16 | 0,19 |
| Habitantes por km² de tierra | 1.261,5 | 3.563,9 | 14.469,9 |
| Comercios y servicios por km² de tierra | 7,5 | 51,9 | 460,9 |

## 4. Umbrales: antes y después

Criterio: ninguna característica puede quedar saturada (siempre 0 o siempre 1) en más del 80 % de las zonas. Si pasa, esa característica no distingue entre zonas.

| Umbral | Antes | Después | Motivo |
|---|---|---|---|
| `steepness_p90_pct` | [4, 12] | **[15, 50]** | Con el MDT, el p90 del terreno va de 12,75 a 53,83: el umbral anterior valía 1 en el **100 %** de las zonas |
| `pop_per_km2` (nuevo) | — | **[1000, 15000]** | Cubre el rango observado (1.261–14.470). El 1 corresponde a la densidad del centro de Donostia |
| `openness_pop_per_km2` (nuevo) | — | **[1000, 15000]** | El mismo rango, invertido: poca población = más espacio para el dron |
| `poi_per_km2` | [20, 300] | **[10, 400]** | Ahora se mide por km² de tierra y el máximo sube a 460,9. Con el rango anterior, el 22 % de las zonas quedaba en 0 y el 17 % en 1 |
| `slope_median_pct` (bici [3, 9]; patinete [2, 7]) | sin cambio | sin cambio | Ahora se aplican a la pendiente de las calles, que es lo que pretendían medir |
| `buildings_per_km2`, `openness_buildings_per_km2` | sin cambio | sin cambio | Solo se usan sin datos de Eustat |

Saturación sobre las mismas métricas reales (% de zonas en 0 / en 1), con los umbrales anteriores y con los nuevos:

| Característica | Antes | Después |
|---|---|---|
| steepness (dron) | 0 % / **100 %** | 6 % / 6 % |
| goods_demand | 22 % / 17 % | 11 % / 6 % |
| flatness (bici) | 0 % / 61 % | 0 % / 61 % |
| flatness (patinete) | 6 % / 33 % | 6 % / 33 % |
| density, infra, openness | 0 % / 0 % | 0 % / 0 % |

La planitud de la bici vale 1 en el 61 % de las zonas porque la mediana de pendiente de sus calles es inferior al 3 %. No se ha tocado: es un resultado físico, no un fallo del umbral, y queda por debajo del 80 %.

**Estos umbrales se han ajustado para que las métricas distingan entre zonas, no para acertar un resultado conocido.** Siguen siendo supuestos del equipo, no parámetros calibrados con datos de uso real.

## 5. Resultado y lectura crítica

- **Personas:** en las zonas llanas y densas (Donostia y sus barrios, Irun, Hernani), bici y patinete quedan casi empatados, con márgenes de 0,1 a 1,4 puntos y confianza "baja". Los pesos de los dos vehículos se parecen mucho, y el modelo no tiene información para separarlos (no hay datos de uso real). **La confianza baja es la respuesta correcta**, no un error. Eibar sale como "ningún vehículo adecuado" (17,2 puntos).
- **Bienes:** la bici gana con margen alto en Donostia y en la costa. El dron sale primero en los municipios de valle con relieve abrupto (Eibar, Tolosa, Arrasate, Pasaia, Azpeitia, Beasain), en varios casos con confianza media o baja. **Esto solo dice que el terreno favorece al dron frente a la bici.** No dice nada de la normativa (ENAIRE), que no se ha comprobado.

## 6. Pendiente

- Contrastar la infraestructura ciclista de OSM en Donostia con la capa de bidegorris municipal (`data/BIDEGORRIA/`).
- Consultar las zonas geográficas UAS de ENAIRE en las zonas donde sale el dron.
- La proporción de calles por encima del 6 % tiene un ruido de fondo de alrededor del 17 % incluso en zonas llanas (taludes y muros en un MDT de 25 m). Por eso el modelo usa la mediana y no esa proporción.

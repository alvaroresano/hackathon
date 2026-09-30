# Límites del sistema

Estos límites aparecen también en cada informe y los devuelve la herramienta `explain_method`.

## De los datos
1. **La zona es un círculo**, no el límite administrativo: se centra en el punto que devuelve Nominatim (radio por defecto 1.500 m), preferentemente el nodo del núcleo (`place`). Un municipio grande queda representado solo por su núcleo.
2. **Pendiente de calles aproximada:** se mide con el MDT LiDAR 2017 de 25 m (geoEuskadi) sobre tramos de ≥ 50 m de las calles de OSM. Muros, taludes y trincheras añaden ruido (en torno al 17 % de los tramos supera el 6 % incluso en zonas llanas), por eso se usa la mediana. Se excluyen puentes y túneles etiquetados; los no etiquetados pueden dar pendientes falsas. El MDT es de 2017.
3. **Agua:** los puntos con cota ≤ 0,5 m se tratan como agua (el MDT da 0 m en el mar). Un terreno real a esa cota (playas, marismas) también se excluye.
4. **Población repartida por área:** la población de cada sección censal (Eustat, 01/01/2025) se reparte en proporción al área que cae en el círculo, suponiendo que es uniforme dentro de la sección. La cifra es la población **del círculo**, no la del municipio.
5. **Solo Gipuzkoa:** la parte del círculo en Francia, Navarra o Bizkaia no tiene población ni cuenta como superficie (afecta sobre todo a Irun y Hondarribia). La capa de secciones es de 2026 y la población de 2025; una sección nueva de Irun no tiene población.
6. **OpenStreetMap es desigual:** la cobertura y el etiquetado del carril bici varían. "Cero km de infraestructura" puede ser real o una falta de etiquetado; el sistema lo avisa, pero no puede distinguirlo. Aún no se ha contrastado con la capa municipal de bidegorris.
7. **Proxies de demanda de reparto:** comercios y oficinas por km² no son pedidos. No hay datos de movilidad real por zona: la Encuesta de Movilidad 2021 solo da el reparto modal por territorio histórico (en Gipuzkoa, 42.131 de 1.919.297 desplazamientos diarios en bici, un 2,2 %).
8. **Datos consultados en una fecha:** OSM cambia; cada fuente lleva su fecha de consulta o de descarga (`data/fuentes.yaml`). La URL exacta de la tabla de población de Eustat está pendiente de anotar.

## Del modelo
9. **Pesos y umbrales heurísticos**, no calibrados con datos de uso. Los umbrales se ajustaron el 30-sep-2026 para que las métricas reales no se saturen (ver `docs/calibracion.md`), no para acertar un resultado. La sensibilidad solo prueba variaciones de pesos, no de umbrales.
10. **Puntuación ≠ probabilidad ni demanda.** Sirve para comparar zonas entre sí bajo los supuestos declarados.
11. **Bici y patinete casi empatan en zonas llanas y densas** (márgenes de 0,1 a 1,4 puntos): sus pesos son parecidos y no hay datos de uso que los separen. El sistema lo refleja con confianza baja.
12. **Drones:** la puntuación mide idoneidad geográfica. No se ha verificado normativa de espacio aéreo (AESA/ENAIRE), viento, ruido ni aceptación social.
13. **No modela** costes, tiempo de viaje, seguridad vial ni competencia entre modos.

## Del agente
14. **El modelo de lenguaje puede equivocarse al redactar.** La verificación de cifras detecta números sin respaldo, pero no valida el razonamiento ni la interpretación.
15. **Dependencia de servicios externos:** si una API falla o limita el uso, el agente lo informa y no rellena huecos. Con la caché poblada puede funcionar sin conexión.

## Qué se ha comprobado y qué no (30-sep-2026)
- **Comprobado:** consultas reales a Nominatim, Overpass, Open-Meteo, MDT y secciones censales; `analyze` completa las 18 zonas en los dos casos de uso; las 544 secciones de Gipuzkoa cruzan con la tabla de población (724.797 habitantes).
- **No comprobado:** el agente con un modelo de lenguaje real (el bucle se probó con un modelo simulado).
- **No comprobado:** la calidad de las recomendaciones frente a la realidad de cada zona; requiere revisión humana con conocimiento local.

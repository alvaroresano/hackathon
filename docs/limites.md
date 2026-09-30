# Límites del sistema

Estos límites aparecen también en cada informe y los devuelve la herramienta `explain_method`.

## De los datos
1. **La zona es un círculo**, no el límite administrativo: se centra en el punto que devuelve Nominatim (radio por defecto 1.500 m). Un municipio grande queda representado solo por su núcleo.
2. **Pendiente aproximada:** se estima con una malla de unos 375 m sobre un modelo digital de elevación de ~90 m. Infravalora pendientes locales de calle y puede verse afectada por la costa.
3. **OpenStreetMap es desigual:** la cobertura y el etiquetado del carril bici varían. "Cero km de infraestructura" puede ser real o una falta de etiquetado; el sistema lo avisa, pero no puede distinguirlo.
4. **Proxies de demanda:** edificios y comercios por km² no son población ni viajes. No se usan datos de población (Eustat), movilidad real (GTFS, aforos) ni turismo.
5. **Datos consultados en una fecha:** OSM cambia; cada fuente lleva su fecha de consulta.

## Del modelo
6. **Pesos y umbrales heurísticos**, no calibrados con datos de uso. Cambiarlos puede cambiar el resultado; la sensibilidad solo prueba variaciones de pesos, no de umbrales.
7. **Puntuación ≠ probabilidad ni demanda.** Sirve para comparar zonas entre sí bajo los supuestos declarados.
8. **Drones:** la puntuación mide idoneidad geográfica. No se ha verificado normativa de espacio aéreo (AESA/ENAIRE), viento, ruido ni aceptación social.
9. **No modela** costes, tiempo de viaje, seguridad vial ni competencia entre modos.

## Del agente
10. **El modelo de lenguaje puede equivocarse al redactar.** La verificación de cifras detecta números sin respaldo, pero no valida el razonamiento ni la interpretación.
11. **Dependencia de servicios externos:** si una API falla o limita el uso, el agente lo informa y no rellena huecos. Con la caché poblada puede funcionar sin conexión.

## Qué no ha sido comprobado (a fecha de entrega del borrador)
- Las consultas reales a Nominatim, Overpass y Open-Meteo (el entorno de desarrollo no tenía acceso a ellas): usar `python -m urbanagent doctor`.
- El agente con un modelo de lenguaje real (el bucle se probó con un modelo simulado).
- La calidad de las recomendaciones frente a la realidad de cada zona: requiere revisión humana con conocimiento local.

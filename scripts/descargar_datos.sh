#!/usr/bin/env bash
# Descarga a data/ los datos oficiales grandes que no se guardan en git.
# Uso: bash scripts/descargar_datos.sh   (desde la raíz del repositorio)
set -euo pipefail
cd "$(dirname "$0")/.."

MDT_URL="ftp://ftp.geo.euskadi.net/lidar/MDE/MAX_ACTUALIDAD/MDT_LIDAR_2017_ETRS89/mdt_lidar_2017_25m_etrs89.zip"
SECC_URL="https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/Unidades_estadisticas/SECCIONES_EUSTAT_5000_ETRS89.zip"

mkdir -p data/mdt25 data/secciones_eustat

if [ ! -f data/mdt25/mdt_lidar_2017_25m_etrs89.tif ]; then
  echo "Descargando MDT LiDAR 2017 de 25 m (geoEuskadi, ~41 MB)..."
  curl -fS --retry 3 -o data/mdt_lidar_2017_25m_etrs89.zip "$MDT_URL"
  unzip -o -q data/mdt_lidar_2017_25m_etrs89.zip -d data/mdt25
else
  echo "MDT ya presente."
fi

if [ ! -f data/secciones_eustat/SECCIONES_EUSTAT_5000_ETRS89.shp ]; then
  echo "Descargando secciones censales (geoEuskadi/Eustat, ~6 MB)..."
  curl -fS --retry 3 -o data/secciones_eustat/SECCIONES_EUSTAT_5000_ETRS89.zip "$SECC_URL"
  unzip -o -q data/secciones_eustat/SECCIONES_EUSTAT_5000_ETRS89.zip -d data/secciones_eustat
else
  echo "Secciones censales ya presentes."
fi

echo "Listo. La población por sección (data/xls0011434_c.csv) ya está en el repositorio."

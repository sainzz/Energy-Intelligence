# Energy Intelligence

Plataforma para cuantificar y predecir la reducción de generación renovable (curtailment) en el Sistema Eléctrico Nacional de Chile, con datos públicos.

Proyecto de portafolio local-first: todo se ejecuta en tu equipo, sin servicios de pago. Plan completo por sprints en el [tablero del proyecto](https://claude.ai/artifact/6fmYbTRprmtzYVUamqK97C).

## Estado

**Sprint 1, ingesta.** Descarga reproducible de los datos originales, manifiesto con SHA-256, informe de inspección y pruebas automáticas.

## Requisitos

- Python 3.12 o superior (desarrollado con 3.14)
- Git
- Unos 200 MB libres para los datos

## Instalación

```powershell
git clone https://github.com/sainzz/Energy-Intelligence.git
cd Energy-Intelligence
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

En Linux o macOS, usa `venv/bin/python` en lugar de `venv\Scripts\python.exe`.

## Obtener los datos desde cero

La carpeta `data/` no se versiona: se reconstruye con estos comandos. Se pueden ejecutar todas las veces que quieras; solo descargan lo que falta y nunca modifican lo ya descargado.

```powershell
# 1. Dataset de curtailment de Zenodo (4 Parquet, ~12 MB, menos de un minuto)
venv\Scripts\python.exe scripts\download_zenodo.py

# 2. Pronósticos meteorológicos archivados de Open-Meteo (~180 MB)
venv\Scripts\python.exe scripts\download_open_meteo.py
```

El paso 2 respeta el límite gratuito de Open-Meteo (10.000 llamadas ponderadas al día), así que **necesita dos ejecuciones en días distintos** para completarse. Termina con código de salida `2` mientras queden tramos pendientes y con `0` cuando está completo.

Cada descarga actualiza `data/raw/manifest.json`, con la ruta, fuente, fecha de descarga, tamaño y SHA-256 de cada archivo. Para verificar que ningún original cambió:

```powershell
venv\Scripts\python.exe scripts\build_manifest.py --check
```

## Informe de inspección

```powershell
venv\Scripts\python.exe scripts\inspect_raw.py
```

Describe esquema, filas, fechas, centrales, nulos y suma de curtailment, y lo guarda en [docs/reports/raw_inspection.md](docs/reports/raw_inspection.md).

## Pruebas

```powershell
venv\Scripts\python.exe -m pytest
```

Las pruebas no acceden a internet: usan respuestas HTTP simuladas y archivos temporales.

## Estructura

```
config/sources.toml        Fuentes de datos y parámetros de descarga
data/raw/                  Originales inmutables (fuera de Git)
docs/data_sources.md       Qué sirve de cada fuente y cómo se clasifica
docs/reports/              Informes generados
scripts/                   Puntos de entrada ejecutables
src/energy_intelligence/   Código del proyecto
  ingestion/               Descarga, escritura atómica y manifiesto
  validation/              Inspección de datos
tests/unit/                Pruebas automáticas
```

## Fuentes de datos

| Fuente | Qué aporta | Licencia |
|---|---|---|
| [Zenodo 10.5281/zenodo.21652187](https://doi.org/10.5281/zenodo.21652187) | Curtailment diario y horario por central, 2022-01 a 2026-05, y catálogo de 300 centrales. | CC BY 4.0. Reyes Cerda, P. y Cea Morales, K. (2026). |
| [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api) | Pronósticos archivados (modelo ECMWF IFS) de radiación, nubosidad, temperatura y viento. | Uso no comercial. Zippenfenig, P. (2023), doi:10.5281/zenodo.7970649. |
| API del Coordinador Eléctrico Nacional | Demanda, transmisión y costos marginales. Pendiente para el Sprint 2; requiere API key. | Información pública del CEN. |

Detalle de cada fuente, variables útiles y riesgos de fuga de información en [docs/data_sources.md](docs/data_sources.md).

## Secretos

Las credenciales van en un archivo `.env` en la raíz, que Git ignora. Nunca en el código.

```
CEN_API_KEY=tu_clave
```

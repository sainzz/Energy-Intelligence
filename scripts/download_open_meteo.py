"""Descarga a data/raw los pronósticos archivados de Open-Meteo definidos en config/sources.toml.

Uso, desde cualquier carpeta:
    venv\\Scripts\\python.exe scripts\\download_open_meteo.py [--limit N]

Se puede ejecutar varias veces: solo pide los tramos que faltan. Códigos de salida:
0 todo descargado, 1 algún tramo falló, 2 quedan tramos pendientes (límite diario).
"""

import argparse
import logging
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Hasta que el proyecto se empaquete con pyproject.toml, el paquete se importa desde src/.
sys.path.insert(0, str(ROOT / "src"))

from energy_intelligence.ingestion.http import build_session  # noqa: E402
from energy_intelligence.ingestion.open_meteo import download_all  # noqa: E402

logger = logging.getLogger("download_open_meteo")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="máximo de tramos a pedir en esta ejecución")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with (ROOT / "config" / "sources.toml").open("rb") as file:
        config = tomllib.load(file)["open_meteo"]

    # Sin reintentos ante 429: si Open-Meteo limita, se corta y se retoma después.
    session = build_session(retry_on_429=False)
    downloaded, existing, failed, remaining = download_all(session, config, ROOT, limit=args.limit)

    logger.info(
        "%d descargados, %d ya existían, %d fallidos, %d pendientes", downloaded, existing, failed, remaining
    )
    if failed:
        return 1
    return 2 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())

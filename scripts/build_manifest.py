"""Actualiza o verifica data/raw/manifest.json (SHA-256, tamaño, fuente y fecha de descarga).

Uso, desde cualquier carpeta:
    venv\\Scripts\\python.exe scripts\\build_manifest.py           # agrega archivos nuevos y verifica el resto
    venv\\Scripts\\python.exe scripts\\build_manifest.py --check   # solo verifica, no escribe

Devuelve código de salida 1 si algún archivo registrado cambió o desapareció.
"""

import argparse
import logging
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Hasta que el proyecto se empaquete con pyproject.toml, el paquete se importa desde src/.
sys.path.insert(0, str(ROOT / "src"))

from energy_intelligence.ingestion import manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="solo verificar, sin escribir el manifiesto")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with (ROOT / "config" / "sources.toml").open("rb") as file:
        config = tomllib.load(file)

    report = manifest.update(ROOT / "data" / "raw", manifest.sources_from_config(config), write=not args.check)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

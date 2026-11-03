"""Descarga a data/raw los archivos de Zenodo definidos en config/sources.toml.

Uso, desde cualquier carpeta:
    venv\\Scripts\\python.exe scripts\\download_zenodo.py

Devuelve código de salida 1 si algún archivo falla.
"""

import logging
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Hasta que el proyecto se empaquete con pyproject.toml, el paquete se importa desde src/.
sys.path.insert(0, str(ROOT / "src"))

from energy_intelligence.ingestion import manifest  # noqa: E402
from energy_intelligence.ingestion.zenodo import (  # noqa: E402
    DownloadError,
    build_session,
    download_file,
    fetch_record,
    select_files,
)

logger = logging.getLogger("download_zenodo")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with (ROOT / "config" / "sources.toml").open("rb") as file:
        all_config = tomllib.load(file)
    config = all_config["zenodo"]
    dest_dir = ROOT / config["dest_dir"]

    session = build_session()
    try:
        record = fetch_record(session, config["api_url"], config["record_id"])
        remote_files = select_files(record, config["files"])
    except DownloadError as exc:
        logger.error("%s", exc)
        return 1

    failures = 0
    for remote in remote_files:
        try:
            download_file(session, remote, dest_dir)
        except DownloadError as exc:
            logger.error("%s", exc)
            failures += 1

    logger.info("%d de %d archivos listos en %s", len(remote_files) - failures, len(remote_files), dest_dir)

    report = manifest.update(ROOT / "data" / "raw", manifest.sources_from_config(all_config))
    return 1 if failures or not report.ok else 0


if __name__ == "__main__":
    sys.exit(main())

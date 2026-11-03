"""Manifiesto de los archivos originales en ``data/raw``.

Registra por archivo su ruta, fuente, fecha de descarga, tamaño y SHA-256. Al
actualizarlo se recalcula el hash de cada archivo y se compara con el registrado:
un archivo ya registrado que cambió o desapareció se informa como problema y su
entrada no se reemplaza, porque los originales no deberían modificarse nunca.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from energy_intelligence.ingestion.http import write_atomic

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
CHUNK_SIZE = 1024 * 1024  # 1 MiB


@dataclass(frozen=True)
class Entry:
    path: str
    source: str
    downloaded_at: str
    size_bytes: int
    sha256: str


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.modified and not self.missing


def sha256_of(path: Path) -> str:
    """SHA-256 de un archivo, leído por bloques para no cargarlo entero en memoria."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(raw_dir: Path) -> dict[str, Entry]:
    path = raw_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["path"]: Entry(**item) for item in data["files"]}


def _raw_files(raw_dir: Path) -> list[Path]:
    """Archivos registrables: todo menos el propio manifiesto y descargas en curso."""
    return sorted(
        p for p in raw_dir.rglob("*")
        if p.is_file() and p.name != MANIFEST_NAME and not p.name.endswith(".part")
    )


def sources_from_config(config: dict, raw_dir: str = "data/raw") -> dict[str, str]:
    """Prefijos de ruta de cada fuente, a partir de ``config/sources.toml``."""

    def prefix(dest_dir: str) -> str:
        return Path(dest_dir).relative_to(raw_dir).as_posix()

    zenodo = config["zenodo"]
    open_meteo = config["open_meteo"]
    return {
        prefix(zenodo["dest_dir"]): f"zenodo:{zenodo['record_id']}",
        f"{prefix(open_meteo['dest_dir'])}/{open_meteo['model']}": (
            f"open-meteo:historical-forecast:{open_meteo['model']}"
        ),
    }


def _source_for(relative: str, sources: dict[str, str]) -> str:
    """La fuente cuyo prefijo de ruta más largo coincide con ``relative``."""
    matches = [prefix for prefix in sources if relative == prefix or relative.startswith(prefix + "/")]
    return sources[max(matches, key=len)] if matches else "desconocida"


def update(raw_dir: Path, sources: dict[str, str], write: bool = True) -> Report:
    """Compara ``data/raw`` con el manifiesto y agrega los archivos nuevos.

    ``sources`` relaciona prefijos de ruta (relativos a ``raw_dir``) con el nombre
    de su fuente. Con ``write=False`` solo verifica, sin tocar el manifiesto.
    """
    previous = load(raw_dir)
    current: dict[str, Entry] = {}
    report = Report()

    for path in _raw_files(raw_dir):
        relative = path.relative_to(raw_dir).as_posix()
        digest = sha256_of(path)
        size = path.stat().st_size
        known = previous.get(relative)

        if known is None:
            # La fecha de modificación del archivo es la de su descarga: la ingesta escribe una sola vez.
            downloaded_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            current[relative] = Entry(
                path=relative,
                source=_source_for(relative, sources),
                downloaded_at=downloaded_at.isoformat(timespec="seconds"),
                size_bytes=size,
                sha256=digest,
            )
            report.added.append(relative)
        elif known.sha256 == digest and known.size_bytes == size:
            current[relative] = known
            report.unchanged.append(relative)
        else:
            current[relative] = known  # se conserva el registro original como evidencia
            report.modified.append(relative)
            logger.error("%s cambió desde que se registró (sha256 %s, antes %s)", relative, digest, known.sha256)

    for relative, known in previous.items():
        if relative not in current:
            current[relative] = known
            report.missing.append(relative)
            logger.error("%s está en el manifiesto pero ya no existe", relative)

    if write and report.added:
        payload = {
            "description": "Archivos originales de data/raw. No se modifican; se regeneran desde la fuente.",
            "files": [asdict(current[key]) for key in sorted(current)],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        write_atomic(raw_dir / MANIFEST_NAME, content.encode("utf-8"))

    logger.info(
        "Manifiesto: %d nuevos, %d sin cambios, %d modificados, %d faltantes",
        len(report.added), len(report.unchanged), len(report.modified), len(report.missing),
    )
    return report

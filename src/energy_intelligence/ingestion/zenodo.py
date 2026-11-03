"""Descarga de archivos publicados en un registro de Zenodo.

Cada archivo se verifica contra el checksum MD5 que publica Zenodo. La descarga
se escribe en un archivo temporal ``.part`` y solo se renombra al nombre final
cuando el tamaño y el checksum coinciden, así un corte nunca deja un archivo
a medias en ``data/raw``. Los archivos que ya existen no se sobrescriben.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import requests

from energy_intelligence.ingestion.http import TIMEOUT, build_session

__all__ = ["build_session"]

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB


class DownloadError(Exception):
    """La descarga o la verificación de un archivo falló."""


class DownloadStatus(Enum):
    DOWNLOADED = "descargado"
    SKIPPED = "ya existía y es válido"


@dataclass(frozen=True)
class RemoteFile:
    name: str
    url: str
    size: int
    md5: str


def fetch_record(session: requests.Session, api_url: str, record_id: str) -> dict:
    """Obtiene los metadatos del registro desde la API de Zenodo."""
    url = f"{api_url.rstrip('/')}/{record_id}"
    try:
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DownloadError(f"No se pudo obtener el registro {record_id}: {exc}") from exc
    return response.json()


def _file_entries(record: dict) -> dict[str, dict]:
    """Normaliza la lista de archivos a ``{nombre: entrada}``.

    La API pública (``/api/records/<id>``) entrega ``files`` como lista y el enlace
    de descarga en ``links.self``; el JSON que exporta la web de Zenodo usa
    ``files.entries`` y ``links.content``. Se aceptan ambos formatos.
    """
    files = record.get("files", [])
    if isinstance(files, dict):
        files = list(files.get("entries", {}).values())
    return {
        entry["key"]: {
            "url": entry["links"].get("content") or entry["links"]["self"],
            "size": entry["size"],
            "checksum": entry["checksum"],
        }
        for entry in files
    }


def select_files(record: dict, names: list[str]) -> list[RemoteFile]:
    """Busca en el registro los archivos pedidos y extrae URL, tamaño y MD5."""
    entries = _file_entries(record)
    missing = [name for name in names if name not in entries]
    if missing:
        raise DownloadError(f"El registro {record.get('id')} no contiene: {', '.join(missing)}")

    selected = []
    for name in names:
        entry = entries[name]
        algorithm, _, digest = entry["checksum"].partition(":")
        if algorithm != "md5":
            raise DownloadError(f"{name}: checksum '{algorithm}' no soportado")
        selected.append(RemoteFile(name=name, url=entry["url"], size=entry["size"], md5=digest))
    return selected


def md5_of(path: Path) -> str:
    """MD5 de un archivo, leído por bloques para no cargarlo entero en memoria."""
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(session: requests.Session, remote: RemoteFile, dest_dir: Path) -> DownloadStatus:
    """Descarga ``remote`` a ``dest_dir`` si no existe ya una copia válida."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / remote.name

    if target.exists():
        if md5_of(target) == remote.md5:
            logger.info("%s: %s", remote.name, DownloadStatus.SKIPPED.value)
            return DownloadStatus.SKIPPED
        # No se sobrescribe un original: alguien debe revisar por qué cambió.
        raise DownloadError(
            f"{target} existe pero su MD5 no coincide con Zenodo; no se sobrescribe"
        )

    partial = target.with_name(target.name + ".part")
    digest = hashlib.md5()
    written = 0
    try:
        with session.get(remote.url, stream=True, timeout=TIMEOUT) as response:
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    file.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
    except (requests.RequestException, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"{remote.name}: falló la descarga: {exc}") from exc

    if written != remote.size or digest.hexdigest() != remote.md5:
        partial.unlink(missing_ok=True)
        raise DownloadError(
            f"{remote.name}: archivo incompleto o corrupto "
            f"({written} de {remote.size} bytes, md5 {digest.hexdigest()})"
        )

    os.replace(partial, target)
    logger.info("%s: %s (%d bytes)", remote.name, DownloadStatus.DOWNLOADED.value, written)
    return DownloadStatus.DOWNLOADED

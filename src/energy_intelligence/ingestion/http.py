"""Utilidades HTTP y de escritura compartidas por los módulos de ingesta."""

from __future__ import annotations

import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT = (10, 60)  # segundos: conexión, lectura entre bloques


def build_session(retries: int = 3, retry_on_429: bool = True) -> requests.Session:
    """Sesión HTTP que reintenta ante errores transitorios del servidor."""
    statuses = (500, 502, 503, 504) + ((429,) if retry_on_429 else ())
    retry = Retry(
        total=retries,
        backoff_factor=1,
        status_forcelist=statuses,
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def write_atomic(target: Path, content: bytes) -> None:
    """Escribe en un ``.part`` y lo renombra: nunca queda un archivo a medias."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        partial.write_bytes(content)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)

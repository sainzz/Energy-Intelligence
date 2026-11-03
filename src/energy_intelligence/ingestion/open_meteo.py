"""Descarga de pronósticos archivados de Open-Meteo por celda de grilla.

Cada consulta cubre una celda y un año calendario, y su respuesta se guarda tal
cual en ``data/raw`` (un JSON por celda y año). Si el archivo ya existe no se
vuelve a pedir, así una ejecución cortada por el límite diario se retoma donde
quedó.

Open-Meteo cobra llamadas "ponderadas": una consulta de más de 14 días o más de
10 variables cuenta como varias. El ritmo de descarga se ajusta a ese peso.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import requests

from energy_intelligence.ingestion.http import TIMEOUT, write_atomic

logger = logging.getLogger(__name__)


class OpenMeteoError(Exception):
    """Una consulta falló o devolvió datos inválidos."""


class QuotaExceeded(OpenMeteoError):
    """Open-Meteo respondió 429: hay que esperar y retomar más tarde."""


@dataclass(frozen=True)
class Cell:
    cell_id: str
    latitude: float
    longitude: float
    plants: tuple[str, ...]


@dataclass(frozen=True)
class Chunk:
    cell: Cell
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def filename(self) -> str:
        return f"{self.start.isoformat()}_{self.end.isoformat()}.json"


def call_weight(days: int, n_variables: int) -> float:
    """Llamadas ponderadas que Open-Meteo cuenta para una ubicación."""
    return max(1.0, days / 14) * max(1.0, n_variables / 10)


def build_cells(
    metadata_path: Path, plants_path: Path, technologies: list[str], resolution: float
) -> list[Cell]:
    """Agrupa las centrales de ``technologies`` por celda redondeada a ``resolution``."""
    technology = {
        row["central_codigo"]: row["tecnologia"]
        for row in pq.read_table(plants_path, columns=["central_codigo", "tecnologia"]).to_pylist()
    }
    metadata = pq.read_table(
        metadata_path, columns=["central_codigo", "latitud", "longitud"]
    ).to_pylist()

    grouped: dict[tuple[float, float], list[str]] = {}
    for row in metadata:
        if technology.get(row["central_codigo"]) not in technologies:
            continue
        if row["latitud"] is None or row["longitud"] is None:
            logger.warning("%s no tiene coordenadas; se omite", row["central_codigo"])
            continue
        key = (_snap(row["latitud"], resolution), _snap(row["longitud"], resolution))
        grouped.setdefault(key, []).append(row["central_codigo"])

    return [
        Cell(cell_id=f"lat{lat:.2f}_lon{lon:.2f}", latitude=lat, longitude=lon, plants=tuple(sorted(codes)))
        for (lat, lon), codes in sorted(grouped.items())
    ]


def _snap(value: float, resolution: float) -> float:
    return round(round(value / resolution) * resolution, 4)


def yearly_chunks(cell: Cell, start: date, end: date) -> list[Chunk]:
    """Divide ``[start, end]`` en tramos por año calendario."""
    chunks = []
    current = start
    while current <= end:
        year_end = min(date(current.year, 12, 31), end)
        chunks.append(Chunk(cell, current, year_end))
        current = year_end + timedelta(days=1)
    return chunks


def write_locations(cells: list[Cell], target: Path) -> None:
    """Guarda qué centrales quedaron en cada celda, para cruzar los datos después."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["cell_id", "latitude", "longitude", "central_codigo"])
    for cell in cells:
        for code in cell.plants:
            writer.writerow([cell.cell_id, cell.latitude, cell.longitude, code])
    content = buffer.getvalue().encode("utf-8")
    if not target.exists() or target.read_bytes() != content:
        write_atomic(target, content)


def fetch_chunk(
    session: requests.Session,
    api_url: str,
    chunk: Chunk,
    model: str,
    hourly: list[str],
    wind_speed_unit: str,
) -> bytes:
    """Pide un tramo a la API y valida la respuesta antes de devolverla."""
    params = {
        "latitude": chunk.cell.latitude,
        "longitude": chunk.cell.longitude,
        "start_date": chunk.start.isoformat(),
        "end_date": chunk.end.isoformat(),
        "hourly": ",".join(hourly),
        "models": model,
        "timeformat": "unixtime",  # UTC: el parámetro timezone ignora el horario de verano
        "wind_speed_unit": wind_speed_unit,
    }
    try:
        response = session.get(api_url, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise OpenMeteoError(f"{chunk.cell.cell_id} {chunk.filename()}: {exc}") from exc

    if response.status_code == 429:
        raise QuotaExceeded(response.text[:200])
    if not response.ok:
        raise OpenMeteoError(
            f"{chunk.cell.cell_id} {chunk.filename()}: HTTP {response.status_code} {response.text[:200]}"
        )

    payload = response.json()
    times = payload.get("hourly", {}).get("time", [])
    expected = chunk.days * 24
    if len(times) != expected:
        raise OpenMeteoError(
            f"{chunk.cell.cell_id} {chunk.filename()}: {len(times)} horas, se esperaban {expected}"
        )
    missing = [name for name in hourly if name not in payload["hourly"]]
    if missing:
        raise OpenMeteoError(f"{chunk.cell.cell_id} {chunk.filename()}: faltan {', '.join(missing)}")
    return response.content


def download_all(
    session: requests.Session,
    config: dict,
    root: Path,
    limit: int | None = None,
    sleep=time.sleep,
) -> tuple[int, int, int, int]:
    """Descarga los tramos que faltan.

    Devuelve (descargados, ya existentes, fallidos, pendientes). ``limit`` acota
    cuántos tramos se piden en esta ejecución, útil para probar.
    """
    dest_dir = root / config["dest_dir"] / config["model"]
    cells = build_cells(
        root / config["plants_metadata"],
        root / config["plants"],
        config["technologies"],
        config["grid_resolution_deg"],
    )
    write_locations(cells, dest_dir / "locations.csv")

    start = date.fromisoformat(config["start_date"])
    end = date.fromisoformat(config["end_date"])
    chunks = [chunk for cell in cells for chunk in yearly_chunks(cell, start, end)]
    pending = [c for c in chunks if not (dest_dir / c.cell.cell_id / c.filename()).exists()]
    logger.info(
        "%d celdas, %d tramos: %d ya descargados, %d pendientes",
        len(cells), len(chunks), len(chunks) - len(pending), len(pending),
    )

    n_vars = len(config["hourly"])
    seconds_per_call = 3600 / config["hourly_budget"]
    spent = 0.0
    downloaded = failed = 0
    for index, chunk in enumerate(pending[:limit], start=1):
        weight = call_weight(chunk.days, n_vars)
        if spent + weight > config["run_budget"]:
            logger.warning("Se alcanzó el presupuesto de %s llamadas; ejecuta de nuevo mañana", config["run_budget"])
            break
        try:
            content = fetch_chunk(
                session, config["api_url"], chunk, config["model"], config["hourly"], config["wind_speed_unit"]
            )
        except QuotaExceeded as exc:
            logger.warning("Open-Meteo limitó las consultas (429): %s. Ejecuta de nuevo más tarde", exc)
            break
        except OpenMeteoError as exc:
            logger.error("%s", exc)
            failed += 1
        else:
            write_atomic(dest_dir / chunk.cell.cell_id / chunk.filename(), content)
            downloaded += 1
            logger.info(
                "[%d/%d] %s %s (%.0f llamadas ponderadas)",
                index, len(pending), chunk.cell.cell_id, chunk.filename(), weight,
            )
        spent += weight
        sleep(math.ceil(weight * seconds_per_call))

    remaining = len(pending) - downloaded
    return downloaded, len(chunks) - len(pending), failed, remaining

"""Inspección básica de los Parquet originales: esquema, volumen, rangos y nulos.

Solo describe los datos; no los corrige. Lo que se encuentre aquí alimenta las
reglas de calidad del Sprint 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


@dataclass
class ColumnProfile:
    name: str
    type: str
    null_pct: float
    distinct: int | None = None
    minimum: object = None
    maximum: object = None


@dataclass
class TableProfile:
    name: str
    rows: int
    columns: list[ColumnProfile] = field(default_factory=list)


def profile_table(name: str, table: pa.Table) -> TableProfile:
    """Tipos, % de nulos y rango (fechas y números) o cardinalidad (texto) por columna."""
    profile = TableProfile(name=name, rows=table.num_rows)
    for column_name in table.column_names:
        column = table[column_name]
        null_pct = 100 * column.null_count / table.num_rows if table.num_rows else 0.0
        col = ColumnProfile(name=column_name, type=str(column.type), null_pct=null_pct)
        if pa.types.is_temporal(column.type) or pa.types.is_integer(column.type) or pa.types.is_floating(column.type):
            bounds = pc.min_max(column)
            col.minimum, col.maximum = bounds["min"].as_py(), bounds["max"].as_py()
        if pa.types.is_string(column.type) or pa.types.is_integer(column.type):
            col.distinct = pc.count_distinct(column, mode="only_valid").as_py()
        profile.columns.append(col)
    return profile


@dataclass
class CurtailmentChecks:
    """Indicadores para confirmar la unidad de ``mwh`` y contrastar con lo publicado."""

    name: str
    total_mwh: float
    zero_pct: float
    plants: int
    plant_technology_pairs: int
    # Máximo de mwh diario / (potencia_mw * 24). Si la unidad fuera kWh rondaría 1.000;
    # un valor sobre 1 en MWh es físicamente imposible y apunta a una potencia mal emparejada.
    max_daily_ratio: float | None
    over_capacity: list[dict] = field(default_factory=list)


def curtailment_checks(name: str, table: pa.Table, metadata: pa.Table | None = None) -> CurtailmentChecks:
    mwh = table["mwh"]
    pairs = pa.table({"c": table["central_codigo"], "t": table["tecnologia"]}).group_by(["c", "t"]).aggregate([])

    ratio = None
    over_capacity: list[dict] = []
    if metadata is not None:
        daily = table.group_by(["fecha", "central_codigo"]).aggregate([("mwh", "sum")])
        joined = daily.join(
            metadata.select(["central_codigo", "potencia_mw", "match_metodo"]), "central_codigo"
        )
        valid = joined.filter(pc.greater(joined["potencia_mw"], 0))
        valid = valid.append_column(
            "ratio", pc.divide(valid["mwh_sum"], pc.multiply(valid["potencia_mw"], 24))
        )
        ratio = pc.max(valid["ratio"]).as_py()
        over = (
            valid.filter(pc.greater(valid["ratio"], 1))
            .group_by(["central_codigo", "potencia_mw", "match_metodo"])
            .aggregate([("mwh_sum", "max"), ("ratio", "max"), ("fecha", "count")])
            .sort_by([("ratio_max", "descending")])
        )
        over_capacity = over.to_pylist()

    return CurtailmentChecks(
        name=name,
        total_mwh=pc.sum(mwh).as_py(),
        zero_pct=100 * pc.sum(pc.equal(mwh, 0)).as_py() / table.num_rows,
        plants=pc.count_distinct(table["central_codigo"]).as_py(),
        plant_technology_pairs=pairs.num_rows,
        max_daily_ratio=ratio,
        over_capacity=over_capacity,
    )


def read(path: Path) -> pa.Table:
    return pq.read_table(path)


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def render_markdown(profiles: list[TableProfile], checks: list[CurtailmentChecks], published_daily_mwh: float) -> str:
    lines = ["# Inspección de datos originales (Zenodo)", ""]
    lines.append("Generado por `scripts/inspect_raw.py`. Solo describe los datos; no los corrige.")
    lines.append("")
    for profile in profiles:
        lines += [f"## {profile.name}", "", f"{profile.rows:,} filas · {len(profile.columns)} columnas", ""]
        lines.append("| columna | tipo | % nulos | distintos | mínimo | máximo |")
        lines.append("|---|---|---:|---:|---|---|")
        for col in profile.columns:
            lines.append(
                f"| {col.name} | {col.type} | {col.null_pct:.2f} | {_fmt(col.distinct)} "
                f"| {_fmt(col.minimum)} | {_fmt(col.maximum)} |"
            )
        lines.append("")

    lines += ["## Curtailment: unidad y contraste con lo publicado", ""]
    lines.append("| tabla | suma mwh | % filas en cero | centrales | pares central-tecnología | máx. diario / (potencia × 24 h) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for check in checks:
        lines.append(
            f"| {check.name} | {check.total_mwh:,.2f} | {check.zero_pct:.1f} | {check.plants} "
            f"| {check.plant_technology_pairs} | {_fmt(check.max_daily_ratio)} |"
        )
    lines.append("")
    daily = next(c for c in checks if c.name == "curtailment_daily")
    diff = daily.total_mwh - published_daily_mwh
    lines.append(
        f"- Suma diaria publicada en el diccionario: {published_daily_mwh:,.2f} MWh. "
        f"Diferencia con la calculada: {diff:,.2f} MWh."
    )
    lines.append(
        "- Unidad: si `mwh` estuviera en kWh, el cociente contra la capacidad instalada rondaría 1.000. "
        f"El máximo es {daily.max_daily_ratio:,.2f}, lo que confirma que la unidad es MWh."
    )
    if daily.over_capacity:
        lines += [
            f"- Hay {len(daily.over_capacity)} centrales con días en que el curtailment supera su potencia × 24 h, "
            "algo físicamente imposible. Lo más probable es que la potencia del catálogo no corresponda "
            "a la unidad que reporta el CEN. Hay que revisarlo en el Sprint 2.",
            "",
            "| central | potencia_mw | match_metodo | días sobre capacidad | máx. mwh diario | máx. cociente |",
            "|---|---:|---|---:|---:|---:|",
        ]
        for row in daily.over_capacity:
            lines.append(
                f"| {row['central_codigo']} | {row['potencia_mw']:,.2f} | {row['match_metodo']} "
                f"| {row['fecha_count']} | {row['mwh_sum_max']:,.2f} | {row['ratio_max']:,.2f} |"
            )
    lines.append("")
    return "\n".join(lines)

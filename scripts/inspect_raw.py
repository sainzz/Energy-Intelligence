"""Informe básico de los Parquet de Zenodo: esquema, filas, fechas, centrales, nulos y suma de curtailment.

Uso, desde cualquier carpeta:
    venv\\Scripts\\python.exe scripts\\inspect_raw.py

Muestra el informe en pantalla y lo guarda en docs/reports/raw_inspection.md.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Hasta que el proyecto se empaquete con pyproject.toml, el paquete se importa desde src/.
sys.path.insert(0, str(ROOT / "src"))

from energy_intelligence.validation import inspection  # noqa: E402

# Suma total de curtailment_daily según data_dictionary.md del dataset v1.1.
PUBLISHED_DAILY_MWH = 19_030_463.14
REPORT_PATH = ROOT / "docs" / "reports" / "raw_inspection.md"


def main() -> int:
    with (ROOT / "config" / "sources.toml").open("rb") as file:
        raw_dir = ROOT / tomllib.load(file)["zenodo"]["dest_dir"]

    tables = {
        name: inspection.read(raw_dir / f"{name}.parquet")
        for name in ("curtailment_daily", "curtailment_hourly", "plants", "plants_metadata")
    }
    profiles = [inspection.profile_table(name, table) for name, table in tables.items()]
    checks = [
        inspection.curtailment_checks(name, tables[name], tables["plants_metadata"])
        for name in ("curtailment_daily", "curtailment_hourly")
    ]

    report = inspection.render_markdown(profiles, checks, PUBLISHED_DAILY_MWH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Informe guardado en {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

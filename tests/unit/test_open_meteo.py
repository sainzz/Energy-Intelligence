import json
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from conftest import FakeResponse
from energy_intelligence.ingestion.open_meteo import (
    Cell,
    Chunk,
    OpenMeteoError,
    QuotaExceeded,
    build_cells,
    call_weight,
    download_all,
    fetch_chunk,
    yearly_chunks,
)

HOURLY = ["shortwave_radiation", "wind_speed_100m"]
CELL = Cell("lat-23.70_lon-70.40", -23.7, -70.4, ("PFV-A",))


def payload(days, variables=HOURLY):
    hours = days * 24
    data = {"time": list(range(hours))} | {name: [0.0] * hours for name in variables}
    return json.dumps({"hourly": data}).encode()


def test_call_weight_follows_open_meteo_rules():
    assert call_weight(days=7, n_variables=5) == 1
    assert call_weight(days=28, n_variables=10) == 2
    assert call_weight(days=14, n_variables=15) == 1.5


def test_yearly_chunks_split_on_calendar_years():
    chunks = yearly_chunks(CELL, date(2022, 6, 1), date(2024, 1, 15))

    assert [(c.start, c.end) for c in chunks] == [
        (date(2022, 6, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 1, 15)),
    ]


def test_build_cells_groups_nearby_plants_and_filters_technology(tmp_path):
    pq.write_table(
        pa.table({
            "central_codigo": ["PFV-A", "PFV-B", "PE-C", "HP-D"],
            "tecnologia": ["Solar", "Solar", "Eólica", "Hidro Pasada"],
        }),
        tmp_path / "plants.parquet",
    )
    pq.write_table(
        pa.table({
            "central_codigo": ["PFV-A", "PFV-B", "PE-C", "HP-D"],
            "latitud": [-23.71, -23.69, -30.0, -35.0],
            "longitud": [-70.41, -70.39, -71.5, -71.0],
        }),
        tmp_path / "meta.parquet",
    )

    cells = build_cells(tmp_path / "meta.parquet", tmp_path / "plants.parquet", ["Solar", "Eólica"], 0.1)

    assert [(c.cell_id, c.plants) for c in cells] == [
        ("lat-30.00_lon-71.50", ("PE-C",)),
        ("lat-23.70_lon-70.40", ("PFV-A", "PFV-B")),
    ]


class TestFetchChunk:
    chunk = Chunk(CELL, date(2022, 1, 1), date(2022, 1, 2))

    def test_valid_response_is_returned_as_is(self, fake_session):
        body = payload(days=2)
        session = fake_session(FakeResponse(content=body))

        assert fetch_chunk(session, "https://api.test", self.chunk, "ecmwf_ifs", HOURLY, "ms") == body
        params = session.calls[0][1]["params"]
        assert params["timeformat"] == "unixtime"
        assert params["models"] == "ecmwf_ifs"

    def test_missing_hours_are_rejected(self, fake_session):
        session = fake_session(FakeResponse(content=payload(days=1)))

        with pytest.raises(OpenMeteoError, match="se esperaban 48"):
            fetch_chunk(session, "https://api.test", self.chunk, "ecmwf_ifs", HOURLY, "ms")

    def test_missing_variable_is_rejected(self, fake_session):
        session = fake_session(FakeResponse(content=payload(days=2, variables=HOURLY[:1])))

        with pytest.raises(OpenMeteoError, match="faltan wind_speed_100m"):
            fetch_chunk(session, "https://api.test", self.chunk, "ecmwf_ifs", HOURLY, "ms")

    def test_rate_limit_raises_quota_exceeded(self, fake_session):
        session = fake_session(FakeResponse(status_code=429, content=b"limit"))

        with pytest.raises(QuotaExceeded):
            fetch_chunk(session, "https://api.test", self.chunk, "ecmwf_ifs", HOURLY, "ms")


@pytest.fixture
def project(tmp_path):
    """Proyecto mínimo con una central solar y la configuración de Open-Meteo."""
    zenodo = tmp_path / "data" / "raw" / "zenodo"
    zenodo.mkdir(parents=True)
    pq.write_table(pa.table({"central_codigo": ["PFV-A"], "tecnologia": ["Solar"]}), zenodo / "plants.parquet")
    pq.write_table(
        pa.table({"central_codigo": ["PFV-A"], "latitud": [-23.7], "longitud": [-70.4]}),
        zenodo / "plants_metadata.parquet",
    )
    config = {
        "api_url": "https://api.test",
        "model": "ecmwf_ifs",
        "dest_dir": "data/raw/open_meteo/historical_forecast",
        "plants_metadata": "data/raw/zenodo/plants_metadata.parquet",
        "plants": "data/raw/zenodo/plants.parquet",
        "technologies": ["Solar"],
        "grid_resolution_deg": 0.1,
        "start_date": "2022-12-31",
        "end_date": "2023-01-01",
        "hourly": HOURLY,
        "wind_speed_unit": "ms",
        "hourly_budget": 3600,
        "run_budget": 100,
    }
    return tmp_path, config


def test_download_all_resumes_without_repeating(project, fake_session):
    root, config = project
    first = fake_session(FakeResponse(content=payload(days=1)), FakeResponse(content=payload(days=1)))

    assert download_all(first, config, root, sleep=lambda s: None) == (2, 0, 0, 0)

    second = fake_session()  # cualquier llamada HTTP haría fallar la prueba
    assert download_all(second, config, root, sleep=lambda s: None) == (0, 2, 0, 0)
    assert second.calls == []


def test_download_all_stops_on_quota_and_keeps_progress(project, fake_session):
    root, config = project
    session = fake_session(FakeResponse(content=payload(days=1)), FakeResponse(status_code=429))

    downloaded, existing, failed, remaining = download_all(session, config, root, sleep=lambda s: None)

    assert (downloaded, failed, remaining) == (1, 0, 1)
    cell_dir = root / config["dest_dir"] / "ecmwf_ifs" / "lat-23.70_lon-70.40"
    assert [p.name for p in cell_dir.iterdir()] == ["2022-12-31_2022-12-31.json"]

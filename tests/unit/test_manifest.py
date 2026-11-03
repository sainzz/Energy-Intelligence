import hashlib
import json

from energy_intelligence.ingestion import manifest

SOURCES = {"zenodo": "zenodo:1", "open_meteo/historical_forecast/ecmwf_ifs": "open-meteo:ifs"}


def make_raw(tmp_path):
    raw = tmp_path / "raw"
    (raw / "zenodo").mkdir(parents=True)
    (raw / "zenodo" / "a.parquet").write_bytes(b"aaa")
    (raw / "open_meteo" / "historical_forecast" / "ecmwf_ifs" / "cell").mkdir(parents=True)
    (raw / "open_meteo" / "historical_forecast" / "ecmwf_ifs" / "cell" / "2022.json").write_bytes(b"{}")
    return raw


def test_first_run_registers_every_file(tmp_path):
    raw = make_raw(tmp_path)

    report = manifest.update(raw, SOURCES)

    assert sorted(report.added) == [
        "open_meteo/historical_forecast/ecmwf_ifs/cell/2022.json",
        "zenodo/a.parquet",
    ]
    entries = manifest.load(raw)
    assert entries["zenodo/a.parquet"].sha256 == hashlib.sha256(b"aaa").hexdigest()
    assert entries["zenodo/a.parquet"].size_bytes == 3
    assert entries["zenodo/a.parquet"].source == "zenodo:1"
    assert entries["open_meteo/historical_forecast/ecmwf_ifs/cell/2022.json"].source == "open-meteo:ifs"


def test_second_run_does_not_duplicate_or_rewrite(tmp_path):
    raw = make_raw(tmp_path)
    manifest.update(raw, SOURCES)
    before = (raw / manifest.MANIFEST_NAME).read_bytes()

    report = manifest.update(raw, SOURCES)

    assert report.added == []
    assert len(report.unchanged) == 2
    assert (raw / manifest.MANIFEST_NAME).read_bytes() == before
    assert len(json.loads(before)["files"]) == 2


def test_new_file_is_appended(tmp_path):
    raw = make_raw(tmp_path)
    manifest.update(raw, SOURCES)
    (raw / "zenodo" / "b.parquet").write_bytes(b"bbb")

    report = manifest.update(raw, SOURCES)

    assert report.added == ["zenodo/b.parquet"]
    assert len(manifest.load(raw)) == 3


def test_altered_file_is_reported_and_original_entry_kept(tmp_path):
    raw = make_raw(tmp_path)
    manifest.update(raw, SOURCES)
    original = manifest.load(raw)["zenodo/a.parquet"]
    (raw / "zenodo" / "a.parquet").write_bytes(b"modificado")

    report = manifest.update(raw, SOURCES)

    assert report.modified == ["zenodo/a.parquet"]
    assert not report.ok
    assert manifest.load(raw)["zenodo/a.parquet"] == original


def test_deleted_file_is_reported_as_missing(tmp_path):
    raw = make_raw(tmp_path)
    manifest.update(raw, SOURCES)
    (raw / "zenodo" / "a.parquet").unlink()

    report = manifest.update(raw, SOURCES)

    assert report.missing == ["zenodo/a.parquet"]
    assert not report.ok


def test_partial_downloads_are_ignored(tmp_path):
    raw = make_raw(tmp_path)
    (raw / "zenodo" / "c.parquet.part").write_bytes(b"a medias")

    report = manifest.update(raw, SOURCES)

    assert "zenodo/c.parquet.part" not in report.added


def test_check_mode_does_not_write(tmp_path):
    raw = make_raw(tmp_path)

    manifest.update(raw, SOURCES, write=False)

    assert not (raw / manifest.MANIFEST_NAME).exists()


def test_sources_from_config():
    config = {
        "zenodo": {"dest_dir": "data/raw/zenodo", "record_id": "123"},
        "open_meteo": {"dest_dir": "data/raw/open_meteo/historical_forecast", "model": "ecmwf_ifs"},
    }

    assert manifest.sources_from_config(config) == {
        "zenodo": "zenodo:123",
        "open_meteo/historical_forecast/ecmwf_ifs": "open-meteo:historical-forecast:ecmwf_ifs",
    }

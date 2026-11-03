import hashlib

import pytest

from conftest import FakeResponse
from energy_intelligence.ingestion.zenodo import (
    DownloadError,
    DownloadStatus,
    RemoteFile,
    download_file,
    select_files,
)

CONTENT = b"datos de prueba" * 1000


def remote(content=CONTENT, name="tabla.parquet"):
    return RemoteFile(
        name=name,
        url=f"https://zenodo.test/{name}",
        size=len(content),
        md5=hashlib.md5(content).hexdigest(),
    )


def entry(key, url_key="self"):
    return {"key": key, "size": 10, "checksum": "md5:abc", "links": {url_key: f"https://zenodo.test/{key}"}}


class TestSelectFiles:
    def test_api_format_list(self):
        record = {"id": "1", "files": [entry("a.parquet"), entry("b.csv")]}
        [selected] = select_files(record, ["a.parquet"])
        assert selected == RemoteFile("a.parquet", "https://zenodo.test/a.parquet", 10, "abc")

    def test_web_export_format_entries(self):
        record = {"id": "1", "files": {"entries": {"a.parquet": entry("a.parquet", url_key="content")}}}
        [selected] = select_files(record, ["a.parquet"])
        assert selected.url == "https://zenodo.test/a.parquet"

    def test_missing_file_raises(self):
        with pytest.raises(DownloadError, match="no contiene"):
            select_files({"id": "1", "files": [entry("a.parquet")]}, ["otro.parquet"])

    def test_unsupported_checksum_raises(self):
        file = entry("a.parquet") | {"checksum": "sha1:abc"}
        with pytest.raises(DownloadError, match="no soportado"):
            select_files({"id": "1", "files": [file]}, ["a.parquet"])


class TestDownloadFile:
    def test_downloads_and_verifies(self, tmp_path, fake_session):
        session = fake_session(FakeResponse(chunks=[CONTENT[:500], CONTENT[500:]]))

        status = download_file(session, remote(), tmp_path)

        assert status is DownloadStatus.DOWNLOADED
        assert (tmp_path / "tabla.parquet").read_bytes() == CONTENT
        assert list(tmp_path.glob("*.part")) == []

    def test_http_error_leaves_nothing(self, tmp_path, fake_session):
        session = fake_session(FakeResponse(status_code=404))

        with pytest.raises(DownloadError, match="falló la descarga"):
            download_file(session, remote(), tmp_path)

        assert list(tmp_path.iterdir()) == []

    def test_interrupted_download_leaves_no_partial_file(self, tmp_path, fake_session):
        session = fake_session(FakeResponse(chunks=[CONTENT[:500], CONTENT[500:]], fail_after=1))

        with pytest.raises(DownloadError):
            download_file(session, remote(), tmp_path)

        assert list(tmp_path.iterdir()) == []

    def test_checksum_mismatch_is_rejected(self, tmp_path, fake_session):
        corrupt = b"X" * len(CONTENT)
        session = fake_session(FakeResponse(content=corrupt))

        with pytest.raises(DownloadError, match="incompleto o corrupto"):
            download_file(session, remote(), tmp_path)

        assert list(tmp_path.iterdir()) == []

    def test_existing_valid_file_is_not_downloaded_again(self, tmp_path, fake_session):
        (tmp_path / "tabla.parquet").write_bytes(CONTENT)
        session = fake_session()  # cualquier llamada HTTP haría fallar la prueba

        status = download_file(session, remote(), tmp_path)

        assert status is DownloadStatus.SKIPPED
        assert session.calls == []

    def test_existing_altered_file_is_not_overwritten(self, tmp_path, fake_session):
        target = tmp_path / "tabla.parquet"
        target.write_bytes(b"alterado")
        session = fake_session()

        with pytest.raises(DownloadError, match="no se sobrescribe"):
            download_file(session, remote(), tmp_path)

        assert target.read_bytes() == b"alterado"

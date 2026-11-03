"""Dobles de prueba compartidos. Las pruebas nunca acceden a internet."""

from __future__ import annotations

import json

import pytest
import requests


class FakeResponse:
    """Respuesta HTTP mínima con la interfaz que usa la ingesta."""

    def __init__(self, status_code=200, content=b"", chunks=None, fail_after=None):
        self.status_code = status_code
        self.content = content
        self._chunks = chunks if chunks is not None else [content]
        self._fail_after = fail_after  # corta el streaming tras N bloques

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=None):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise requests.ConnectionError("conexión cortada")
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    """Devuelve las respuestas en orden y registra cada llamada."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"llamada HTTP inesperada a {url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake_session():
    return FakeSession

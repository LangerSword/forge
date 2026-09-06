import json
from pathlib import Path

import httpx
import pytest

from forge.ao import AOClient, AOTransportError, write_ao_surface


def test_surface_manifest_marks_spawn_blocked(tmp_path: Path):
    p = write_ao_surface(tmp_path / '.forge' / 'ao-surface.json')
    data = json.loads(p.read_text())
    assert data['routes']['healthz']['status'] == 'known_exercised'
    assert data['routes']['spawn']['status'] == 'blocked_unknown_payload'


def test_client_restricts_non_loopback():
    with pytest.raises(ValueError):
        AOClient('https://example.com')


def test_client_wraps_http_errors(monkeypatch):
    class FakeClient:
        def request(self, *args, **kwargs):
            request = httpx.Request('GET', 'http://127.0.0.1:3001/healthz')
            response = httpx.Response(503, request=request)
            response.raise_for_status()

    client = AOClient()
    client._client = FakeClient()
    with pytest.raises(AOTransportError):
        client.health()

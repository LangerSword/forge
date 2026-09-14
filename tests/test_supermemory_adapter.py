from __future__ import annotations

from types import SimpleNamespace

import pytest

from forge.memory import MemoryAdapter, Observation
from forge.supermemory_adapter import MemoryTransportError, SupermemoryAdapter


class FakeHttpClient:
    """Records calls; returns canned responses. Never touches the network."""

    def __init__(self, responses: dict | None = None):
        self.calls: list[dict] = []
        self.responses = responses or {}

    def request(self, method, url, *, json_body=None, params=None, headers=None):
        self.calls.append({
            "method": method,
            "url": url,
            "json_body": json_body,
            "params": params,
            "headers": headers,
        })
        value = self.responses.get((method, url))
        if isinstance(value, Exception):
            raise value
        return value if value is not None else ({"results": []} if "search" in url else {})


def _observation() -> Observation:
    return Observation(
        node_id="n1",
        kind="outcome",
        description="built the settings panel",
        task_family="settings-ui",
        evidence_refs=("run:r1",),
        activation="high",
    )


def test_write_issues_exactly_one_request_with_metadata() -> None:
    client = FakeHttpClient()
    adapter = SupermemoryAdapter(api_key="test-only", client=client)

    adapter.write(_observation())

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["json_body"]["content"] == "built the settings panel"
    metadata = call["json_body"]["metadata"]
    assert metadata["node_id"] == "n1"
    assert metadata["kind"] == "outcome"
    assert metadata["task_family"] == "settings-ui"
    assert metadata["evidence_refs"] == ["run:r1"]


def test_write_sends_bearer_token() -> None:
    client = FakeHttpClient()
    adapter = SupermemoryAdapter(api_key="test-only", client=client)
    adapter.write(_observation())
    assert client.calls[0]["headers"]["Authorization"] == "Bearer test-only"


def test_recall_maps_response_and_respects_limit() -> None:
    client = FakeHttpClient({
        ("GET", "http://localhost:6767/v3/search"): {
            "results": [
                {"content": "first", "metadata": {"node_id": "a", "kind": "decision",
                                                 "task_family": "f1", "evidence_refs": ["run:1"],
                                                 "activation": "high"}},
                {"content": "second", "metadata": {"node_id": "b"}},
                {"content": "third", "metadata": {"node_id": "c"}},
            ]
        }
    })
    adapter = SupermemoryAdapter(api_key="test-only", client=client)

    recalled = adapter.recall(query="settings", limit=2)

    assert len(recalled) == 2
    assert recalled[0].description == "first"
    assert recalled[0].node_id == "a"
    assert recalled[0].kind == "decision"
    assert recalled[0].task_family == "f1"
    assert recalled[0].evidence_refs == ("run:1",)
    assert client.calls[0]["params"]["limit"] == 2
    assert client.calls[0]["params"]["q"] == "settings"


def test_missing_api_key_fails_loudly(monkeypatch) -> None:
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    adapter = SupermemoryAdapter(client=FakeHttpClient())

    with pytest.raises(ValueError, match="SUPERMEMORY_API_KEY is not configured"):
        adapter.write(_observation())
    with pytest.raises(ValueError, match="SUPERMEMORY_API_KEY is not configured"):
        adapter.recall(query="anything")


def test_api_key_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_from_env")
    adapter = SupermemoryAdapter(client=FakeHttpClient())
    assert adapter.api_key == "sm_from_env"


def test_transport_failure_raises_and_never_pretends_empty() -> None:
    def boom(method, url, **kwargs):
        raise ConnectionError("connection refused")

    adapter = SupermemoryAdapter(api_key="test-only", client=SimpleNamespace(request=boom))

    with pytest.raises(MemoryTransportError):
        adapter.recall(query="anything")
    with pytest.raises(MemoryTransportError):
        adapter.write(_observation())


def test_backend_error_response_raises_transport_error() -> None:
    client = FakeHttpClient({
        ("GET", "http://localhost:6767/v3/search"): MemoryTransportError("http 503"),
    })
    adapter = SupermemoryAdapter(api_key="test-only", client=client)
    with pytest.raises(MemoryTransportError):
        adapter.recall(query="anything")


def test_adapter_satisfies_memory_protocol() -> None:
    client = FakeHttpClient()
    adapter: MemoryAdapter = SupermemoryAdapter(api_key="test-only", client=client)

    adapter.write(_observation())

    assert adapter.recall(query="anything") == ()
    assert len(client.calls) == 2


def test_profile_returns_backend_summary() -> None:
    client = FakeHttpClient({
        ("GET", "http://localhost:6767/v3/profile"): {
            "tag": "settings-ui",
            "observation_count": 3,
            "kinds": {"outcome": 2, "decision": 1},
        }
    })
    adapter = SupermemoryAdapter(api_key="test-only", client=client)

    profile = adapter.profile(tag="settings-ui")

    assert profile["observation_count"] == 3
    assert profile["kinds"] == {"outcome": 2, "decision": 1}
    assert client.calls[0]["params"]["tag"] == "settings-ui"


def test_build_memory_adapter_falls_back_to_local_stub(monkeypatch) -> None:
    from forge.memory import LocalMemoryStub
    from forge.supermemory_adapter import build_memory_adapter

    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    adapter = build_memory_adapter()
    assert isinstance(adapter, LocalMemoryStub)


def test_build_memory_adapter_selects_supermemory_when_configured(monkeypatch) -> None:
    from forge.supermemory_adapter import build_memory_adapter

    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_test")
    adapter = build_memory_adapter(client=FakeHttpClient())
    assert isinstance(adapter, SupermemoryAdapter)

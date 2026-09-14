"""Supermemory adapter: a real backend behind the ``MemoryAdapter`` protocol.

Design rules (non-negotiable):

- **Never silently succeed.** A missing API key raises ``ValueError``; a
  transport failure raises ``MemoryTransportError``. Recall never returns an
  empty tuple to disguise a broken backend.
- **All HTTP goes through an injectable client** so tests exercise the full
  mapping without touching the network.
- **The local stub remains authoritative until this adapter is configured and
  read back.** Selecting the backend is a caller decision, not a default.

Endpoint paths and payload shapes here follow the documented Supermemory
request pattern (content + metadata on write, search on recall). Verify them
against the live API docs before connecting a real deployment — this module
has been exercised against a fake client, not the live service.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .memory import LocalMemoryStub, Observation

DEFAULT_BASE_URL = "http://localhost:6767"


class MemoryTransportError(RuntimeError):
    """A memory-backend failure that must surface, never be swallowed."""


class HttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...


class UrllibHttpClient:
    """Minimal stdlib HTTP client — no extra dependency, no hidden retries."""

    def __init__(self, timeout_s: float = 15.0):
        self.timeout_s = timeout_s

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise MemoryTransportError(f"http {exc.code} from memory backend") from exc
        except urllib.error.URLError as exc:
            raise MemoryTransportError(f"memory backend unreachable: {exc.reason}") from exc
        return json.loads(body) if body else {}


class SupermemoryAdapter:
    """MemoryAdapter implementation backed by a Supermemory-compatible service."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        client: HttpClient | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.api_key = api_key or os.getenv("SUPERMEMORY_API_KEY")
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.timeout_s = timeout_s

    def _http(self) -> HttpClient:
        if not self.api_key:
            raise ValueError("SUPERMEMORY_API_KEY is not configured")
        if self._client is None:
            self._client = UrllibHttpClient(timeout_s=self.timeout_s)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def write(self, observation: Observation) -> None:
        client = self._http()
        payload = {
            "content": observation.description,
            "metadata": {
                "node_id": observation.node_id,
                "kind": observation.kind,
                "task_family": observation.task_family,
                "activation": observation.activation,
                "evidence_refs": list(observation.evidence_refs),
            },
        }
        try:
            client.request(
                "POST",
                f"{self.base_url}/v3/documents",
                json_body=payload,
                headers=self._headers(),
            )
        except MemoryTransportError:
            raise
        except Exception as exc:
            raise MemoryTransportError(
                f"supermemory write failed: {type(exc).__name__}"
            ) from exc

    def recall(
        self, *, query: str, task_family: str | None = None, limit: int = 5
    ) -> tuple[Observation, ...]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        client = self._http()
        params: dict[str, Any] = {"q": query, "limit": limit}
        if task_family is not None:
            params["containerTags"] = task_family
        try:
            response = client.request(
                "GET",
                f"{self.base_url}/v3/search",
                params=params,
                headers=self._headers(),
            )
        except MemoryTransportError:
            raise
        except Exception as exc:
            raise MemoryTransportError(
                f"supermemory recall failed: {type(exc).__name__}"
            ) from exc
        results = response.get("results") or []
        observations: list[Observation] = []
        for item in results[:limit]:
            observations.append(self._to_observation(item))
        return tuple(observations)

    def profile(self, *, tag: str) -> dict[str, Any]:
        client = self._http()
        try:
            response = client.request(
                "GET",
                f"{self.base_url}/v3/profile",
                params={"tag": tag},
                headers=self._headers(),
            )
        except MemoryTransportError:
            raise
        except Exception as exc:
            raise MemoryTransportError(
                f"supermemory profile failed: {type(exc).__name__}"
            ) from exc
        return {
            "tag": tag,
            "observation_count": int(response.get("observation_count", 0)),
            "kinds": dict(response.get("kinds") or {}),
        }

    @staticmethod
    def _to_observation(item: dict[str, Any]) -> Observation:
        metadata = item.get("metadata") or {}
        return Observation(
            node_id=str(metadata.get("node_id") or item.get("id") or "unknown"),
            kind=str(metadata.get("kind") or "outcome"),
            description=str(item.get("content") or item.get("description") or ""),
            task_family=str(metadata.get("task_family") or "unknown"),
            evidence_refs=tuple(metadata.get("evidence_refs") or ()),
            activation=str(metadata.get("activation") or "medium"),
        )


def build_memory_adapter(
    *,
    base_url: str = DEFAULT_BASE_URL,
    client: HttpClient | None = None,
) -> LocalMemoryStub | SupermemoryAdapter:
    """Select the memory backend: Supermemory when configured, local stub otherwise.

    The stub is the default because it is deterministic and offline. Selecting
    the hosted backend is an explicit configuration act (SUPERMEMORY_API_KEY).
    """
    if os.getenv("SUPERMEMORY_API_KEY"):
        return SupermemoryAdapter(base_url=base_url, client=client)
    return LocalMemoryStub()

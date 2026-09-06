"""AO loopback transport for the known, exercised API surface."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import neatlogs


class AOTransportError(RuntimeError):
    pass


@dataclass
class AOClient:
    base_url: str = "http://127.0.0.1:3001"
    timeout_s: float = 5.0

    def __post_init__(self):
        if not self.base_url.startswith("http://127.0.0.1:"):
            raise ValueError("AO client is restricted to loopback HTTP")
        self._client = httpx.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout_s)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=payload, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise AOTransportError(f"AO {method} {path} failed status={status}: {str(exc)[:300]}") from exc

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def health(self) -> dict[str, Any]: return self.get("/healthz")
    def ready(self) -> dict[str, Any]: return self.get("/readyz")
    def agents(self) -> dict[str, Any]: return self.get("/api/v1/agents")
    def projects(self) -> dict[str, Any]: return self.get("/api/v1/projects")
    def sessions(self) -> dict[str, Any]: return self.get("/api/v1/sessions")
    def session(self, session_id: str) -> dict[str, Any]: return self.get(f"/api/v1/sessions/{session_id}")

    @neatlogs.span(kind="TOOL", name="send")
    def send(self, session_id: str, message: str) -> dict[str, Any]:
        return self.post(f"/api/v1/sessions/{session_id}/send", {"message": message})

    @neatlogs.span(kind="TOOL", name="kill")
    def kill(self, session_id: str) -> dict[str, Any]:
        return self.post(f"/api/v1/sessions/{session_id}/kill", {})


def write_ao_surface(path: Path, *, base_url: str = "http://127.0.0.1:3001") -> Path:
    surface = {
        "base_url": base_url,
        "routes": {
            "healthz": {"method": "GET", "status": "known_exercised"},
            "readyz": {"method": "GET", "status": "known_exercised"},
            "agents": {"method": "GET", "status": "known_exercised"},
            "projects": {"method": "GET", "status": "known_exercised"},
            "sessions": {"method": "GET", "status": "known_exercised"},
            "session": {"method": "GET", "status": "known_exercised"},
            "send": {"method": "POST", "status": "known_unexercised", "payload": {"message": "<redacted>"}},
            "kill": {"method": "POST", "status": "known_unexercised", "payload": {}},
            "spawn": {
                "method": "POST", "status": "blocked_unknown_payload",
                "reason": "CLI flags are known; raw JSON body and response semantics are not verified.",
                "next_action": "Use AO CLI spawn for an explicitly approved tiny worker, then record observed result.",
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
    return path

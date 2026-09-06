"""Evidence-bounded readiness contract for AO coding harnesses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class HarnessReadiness:
    """Observed readiness facts for one supported AO harness."""

    name: str
    supported: bool
    installed: bool
    authorized: bool
    smoke_tested: bool

    @property
    def ready(self) -> bool:
        return self.supported and self.installed and self.authorized and self.smoke_tested

    @property
    def state(self) -> str:
        if self.ready:
            return "ready"
        if not self.supported:
            return "unsupported"
        if not self.installed:
            return "not_installed"
        if not self.authorized:
            return "not_authorized"
        if not self.smoke_tested:
            return "not_smoke_tested"
        return "not_ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "supported": self.supported,
            "installed": self.installed,
            "authorized": self.authorized,
            "smoke_tested": self.smoke_tested,
            "ready": self.ready,
            "state": self.state,
        }


@dataclass(frozen=True)
class HarnessReadinessReport:
    harnesses: tuple[HarnessReadiness, ...]

    @property
    def authorized_smoke_tested_count(self) -> int:
        return sum(item.supported and item.installed and item.authorized and item.smoke_tested for item in self.harnesses)

    @property
    def cross_harness_pass(self) -> bool:
        return cross_harness_pass(self)

    def to_dict(self) -> dict[str, Any]:
        ready = self.authorized_smoke_tested_count
        return {
            "schema_version": "forge.harness-readiness.v1",
            "harnesses": [item.to_dict() for item in self.harnesses],
            "authorized_smoke_tested_count": ready,
            "cross_harness_pass": ready >= 2,
        }


def _as_bool(value: Any) -> bool:
    return value is True


def _name(agent: Mapping[str, Any]) -> str | None:
    for key in ("name", "id", "slug", "type", "agent"):
        value = agent.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _authorized(agent: Mapping[str, Any]) -> bool:
    status = agent.get("authStatus", agent.get("auth_status", agent.get("authorization")))
    if isinstance(status, str):
        return status.strip().lower() in {"authorized", "authenticated", "ready", "logged_in"}
    return _as_bool(status)


def _names(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        values: Iterable[Any] = value.keys()
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return ()
    result: list[str] = []
    for item in values:
        name = _name(item) if isinstance(item, Mapping) else str(item).strip().lower()
        if name and name not in result:
            result.append(name)
    return tuple(result)


def build_harness_report(
    catalog: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
    *,
    supported_catalog: Iterable[str] | None = None,
    smoke_tested: Mapping[str, Any] | Iterable[str] = (),
) -> HarnessReadinessReport:
    """Normalize AO catalog facts without treating unknown fields as evidence.

    ``supported_catalog`` is explicit because a missing catalog cannot prove
    that an arbitrary local binary is supported.  The input is copied into
    booleans only; raw AO payloads and credential-like fields are not emitted.
    """
    if supported_catalog is None:
        if isinstance(catalog, Mapping):
            supported = catalog.get("supported", catalog.get("catalog", ()))
            supported_names = _names(supported)
        else:
            supported_names = ()
    else:
        supported_names = tuple(str(item).strip().lower() for item in supported_catalog if str(item).strip())
    supported_set = set(supported_names)

    installed_names: set[str] = set()
    authorized_names: set[str] = set()
    if isinstance(catalog, Mapping):
        catalog_map = catalog
        raw_agents = catalog_map.get("agents", catalog_map.get("items", ()))
        installed_names = set(_names(catalog_map.get("installed", ())))
        authorized_names = set(_names(catalog_map.get("authorized", ())))
    else:
        raw_agents = catalog or ()
    agents = [item for item in raw_agents if isinstance(item, Mapping)]
    observed: dict[str, Mapping[str, Any]] = {}
    for agent in agents:
        name = _name(agent)
        if name:
            observed[name] = agent

    if isinstance(smoke_tested, Mapping):
        smoked = {str(name).strip().lower() for name, passed in smoke_tested.items() if _as_bool(passed)}
    else:
        smoked = {str(name).strip().lower() for name in smoke_tested}
    names = list(supported_names)
    for name in observed:
        if name not in names:
            names.append(name)
    result = []
    for name in names:
        agent = observed.get(name, {})
        installed_value = agent.get("installed", agent.get("isInstalled", agent.get("present", False)))
        result.append(
            HarnessReadiness(
                name=name,
                supported=name in supported_set if supported_set else name in observed,
                installed=name in installed_names or _as_bool(installed_value),
                authorized=name in authorized_names or _authorized(agent),
                smoke_tested=name in smoked,
            )
        )
    return HarnessReadinessReport(tuple(result))


def cross_harness_pass(report: HarnessReadinessReport) -> bool:
    """Require two distinct, authorized and smoke-tested harnesses."""
    return len({item.name for item in report.harnesses if item.ready}) >= 2

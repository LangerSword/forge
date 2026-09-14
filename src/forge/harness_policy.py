"""The declared unified-harness contract.

One harness, pinned variance: instead of proving a skill portable across
harnesses we will never run, the environment is pinned by construction — a
policy declares what can be used (harness, models, session interface, poll
bounds), ``validate_request`` rejects anything else loudly BEFORE any spawn
touches the daemon, and ``policy_hash`` pins comparability: two runs are only
comparable when they were validated against the same policy hash, recorded in
the ledger next to the actual spawn flags.

Same fail-loud style as ``observation_policy.ObservationPolicy``: a violated
contract is an exception, never a silently downgraded request.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PINNED_HARNESS = "opencode"


class HarnessPolicyError(ValueError):
    """A requested run violates the declared harness policy."""


@dataclass(frozen=True)
class HarnessPolicy:
    """What can be used in a Forge-run session on the unified harness.

    - ``harness`` is pinned: the unified harness is opencode.
    - ``allowed_models`` is an explicit allowlist of exact ids or provider
      prefixes (``"nvidia/"`` covers the nvidia family); ``None`` allows the
      harness default (model unset) so model-variant A/B stays first-class
      *inside* the policy.
    - ``allowed_modes`` pins the session interface (chat, i.e. the structured
      agent connection the runner polls).
    - the bounds cap every run's poll/runtime budget.
    """

    harness: str
    allowed_models: tuple[str | None, ...] = (None,)
    allowed_modes: tuple[str, ...] = ("chat",)
    max_polls: int = 120
    max_poll_interval_s: float = 30.0
    max_runtime_s: float = 900.0
    max_idle_s: float = 300.0

    def __post_init__(self) -> None:
        if self.harness != PINNED_HARNESS:
            raise HarnessPolicyError(
                f"harness is pinned to {PINNED_HARNESS!r}; got {self.harness!r}"
            )
        if not self.allowed_models:
            raise HarnessPolicyError("allowed_models must not be empty (allow the default with None)")
        if self.max_polls < 1:
            raise HarnessPolicyError("max_polls must be >= 1")
        if self.max_poll_interval_s <= 0:
            raise HarnessPolicyError("max_poll_interval_s must be > 0")
        if self.max_runtime_s <= 0:
            raise HarnessPolicyError("max_runtime_s must be > 0")
        if self.max_idle_s < 0:
            raise HarnessPolicyError("max_idle_s must be >= 0")

    def _model_allowed(self, model: str | None) -> bool:
        for entry in self.allowed_models:
            if entry is None:
                if model is None:
                    return True
                continue
            if model is None:
                continue
            if model == entry or model.startswith(entry):
                return True
        return False

    def validate_request(self, request: Any) -> None:
        """Reject a run request that violates the policy — before spawn."""
        if request.harness != self.harness:
            raise HarnessPolicyError(f"harness is not allowlisted: {request.harness!r}")
        if request.mode not in self.allowed_modes:
            raise HarnessPolicyError(f"session mode is not allowlisted: {request.mode!r}")
        if not self._model_allowed(getattr(request, "model", None)):
            raise HarnessPolicyError(f"model is not allowlisted: {request.model!r}")
        if request.max_polls > self.max_polls:
            raise HarnessPolicyError(
                f"max_polls {request.max_polls} exceeds policy {self.max_polls}"
            )
        if request.poll_interval_s > self.max_poll_interval_s:
            raise HarnessPolicyError(
                f"poll_interval_s {request.poll_interval_s} exceeds policy {self.max_poll_interval_s}"
            )
        if request.max_runtime_s is not None and request.max_runtime_s > self.max_runtime_s:
            raise HarnessPolicyError(
                f"max_runtime_s {request.max_runtime_s} exceeds policy {self.max_runtime_s}"
            )
        if request.max_idle_s > self.max_idle_s:
            raise HarnessPolicyError(
                f"max_idle_s {request.max_idle_s} exceeds policy {self.max_idle_s}"
            )

    @classmethod
    def load(cls, path: Path) -> "HarnessPolicy":
        """Load the declared contract from JSON, validating on construction."""
        data = json.loads(path.read_text())
        return cls(
            harness=data["harness"],
            allowed_models=tuple(data.get("allowed_models", (None,))),
            allowed_modes=tuple(data.get("allowed_modes", ("chat",))),
            max_polls=int(data.get("max_polls", 120)),
            max_poll_interval_s=float(data.get("max_poll_interval_s", 30.0)),
            max_runtime_s=float(data.get("max_runtime_s", 900.0)),
            max_idle_s=float(data.get("max_idle_s", 300.0)),
        )


def policy_hash(policy: HarnessPolicy) -> str:
    """Deterministic hash over the policy's pins — the comparability contract.

    Two runs are only comparable when their ledger records show the same
    policy hash; any pin change (bounds, model allowlist, mode) changes the
    hash and breaks comparability loudly.
    """
    payload = json.dumps({
        "harness": policy.harness,
        "allowed_models": list(policy.allowed_models),
        "allowed_modes": list(policy.allowed_modes),
        "max_polls": policy.max_polls,
        "max_poll_interval_s": policy.max_poll_interval_s,
        "max_runtime_s": policy.max_runtime_s,
        "max_idle_s": policy.max_idle_s,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_request(request: Any, policy: HarnessPolicy) -> bool:
    """Convenience wrapper: validate and return True, raising on violation."""
    policy.validate_request(request)
    return True

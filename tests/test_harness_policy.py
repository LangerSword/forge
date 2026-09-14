"""Tests for harness_policy.py — the declared unified-harness contract.

One harness, pinned variance: a policy declares what can be used (harness,
models, bounds) and validate_request() rejects anything else loudly — before
any spawn touches the daemon.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from forge.harness_policy import (
    HarnessPolicy,
    HarnessPolicyError,
    policy_hash,
    validate_request,
)

VALID_POLICY = HarnessPolicy(
    harness="opencode",
    allowed_models=("nvidia/", "deepseek/", "local-lmstudio/", None),
    allowed_modes=("chat",),
    max_polls=120,
    max_poll_interval_s=30.0,
    max_runtime_s=900.0,
    max_idle_s=300.0,
)


# --------------------------------------------------------------------------
# Policy construction
# --------------------------------------------------------------------------


def test_policy_rejects_unknown_harness() -> None:
    with pytest.raises(HarnessPolicyError, match="harness"):
        HarnessPolicy(harness="claude-code")


def test_policy_rejects_empty_model_allowlist() -> None:
    with pytest.raises(HarnessPolicyError, match="model"):
        HarnessPolicy(harness="opencode", allowed_models=())


def test_policy_rejects_bad_bounds() -> None:
    with pytest.raises(HarnessPolicyError, match="polls"):
        HarnessPolicy(harness="opencode", max_polls=0)
    with pytest.raises(HarnessPolicyError, match="interval"):
        HarnessPolicy(harness="opencode", max_poll_interval_s=0.0)
    with pytest.raises(HarnessPolicyError, match="runtime"):
        HarnessPolicy(harness="opencode", max_runtime_s=0.0)
    with pytest.raises(HarnessPolicyError, match="idle"):
        HarnessPolicy(harness="opencode", max_idle_s=-1.0)


def test_policy_hash_is_deterministic_and_sensitive() -> None:
    p2 = replace(VALID_POLICY)
    assert policy_hash(VALID_POLICY) == policy_hash(p2)
    # any pin change must change the hash (the comparability contract)
    assert policy_hash(VALID_POLICY) != policy_hash(replace(VALID_POLICY, max_runtime_s=600.0))
    assert policy_hash(VALID_POLICY) != policy_hash(replace(VALID_POLICY, allowed_models=("nvidia/",)))
    assert policy_hash(VALID_POLICY) != policy_hash(replace(VALID_POLICY, allowed_modes=("chat", "tui")))


# --------------------------------------------------------------------------
# validate_request: fail loud before any spawn
# --------------------------------------------------------------------------


def _request(**overrides: Any) -> Any:
    from forge.ao_runner import AORunRequest

    defaults: dict[str, Any] = {
        "run_id": "policy-test",
        "goal": "g",
        "project": "forge",
        "worker_name": "w",
        "prompt": "do the thing",
        "harness": "opencode",
        "mode": "chat",
        "max_polls": 40,
        "poll_interval_s": 2.0,
        "max_runtime_s": 300.0,
        "max_idle_s": 90.0,
    }
    defaults.update(overrides)
    return AORunRequest(**defaults)


def test_validate_accepts_within_policy() -> None:
    assert validate_request(_request(), VALID_POLICY) is True


def test_validate_rejects_nonallowlisted_model() -> None:
    with pytest.raises(HarnessPolicyError, match="model"):
        validate_request(_request(model="some-sketchy-model"), VALID_POLICY)


def test_validate_rejects_wrong_harness() -> None:
    with pytest.raises(HarnessPolicyError, match="harness"):
        validate_request(_request(harness="claude-code"), VALID_POLICY)


def test_validate_rejects_wrong_mode() -> None:
    with pytest.raises(HarnessPolicyError, match="mode"):
        validate_request(_request(mode="tui"), VALID_POLICY)


def test_validate_rejects_bounds_outside_policy() -> None:
    with pytest.raises(HarnessPolicyError, match="polls"):
        validate_request(_request(max_polls=200), VALID_POLICY)
    with pytest.raises(HarnessPolicyError, match="runtime"):
        validate_request(_request(max_runtime_s=3600.0), VALID_POLICY)
    with pytest.raises(HarnessPolicyError, match="interval"):
        validate_request(_request(poll_interval_s=60.0), VALID_POLICY)
    with pytest.raises(HarnessPolicyError, match="idle"):
        validate_request(_request(max_idle_s=600.0), VALID_POLICY)


def test_validate_allows_prefix_matches_and_default_model() -> None:
    # prefix entry ("nvidia/") covers provider families; None = harness default
    assert validate_request(_request(model="nvidia/abacusai/dracarys-llama-3.1-70b-instruct"), VALID_POLICY) is True
    assert validate_request(_request(model="deepseek/deepseek-v4-flash"), VALID_POLICY) is True
    assert validate_request(model := _request(model=None), VALID_POLICY) is True  # noqa: F841


def test_policy_load_round_trips_json(tmp_path: Path) -> None:
    path = tmp_path / "harness-policy.json"
    path.write_text(json.dumps({
        "harness": "opencode",
        "allowed_models": ["nvidia/", "deepseek/", "local-lmstudio/", None],
        "allowed_modes": ["chat"],
        "max_polls": 120,
        "max_poll_interval_s": 30.0,
        "max_runtime_s": 900.0,
        "max_idle_s": 300.0,
    }))
    policy = HarnessPolicy.load(path)
    assert policy == VALID_POLICY
    assert policy_hash(policy) == policy_hash(VALID_POLICY)


def test_policy_load_rejects_unknown_harness(tmp_path: Path) -> None:
    path = tmp_path / "harness-policy.json"
    path.write_text(json.dumps({"harness": "codex", "allowed_models": ["x/"]}))
    with pytest.raises(HarnessPolicyError, match="harness"):
        HarnessPolicy.load(path)


import json  # noqa: E402  (used above; kept next to its tests)

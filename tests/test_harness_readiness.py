import json
from pathlib import Path

from forge.harness_readiness import (
    HarnessReadiness,
    HarnessReadinessReport,
    build_harness_report,
    cross_harness_pass,
)


def test_readiness_distinguishes_catalog_install_auth_and_smoke():
    report = build_harness_report(
        {
            "agents": [
                {"name": "opencode", "installed": True, "authStatus": "authorized"},
                {"name": "claude-code", "installed": True, "authStatus": "unknown"},
            ]
        },
        supported_catalog=("opencode", "claude-code", "codex"),
        smoke_tested={"opencode": True},
    )

    by_name = {item.name: item for item in report.harnesses}
    assert by_name["opencode"].ready
    assert by_name["opencode"].smoke_tested
    assert not by_name["claude-code"].authorized
    assert not by_name["claude-code"].ready
    assert by_name["codex"].supported
    assert not by_name["codex"].installed
    assert not report.cross_harness_pass
    assert report.authorized_smoke_tested_count == 1


def test_cross_harness_pass_requires_two_ready_harnesses():
    a = HarnessReadiness("a", True, True, True, True)
    b = HarnessReadiness("b", True, True, True, True)
    c = HarnessReadiness("c", True, True, True, False)
    report = HarnessReadinessReport((a, b, c))
    assert cross_harness_pass(report)
    assert report.to_dict()["cross_harness_pass"] is True
    assert json.loads(json.dumps(report.to_dict()))["schema_version"] == "forge.harness-readiness.v1"


def test_report_serialization_never_includes_raw_agent_payload(tmp_path: Path):
    report = build_harness_report(
        {"agents": [{"name": "opencode", "installed": True, "authStatus": "authorized", "token": "secret"}]},
        smoke_tested={"opencode": True},
    )
    payload = json.dumps(report.to_dict())
    assert "secret" not in payload
    assert "token" not in payload.lower()


def test_smoke_tested_requires_explicit_true():
    report = build_harness_report(
        {"agents": [{"name": "opencode", "installed": True, "authStatus": "authorized"}]},
        smoke_tested={"opencode": "passed"},
    )
    assert not report.harnesses[0].smoke_tested

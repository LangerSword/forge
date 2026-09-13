"""Tests for the context-fabric memory protocol and the local deterministic store."""
from __future__ import annotations

import pytest

from forge.memory import LocalMemoryStub, MemoryAdapter, Observation, render_recall


def _obs(
    node_id: str = "n1",
    kind: str = "design_pattern",
    description: str = "card-based layout with frosted glass",
    task_family: str = "ui",
    **overrides,
) -> Observation:
    base = dict(
        node_id=node_id,
        kind=kind,
        description=description,
        task_family=task_family,
        evidence_refs=("run:n1",),
        activation="medium",
    )
    base.update(overrides)
    return Observation(**base)


def test_observation_requires_node_and_kind() -> None:
    with pytest.raises(Exception):
        Observation(node_id="", kind="design_pattern", description="x")
    with pytest.raises(Exception):
        Observation(node_id="n1", kind="", description="x")


def test_local_memory_writes_and_recalls_observation() -> None:
    memory = LocalMemoryStub()
    memory.write(_obs())
    recalled = memory.recall(query="frosted glass layout", limit=5)
    assert len(recalled) == 1
    assert recalled[0].node_id == "n1"
    assert recalled[0].description == "card-based layout with frosted glass"


def test_local_memory_recall_respects_limit() -> None:
    memory = LocalMemoryStub()
    for index in range(3):
        memory.write(
            _obs(node_id=f"n{index}", description=f"shared token number {index}", task_family="ui")
        )
    recalled = memory.recall(query="shared token", limit=2)
    assert len(recalled) == 2


def test_local_memory_recall_filters_by_task_family() -> None:
    memory = LocalMemoryStub()
    memory.write(_obs(node_id="alpha-1", description="alpha layout", task_family="alpha"))
    memory.write(_obs(node_id="beta-1", description="alpha layout again", task_family="beta"))
    recalled = memory.recall(query="alpha layout", task_family="alpha", limit=5)
    assert [obs.node_id for obs in recalled] == ["alpha-1"]


def test_local_memory_recall_is_deterministic() -> None:
    memory = LocalMemoryStub()
    memory.write(_obs(node_id="first", description="same shared words here"))
    memory.write(_obs(node_id="second", description="same shared words here"))
    first = memory.recall(query="same shared words", limit=5)
    second = memory.recall(query="same shared words", limit=5)
    assert [obs.node_id for obs in first] == [obs.node_id for obs in second]


def test_local_memory_profile_returns_compact_summary() -> None:
    memory = LocalMemoryStub()
    memory.write(_obs(node_id="a", kind="decision", task_family="ui"))
    memory.write(_obs(node_id="b", kind="failure", task_family="ui"))
    profile = memory.profile(tag="ui")
    assert profile["tag"] == "ui"
    assert profile["observation_count"] == 2
    assert profile["kinds"] == {"decision": 1, "failure": 1}


def test_local_memory_satisfies_protocol() -> None:
    memory: MemoryAdapter = LocalMemoryStub()
    memory.write(_obs())
    assert memory.recall(query="frosted glass", limit=1)


def test_render_recall_produces_bounded_text() -> None:
    observations = tuple(
        _obs(node_id=f"n{index}", description=f"observation number {index}") for index in range(10)
    )
    text = render_recall(observations, max_chars=200)
    assert "observation number 0" in text
    assert len(text) <= 200


def test_render_recall_marks_empty_recall_explicitly() -> None:
    text = render_recall((), max_chars=200)
    assert text == ""

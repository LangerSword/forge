"""Context fabric: the memory protocol every graph node reads and writes.

Design rule (from the graph architecture plan): nodes never pass raw
transcripts to each other. Each node RECALLS relevant context before acting
and WRITES structured observations after acting. Supermemory is the intended
production backend; `LocalMemoryStub` implements the identical contract
deterministically so the graph can be built and tested without the service.

Keep this module LLM-free and deterministic. The adapter is a boundary:
swap `LocalMemoryStub` for a Supermemory-backed adapter without touching any
scheduler or node code.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

ObservationKind = str  # design_pattern | tech_used | interaction | failure | decision | artifact | outcome

OBSERVATION_KINDS: tuple[str, ...] = (
    "design_pattern",
    "tech_used",
    "interaction",
    "failure",
    "decision",
    "artifact",
    "outcome",
)

_ACTIVATIONS = ("high", "medium", "low")


class Observation(BaseModel):
    """One structured memory entry — the unit the graph writes and recalls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=1000)
    task_family: str = Field(default="unknown", min_length=1, max_length=120)
    evidence_refs: tuple[str, ...] = ()
    activation: str = Field(default="medium")


class MemoryAdapter(Protocol):
    """The contract a memory backend must satisfy (local stub or Supermemory)."""

    def write(self, observation: Observation) -> None: ...

    def recall(
        self, *, query: str, task_family: str | None = None, limit: int = 5
    ) -> tuple[Observation, ...]: ...

    def profile(self, *, tag: str) -> dict[str, Any]: ...


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


class LocalMemoryStub:
    """Deterministic local memory: keyword-overlap recall, no network, no LLM.

    Same contract as the future Supermemory adapter. Recall is stable:
    results rank by keyword overlap and fall back to write order, so tests
    and replays are reproducible.
    """

    def __init__(self) -> None:
        self._observations: list[Observation] = []

    def write(self, observation: Observation) -> None:
        self._observations.append(observation)

    def recall(
        self, *, query: str, task_family: str | None = None, limit: int = 5
    ) -> tuple[Observation, ...]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        query_tokens = _tokens(query)
        scored: list[tuple[int, int, Observation]] = []
        for index, observation in enumerate(self._observations):
            if task_family is not None and observation.task_family != task_family:
                continue
            overlap = len(query_tokens & _tokens(observation.description))
            scored.append((overlap, index, observation))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(observation for _, _, observation in scored[:limit])

    def profile(self, *, tag: str) -> dict[str, Any]:
        matching = [obs for obs in self._observations if obs.task_family == tag]
        kinds: dict[str, int] = {}
        for observation in matching:
            kinds[observation.kind] = kinds.get(observation.kind, 0) + 1
        return {
            "tag": tag,
            "observation_count": len(matching),
            "kinds": dict(sorted(kinds.items())),
        }

    def __len__(self) -> int:
        return len(self._observations)


def render_recall(observations: tuple[Observation, ...], *, max_chars: int = 1200) -> str:
    """Render recalled observations as a bounded context block.

    Returns an empty string when there is nothing to recall — callers must
    treat empty as 'no memory', never as an error.
    """
    if not observations:
        return ""
    lines: list[str] = []
    total = 0
    for observation in observations:
        line = f"- [{observation.kind}] {observation.description} (source: {observation.node_id})"
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)

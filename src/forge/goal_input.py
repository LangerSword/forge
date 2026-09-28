"""Goal ingestion for forge commands.

Two documented input formats:

1. **GoalSpec JSON** (``.json``) — validated exactly as before.
2. **Markdown plan** (``.md`` / ``.markdown``) — a deterministic mapping,
   designed for human-written plans (OMH plans, BUILD-style docs):

   - YAML front matter (``--- ... ---``) is skipped.
   - ``# Title`` is the fallback goal text.
   - The first section whose heading contains "goal" (excluding
     "non-goal(s)" headings) supplies the goal text, one bullet per line;
     an explicit ``Goal:`` labeled line wins over any section.
   - The first section whose heading contains "acceptance" supplies the
     acceptance criteria, one per bullet (``- [ ]`` checkbox markers
     stripped). Missing acceptance fails loud — never a guessed goal.
   - Labeled lines anywhere supply: ``Repo:``, ``Harness:``, ``Artifact:``,
     ``Max minutes:``, ``Max parallel:``.
   - ``Repo`` defaults to the current directory; ``Harness`` falls back to
     ``.forge/harness-policy.json`` when present.

Every error is a GoalInputError that names the file and the fix.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import GoalSpec


class GoalInputError(ValueError):
    """A goal file that cannot be turned into a GoalSpec, with the fix."""


_JSON_SUFFIXES = {".json"}
_MD_SUFFIXES = {".md", ".markdown"}
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s*")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")


def _labeled(lines: list[str], label: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip("`").strip()
    return None


def _labeled_int(lines: list[str], label: str, *, default: int) -> int:
    raw = _labeled(lines, label)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise GoalInputError(f"'{label}:' must be an integer, got {raw!r}") from exc
    if value < 1:
        raise GoalInputError(f"'{label}:' must be >= 1, got {value}")
    return value


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            newline = text.find("\n", end + 1)
            return text[newline + 1:] if newline != -1 else ""
    return text


def _sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    title: str | None = None
    body: list[str] = []
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            if title is not None:
                sections.append((title, body))
            title, body = match.group(1).strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, body))
    return sections


def _bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = _BULLET_RE.match(line)
        if not match:
            continue
        item = _CHECKBOX_RE.sub("", match.group(1).strip()).strip()
        if item:
            items.append(item)
    return items


def _policy_harness(root: Path) -> str | None:
    path = root / ".forge" / "harness-policy.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    harness = payload.get("harness")
    return str(harness) if isinstance(harness, str) and harness.strip() else None


def goal_spec_from_markdown(text: str, *, source: str, root: Path) -> GoalSpec:
    body_text = _strip_front_matter(text)
    lines = body_text.splitlines()
    sections = _sections(lines)

    title = next((m.group(1).strip() for line in lines if (m := _HEADING_RE.match(line))), None)

    goal_text = _labeled(lines, "goal")
    if goal_text is None:
        for heading, body in sections:
            normal = heading.lower()
            if "goal" in normal and "non" not in normal:
                items = _bullets(body)
                goal_text = "\n".join(items) if items else "\n".join(line.strip() for line in body if line.strip())
                break
    goal_text = (goal_text or title or "").strip()
    if not goal_text:
        raise GoalInputError(f"no goal found in {source}: add a '## Goal' section or a 'Goal:' line")

    acceptance: list[str] = []
    for heading, body in sections:
        if "acceptance" in heading.lower():
            acceptance = _bullets(body)
            break
    if not acceptance:
        raise GoalInputError(
            f"no acceptance criteria found in {source}: add a section like "
            "'## Acceptance' with '- item' bullets (or use a GoalSpec JSON file)"
        )

    repo = _labeled(lines, "repo") or str(root)
    harness = _labeled(lines, "harness") or _policy_harness(root)
    if not harness:
        raise GoalInputError(
            f"no harness declared in {source}: add a 'Harness: <name>' line "
            "or create .forge/harness-policy.json"
        )
    artifact = _labeled(lines, "artifact")
    max_minutes = _labeled_int(lines, "max minutes", default=15)
    max_parallel = _labeled_int(lines, "max parallel", default=1)

    kwargs: dict[str, Any] = {
        "goal": goal_text[:4000],
        "repo": repo,
        "acceptance": acceptance,
        "harness": harness,
        "max_minutes": max_minutes,
        "max_parallel": max_parallel,
    }
    if artifact:
        kwargs["artifact_path"] = artifact
    return GoalSpec(**kwargs)


def load_goal_spec(path: Path, *, root: Path | None = None) -> GoalSpec:
    """Load a GoalSpec from a .json file or a .md plan, failing loud."""
    root = root or Path.cwd()
    if not path.is_file():
        raise GoalInputError(
            f"goal file not found: {path} (relative paths resolve from {root}; "
            "use an absolute path, or run from the file's directory)"
        )
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in _JSON_SUFFIXES:
        try:
            return GoalSpec.model_validate_json(text)
        except Exception as exc:
            first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            raise GoalInputError(f"invalid GoalSpec JSON in {path}: {first}") from exc
    if suffix in _MD_SUFFIXES:
        return goal_spec_from_markdown(text, source=str(path), root=root)
    raise GoalInputError(
        f"unsupported goal file type '{path.suffix}' for {path}: "
        "expected .json (GoalSpec) or .md (markdown plan)"
    )
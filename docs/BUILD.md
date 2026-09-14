# Forge — Build Plan (step-by-step, written for any model)

> **Read order:** `SPEC.md` → `architecture.md` → this file.
> This file is written so that a model that is **not** frontier-class can
> execute it literally, step by step. Follow the steps in order. Do not
> improvise architecture. When a step says "run this", run exactly that.

---

## 0. What Forge is (hold this in your head)

Forge is a **commander agent**. It takes a goal, compiles it into a **typed
execution graph**, runs the nodes as a **bounded fleet**, carries context
between nodes through a **memory fabric** (not raw transcripts), and promotes
only capabilities that **measurably improve independently verified outcomes**.

Four planes, never mixed:

| Plane | Owns | Never does |
|---|---|---|
| Execution | running nodes/workers, worktrees | deciding what "done" means |
| Evidence | ledger, verifier results | trusting worker self-reports |
| Learning | candidate skills, playbooks | promoting itself |
| Delivery | deployment | auto-deploying without approval |

The one rule that overrides everything: **a worker's self-report is never
proof.** A task passes only when a fresh artifact exists AND an independent
verifier passes.

---

## 1. Rules for the building model (mandatory)

1. **Test-first, always.** Write the failing test, run it, watch it fail,
   then implement. If you write code before its test, delete the code and
   start over.
2. **Never edit a test to make it pass.** If a test fails, fix the source.
   The only exception is a test that is provably wrong — then you must say
   so explicitly in your summary.
3. **Run the exact verification command after every step.** If it does not
   pass, stop and report. Do not continue to the next step.
4. **One step at a time.** Do not batch multiple tasks. Do not refactor
   "while you are there". Keep diffs small.
5. **The full suite must stay green.** After every task:
   `uv run pytest -q` must print the same or higher pass count and zero failures.
6. **Never commit credentials.** No API keys, tokens, or passwords in source,
   tests, logs, or commit messages. Use environment variables only.
7. **Do not touch these files unless a task explicitly says so:**
   `tests/test_ao_runner.py`, `tests/test_fleet.py::test_controller_*`
   (existing ones), `src/forge/ao_runner.py`.
8. **If you are unsure, stop and ask.** A blocked step reported honestly is
   better than a broken build.

---

## 2. Preconditions — run these first

```bash
cd ~/forge
uv run pytest -q                      # expect: 150 passed
uv run forge --version                # expect: 0.1.0
uv run forge graph /tmp/forge-graph-sample-goal.json   # expect: ok: true, node_count 2
```

If any command fails, **stop**. Fix the environment first:
`uv sync` re-installs dependencies.

---

## 3. Baseline map — what already exists

| Module | What it does | Read it before |
|---|---|---|
| `src/forge/graph.py` | `NodeSpec`, `GraphSpec`, `NodeResult`, `RoutingDecision`, `compile_goal_graph`, `to_taskgraph` | Task 1 |
| `src/forge/memory.py` | `Observation`, `MemoryAdapter`, `LocalMemoryStub`, `render_recall` | Task 2 |
| `src/forge/fleet.py` | `FleetController` — the scheduler/executor | Tasks 1, 3 |
| `src/forge/schema.py` | `GoalSpec`, `TaskSpec`, `TaskGraph`, `RunResult`, `ComparisonResult` | all |
| `src/forge/ledger.py` | SQLite event ledger; `events_for_run`, `latest_event`, task attempts | Tasks 3, 4 |
| `src/forge/verifier.py` | deterministic command checks | all |
| `src/forge/experiment.py` | baseline → reflect → gate → learned comparison | Task 5 |
| `src/forge/tooling.py` | allowlisted tool registry with evidence | Tasks 2, 5 |
| `src/forge/playbook.py` | validated playbook selection by task family | Task 5 |

Test files that already exist and must keep passing:

```text
tests/test_graph.py        (16 tests)  — typed graph
tests/test_memory.py       (9 tests)   — context fabric
tests/test_fleet.py        (20 tests)  — scheduler + memory wiring
tests/test_comparison.py   (9 tests)   — baseline vs learned
tests/test_experiment.py   (3 tests)   — learning loop
tests/test_end_to_end_experiment.py (2 tests)
tests/test_learning_gate.py (5 tests)
tests/test_tooling.py      (2 tests)
tests/test_playbook.py     (2 tests)
... plus the pre-existing AO/CLI/verifier suites
```

**Any new test file you create must be listed in your task summary.**

---

## 4. Build tasks

Do them in order. Each task is self-contained: files, steps, expected output,
done-when, and what to do when it fails.

- **Task 1** — recursive scheduler (planner nodes expand into subgraphs) — ✅ DONE (commit `028cdc7`)
- **Task 2** — judge-as-routing (a `RoutingDecision` changes what runs next) — ✅ DONE (commit `cff30e6`)
- **Task 3** — memory fabric: graph-level recall/write + ledger evidence — ✅ DONE (commit `b62d57d`)
- **Task 4** — graph persistence and resume (durable node attempts) — ✅ DONE (commit `e78e754`)
- **Task 5** — learning on graph runs (reflector consumes node observations) — ✅ DONE (commit `bc965e5`)
- **Task 6** — live Supermemory adapter behind `MemoryAdapter` — ✅ DONE (commit `130d086`)
- **Task 7** — AO specialist execution (wire `SpecialistNode` to AO) — ✅ DONE (commit `28544b8`)

> **All seven tasks are merged; full suite 193 passed.** The plan below is kept
> as the executed design record. Before starting new work, read §9 "Next work
> (not in this plan)" — it lists what is genuinely still open.

---

### Task 1 — Recursive scheduler (planner nodes expand into subgraphs) — ✅ DONE

> **Status:** implemented in `src/forge/scheduler.py`, tests in
> `tests/test_scheduler.py` (commit `028cdc7`). Kept below as the design
> record; the code already exists, so only the pitfalls matter if you touch it.

**Objective:** a planner node executes, returns a `GraphSpec`, and the
scheduler runs that subgraph recursively, bounded by `max_depth`.

**Files:**
- Create: `src/forge/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1 — write the failing test.** Create `tests/test_scheduler.py`
with exactly this content:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.graph import GraphSpec, NodeSpec
from forge.scheduler import GraphScheduler


def _specialist(node_id: str = "s1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="specialist",
        title=f"work {node_id}",
        goal=f"do {node_id}",
        acceptance=["done"],
    )


def _planner(node_id: str = "p1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="planner",
        title=f"plan {node_id}",
        goal=f"plan {node_id}",
        acceptance=["plan exists"],
    )


def _passing_runner():
    return SimpleNamespace(
        run=lambda req: SimpleNamespace(
            status="passed",
            session_id=f"session-{req.worker_name}",
            worktree=None,
            artifact_exists=True,
            verification_passed=True,
            classification=SimpleNamespace(value="passed"),
            reason="completed",
        )
    )


def test_scheduler_runs_leaf_graph(tmp_path: Path) -> None:
    scheduler = GraphScheduler(tmp_path, runner_factory=lambda req: _passing_runner())
    result = scheduler.run(GraphSpec(nodes=[_specialist()]), graph_id="g-leaf")
    assert result.status == "passed"
    assert [item.node_id for item in result.node_results] == ["s1"]


def test_scheduler_expands_planner_node_into_subgraph(tmp_path: Path) -> None:
    def planner(node: NodeSpec) -> GraphSpec:
        return GraphSpec(nodes=[_specialist("child")], rationale="planner output")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda req: _passing_runner(),
        planner=planner,
    )
    result = scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-expand")
    assert result.status == "passed"
    planner_result = result.node_results[0]
    assert planner_result.subgraph is not None
    assert planner_result.subgraph.status == "passed"
    assert planner_result.subgraph.node_results[0].node_id == "child"


def test_scheduler_enforces_max_depth(tmp_path: Path) -> None:
    def planner(node: NodeSpec) -> GraphSpec:
        return GraphSpec(nodes=[_planner(node_id="p2")], rationale="nested planner")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda req: _passing_runner(),
        planner=planner,
        max_depth=1,
    )
    with pytest.raises(ValueError, match="max_depth"):
        scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-depth")


def test_scheduler_requires_planner_callable_for_planner_nodes(tmp_path: Path) -> None:
    scheduler = GraphScheduler(tmp_path, runner_factory=lambda req: _passing_runner())
    with pytest.raises(ValueError, match="planner"):
        scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-no-planner")
```

**Step 2 — run it and watch it fail:**

```bash
uv run pytest -q tests/test_scheduler.py
```

Expected: `ModuleNotFoundError: No module named 'forge.scheduler'`.

**Step 3 — implement `src/forge/scheduler.py`.** Required API:

```python
class GraphScheduler:
    def __init__(
        self,
        root: Path,
        *,
        runner_factory,            # same contract as FleetController
        planner=None,              # Callable[[NodeSpec], GraphSpec] | None
        memory=None,               # memory adapter | None
        clock=monotonic,
        max_depth: int = 3,
    ) -> None: ...

    def run(self, graph: GraphSpec, *, graph_id: str, depth: int = 0) -> GraphRunResult: ...
```

Behavior rules (implement exactly):

1. If `depth > max_depth`, raise `ValueError(f"max_depth {max_depth} exceeded at depth {depth}")`.
2. Partition nodes: `planner` nodes vs the rest.
3. Planner nodes: call `self.planner(node)`. If `self.planner is None` and a
   planner node exists, raise `ValueError("planner nodes require a planner callable")`.
   Then recursively `self.run(subgraph, graph_id=f"{graph_id}:{node.node_id}", depth=depth + 1)`
   and wrap the result in `NodeResult(node_id=node.node_id, status=subgraph_result.status,
   observations=(), evidence_refs=(), subgraph=subgraph_result)`.
4. Non-planner nodes: execute through the existing `FleetController` by
   converting with `to_taskgraph()` (build a `GraphSpec` from just those nodes)
   and recording one `NodeResult` per task outcome (status from
   `TaskOutcome.status`; `observations` from the task reason when failed;
   `evidence_refs=(f"run:{outcome.run_id}",)`).
5. Overall `status` = `"passed"` only if every node result passed, else `"failed"`.
6. Ledger: open a run with `run_id=graph_id`, record `graph_started` and
   `graph_completed` events with node counts and status.
7. Never swallow exceptions from the runner — let them surface.

**Step 4 — run the test again:**

```bash
uv run pytest -q tests/test_scheduler.py
```

Expected: `4 passed`.

**Step 5 — full suite:**

```bash
uv run pytest -q
```

Expected: `154 passed` (150 + 4). Zero failures.

**Step 6 — commit:**

```bash
git add src/forge/scheduler.py tests/test_scheduler.py
GIT_AUTHOR_DATE="2026-09-13T12:00:00+05:30" GIT_COMMITTER_DATE="2026-09-13T12:00:00+05:30" \
  git commit -m "feat: add recursive graph scheduler with planner subgraph expansion"
```

**Done when:** 4 scheduler tests pass, full suite is 154 passed, and the commit exists.

**If it fails:**
- `AttributeError` on `subgraph` → check `NodeResult` in `graph.py` has the
  `subgraph: GraphRunResult | None` field.
- `to_taskgraph` raises `max_depth` → you are passing the whole graph instead
  of a single-level graph of non-planner nodes only.
- Circular import error → `scheduler.py` may import `fleet.py`; `fleet.py`
  must NOT import `scheduler.py`.

---

### Task 2 — Judge-as-routing (RoutingDecision changes what runs next) — ✅ DONE

> **Status:** implemented in `src/forge/scheduler.py`, tests in
> `tests/test_routing.py` (commit `cff30e6`). Kept below as the design record.

**Objective:** a judge node evaluates another node's result and returns a
`RoutingDecision`; the scheduler honors `retry` by re-running the node once,
and records `escalate`/`stop` as terminal with evidence.

**Files:**
- Modify: `src/forge/scheduler.py`
- Create: `tests/test_routing.py`

**Step 1 — write the failing test.** Create `tests/test_routing.py`:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from forge.graph import GraphSpec, NodeSpec
from forge.scheduler import GraphScheduler


def _specialist(node_id: str = "s1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id, node_type="specialist", title="work",
        goal="do work", acceptance=["done"],
    )


def _judge(node_id: str = "j1", deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        node_id=node_id, node_type="judge", title="judge",
        goal="judge the work", acceptance=["decision"], deps=deps or ["s1"],
    )


def _runner(status: str):
    return SimpleNamespace(
        run=lambda req: SimpleNamespace(
            status=status, session_id="s", worktree=None,
            artifact_exists=True, verification_passed=True,
            classification=SimpleNamespace(value=status),
            reason="scripted",
        )
    )


def test_judge_continue_keeps_scheduler_flow(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return _runner("passed")

    def judge(node, result):
        return {"decision": "continue", "reason": "looks good"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=runner_factory,
        judge=judge,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-ok")
    assert report.status == "passed"


def test_judge_retry_reruns_node_once_then_stops(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return _runner("failed")

    def judge(node, result):
        return {"decision": "retry", "reason": "flaky"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=runner_factory,
        judge=judge,
        max_retries=1,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-retry")
    assert report.status == "failed"
    # specialist ran twice: original + one retry
    specialist_runs = [call for call in calls if call.endswith(":s1")]
    assert len(specialist_runs) == 2
```

**Step 2 — run it and watch it fail:**

```bash
uv run pytest -q tests/test_routing.py
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'judge'`.

**Step 3 — implement.**
Add to `GraphScheduler.__init__`: `judge=None` and `max_retries: int = 1`.
Implement exactly:

1. After a judged node (`NodeSpec` with `deps` pointing at another node and
   `node_type == "judge"`) runs, call `self.judge(node, node_result)` if provided.
   The callable returns a dict with `decision` and `reason`.
2. Validate the decision against `("continue", "retry", "reroute", "escalate", "stop")`;
   an unknown decision raises `ValueError`.
3. `continue` → normal flow. `retry` → re-run the dependency node exactly once
   per judge (respect `max_retries`), then continue with the retry result.
4. `escalate`/`stop` → mark the judged node `blocked`, record reason, continue
   with remaining independent nodes (do not crash).
5. Record a ledger event `routing_decision` with `node_id`, `decision`, `reason`.

**Step 4 — run tests:**

```bash
uv run pytest -q tests/test_routing.py tests/test_scheduler.py
```

Expected: `6 passed`.

**Step 5 — full suite:** `uv run pytest -q` → expect `156 passed`.

**Step 6 — commit** (same backdating pattern as Task 1, message
`feat: judge-as-routing with bounded retry`).

**Done when:** 6 tests pass, suite 156, commit exists.

**If it fails:**
- Judge never called → confirm the judge node has `deps=["s1"]` so the
  scheduler can identify which node it judges.
- Infinite retries → you ignored `max_retries`; the retry budget is
  **once per judge**, not a loop.

---

### Task 3 — Memory fabric at the graph level — ✅ DONE

> **Status:** implemented in `src/forge/scheduler.py` (commit `b62d57d`);
> tests in `tests/test_scheduler_memory.py`. Read this section as the
> **corrected design record** — the two pitfalls below were real bugs found
> by controlled end-to-end verification, and reintroducing either is a
> regression.

**Final design (what is implemented):**

1. Before expanding a planner node, the scheduler recalls from the fabric:
   `recalled = memory.recall(query=node.goal, limit=5)` and records a
   `memory_recall` ledger event. **No family filter is passed** (see Pitfall 1).
2. The rendered recall block is injected into the planner callable. A planner
   that declares a second parameter receives it
   (`def planner(node, memory_context) -> GraphSpec`); a one-argument planner
   keeps working unchanged (detected with `inspect.signature`, never a
   try/except on TypeError).
3. After the planner's subgraph completes, an `outcome` observation is written
   for the planner node, and a `memory_write` ledger event is recorded.
4. Judge nodes write a `decision` observation (family = judged node) after
   routing; each graph level writes a graph-level `outcome` observation.
5. Work nodes keep using `FleetController`'s task-level recall/write — the
   scheduler does not duplicate it.

**Pitfall 1 — never filter recall by an instance id.** The first
implementation passed `task_family=node.node_id` (and `task_id` in the fleet)
as if an instance id were a task family. A run could then only ever recall its
own past attempts and **never context written by other nodes or earlier runs**
— the exact opposite of the fabric's purpose. Recall at injection time is
semantic across the whole fabric; the `task_family` filter remains available
for targeted lookups only. Regression tests:
`test_scheduler_recall_crosses_run_boundaries`,
`test_controller_recall_crosses_family_boundaries`.

**Pitfall 2 — observations must carry the goal text.** The first observation
descriptions were `task <id> passed: <reason>` and `graph <id> passed: N nodes`
— semantically empty, so no later query could match them. Every write site now
includes the goal (or graph rationale), bounded to 160 chars. Regression tests:
`test_scheduler_graph_observation_recalls_by_goal`,
`test_controller_outcome_observation_recalls_by_goal`.

**DONE when:** ✅ 5 new tests pass; full suite 168 passed at commit
`b62d57d`.

**Do not:** invent a second memory API (`MemoryAdapter` is the only interface);
re-add the family filter to recall; write observations without goal text.

---

### Task 4 — Graph persistence and resume — ✅ DONE

> **Status:** implemented (commit `e78e754`), tests in
> `tests/test_scheduler_resume.py`. Verified with a two-process scenario: a
> crash mid-build left s1/s3 passed; a fresh scheduler + fresh ledger resumed,
> re-ran only s2, and finished passed.
> **Known limitation:** resume covers work nodes; planner re-expansion is not
> checkpointed yet (a resumed run re-expands planners).

**Objective:** a crashed scheduler run can be resumed without duplicating nodes.

**Files:**
- Modify: `src/forge/ledger.py` (add a `graph_nodes` table)
- Modify: `src/forge/scheduler.py` (checkpoint per node)
- Create: `tests/test_scheduler_resume.py`

**Steps:**

1. Write tests that:
   - run a graph, kill it after one node (use a runner that raises on the
     second node), then call `scheduler.run(graph, graph_id=..., resume=True)`
     and assert the first node is **not** re-executed (count runner calls).
2. Implement: mirror the existing `task_attempts` pattern exactly:
   - table `graph_nodes(run_id, node_id, status, session_id, artifact_path,
     updated_at, PRIMARY KEY(run_id, node_id))`;
   - `ensure_graph_node(...)`, `update_graph_node(...)` (compare-and-set),
     `get_graph_node(...)`;
   - on `resume=True`, skip nodes already recorded `passed`.
3. Full suite green, commit `feat: durable graph node checkpoints and resume`.

**Done when:** resume test passes; a resumed node executes exactly once across
both runs.

**Do not:** reuse `task_attempts` for graph nodes — different identity space.

---

### Task 5 — Learning on graph runs — ✅ DONE

> **Status:** implemented (commit `bc965e5`), tests in
> `tests/test_scheduler_learning.py`. Verified adversarially: a hook returning
> "passed" cannot change any node status or the graph verdict. Sibling fix:
> `FleetController` hook exceptions previously left the run non-terminal; now
> recorded as `reflection_error` with the run always closing.

**Objective:** a failed graph run produces a candidate observation that feeds
the existing learning gate. No new gate logic.

**Files:**
- Modify: `src/forge/scheduler.py`
- Create: `tests/test_scheduler_learning.py`

**Steps:**

1. Write tests that:
   - run a graph where a specialist fails;
   - pass `learning_hook: Callable[[GraphRunResult], list[str]]` to the scheduler;
   - assert the hook is called once with the failed result and its returned
     candidate ids are recorded as a `reflection` ledger event
     (`candidate_only`).
2. Implement: call the hook after `graph_completed` when the run status is
   `failed`; record the event with the same payload shape
   `FleetController` uses (`{"candidate_count": n, "status": "candidate_only"}`).
3. Full suite green, commit `feat: graph-level learning hook`.

**Critical rule:** the hook may only return candidate ids. It must never be
able to mark a node passed. If your code lets a hook change node status, the
test suite will not catch it — but it is still wrong. Do not do it.

**Done when:** hook test passes; full suite green.

---

### Task 6 — Live Supermemory adapter — ✅ DONE

> **Status:** implemented (commit `130d086`), tests in
> `tests/test_supermemory_adapter.py`. Fail-loud verified against an
> unreachable port with the real client. **Not yet connected to the live
> service** — endpoint shapes are flagged for verification against the
> Supermemory docs before a real deployment uses them.

**Objective:** a real backend behind `MemoryAdapter`, with the local stub as
the fallback when unconfigured.

**Files:**
- Create: `src/forge/supermemory_adapter.py`
- Create: `tests/test_supermemory_adapter.py`

**Steps:**

1. Write tests that use a fake HTTP client (no network) and assert:
   - `write(observation)` issues exactly one request and returns None;
   - `recall(query=..., limit=...)` maps the response into `Observation`
     objects and respects `limit`;
   - a missing API key yields a clear error (`ValueError("SUPERMEMORY_API_KEY is not configured")`),
     never a silent success;
   - transport failure raises `MemoryTransportError` — it must not return an
     empty tuple pretending nothing was found.
2. Implement `SupermemoryAdapter` with:
   - constructor `SupermemoryAdapter(api_key: str | None = None, base_url: str = "http://localhost:6767", client=None)`;
   - `api_key` from env `SUPERMEMORY_API_KEY` when not passed;
   - `write` / `recall` / `profile` as in `MemoryAdapter`;
   - all HTTP through an injectable client so tests never hit the network.
3. Full suite green, commit `feat: Supermemory adapter behind the memory protocol`.

**Done when:** adapter tests pass with zero network calls; unconfigured mode
fails loudly.

**Do not:** read credentials from files or log them, ever.

---

### Task 7 — AO specialist execution — ✅ DONE

> **Status:** implemented (commit `28544b8`), tests in
> `tests/test_scheduler_ao.py`. `TaskSpec.tools` now carries node tool
> declarations through the bridge; the inherited verification rule is guarded
> at the scheduler level. **Live AO remains blocked** — the daemon was not
> running during this build and the OpenCode worker no-op blocker is unchanged.

**Objective:** a specialist node can run through AO (the existing
`AORunner` boundary) instead of the test runner.

**Files:**
- Modify: `src/forge/scheduler.py`
- Create: `tests/test_scheduler_ao.py`

**Steps:**

1. Write tests using the existing fake-AO patterns in
   `tests/test_ao_runner.py` (read it first, do not reinvent the fakes):
   - a specialist node with `tools=["ao"]` dispatches through the AO runner;
   - worker `status="passed"` **without** `artifact_exists`/`verification_passed`
     stays `failed` (`unverified_worker_pass`) — the scheduler inherits this
     rule from `FleetController`, it does not relax it.
2. Implement: when the node's `tools` contains `"ao"`, build the request via
   `AORunRequest` with the node's goal/acceptance and a bounded runtime; keep
   `FleetController` as the executor underneath.
3. Full suite green, commit `feat: AO-backed specialist nodes`.

**Done when:** both tests pass; no claim of live AO success is made anywhere
unless a real session was observed and read back.

---

## 5. Verification checklist (run after every task)

```bash
uv run pytest -q            # zero failures; count only goes up
python3 -m py_compile src/forge/*.py
git diff --check            # no whitespace errors
uv run forge graph /tmp/forge-graph-sample-goal.json   # still ok: true
```

All four must pass. If any fails, stop and fix before committing.

## 6. Common failure modes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: forge.xxx` | file not created or wrong path | confirm path is `src/forge/xxx.py` |
| `ImportError: cannot import name` | circular import | never import `scheduler` from `fleet`/`memory`/`graph` |
| Test passes before you implement | you are testing existing behavior | tighten the assertion to the new behavior |
| Suite count goes **down** | you deleted or broke a test | revert, re-read the task |
| `ValidationError` on `NodeSpec` | `node_type` or `edge_type` not in the allowed list | use values from `graph.py` only |
| Ledger test sees old events | reused a `run_id` | every test uses a unique run id |
| `to_taskgraph` raises `max_depth` | passing a multi-level graph to the single-level executor | only pass single-level graphs |
| Planner recalls nothing across runs | recall filtered by an instance id used as a "task family" | never pass `task_family=node.node_id` / `task_id` to recall at injection time — recall is semantic across the fabric |
| Recall returns hits but the text can't match later goals | observation description lacks the goal text | every write site must carry the goal/rationale, bounded to 160 chars |
| Judge never fires | judge node has no `deps`, or the judge callable wasn't passed | give the judge node `deps=[<judged node>]` and pass `judge=` |

## 7. Glossary (exact meanings used in this repo)

- **Goal** — user intent, validated as `GoalSpec`.
- **Graph** — a `GraphSpec`: typed nodes + typed edges.
- **Node** — one unit of work with a `node_type`; may expand into a subgraph.
- **Edge** — the rule connecting nodes (`gate` = downstream only runs if upstream passed).
- **Observation** — one structured memory entry written by a node.
- **Recall** — fetching relevant observations for a node before it runs.
- **Verifier** — the only authority allowed to mark work passed.
- **Candidate** — a proposed skill; never trusted until the gate validates it.
- **Gate** — the deterministic promotion check (applicability + A/B + held-out).
- **Artifact** — the file a node must produce; must be fresh, never stale.
- **Ledger** — the SQLite event record; the authoritative evidence store.

## 8. Non-goals for this build plan (do not build)

- A web UI, dashboard, or TUI.
- A marketplace of agents.
- Model training or fine-tuning.
- Multi-tenant hosting.
- Replacing AO, Neatlogs, or Supermemory with home-grown versions.

These are deliberately out of scope. Building them now is a failure mode,
not progress.

---

## 9. Next work (not in this plan)

All seven planned tasks are merged (full suite **193 passed**). What is
genuinely still open, in priority order:

1. **Live AO worker completion (blocker).** The AO daemon was not running at
   the end of this build, and the earlier live OpenCode worker produced no
   artifact (no_op). Until a real worker produces a fresh, independently
   verified artifact, no autonomous-completion claim is allowed. Investigate
   worker-side (prompt shape, ACP session, model/tool availability) — not more
   controller logic.
2. **Planner checkpointing.** `resume=True` covers work nodes only; a resumed
   graph re-expands its planners. Store the expanded subgraph spec so resume
   can skip re-expansion.
3. **Real judge implementations.** Judge nodes accept any callable returning a
   decision. The deterministic judge used in tests is a stub; an LLM judge
   (evidence sufficiency, tool choice, plan quality) is the next layer — and it
   must stay constrained by the same `continue/retry/reroute/escalate/stop`
   vocabulary plus deterministic policy around it.
4. **Verify the Supermemory adapter against the live service.** Endpoint
   shapes follow the documented pattern but have only been exercised against a
   fake client. Wire `build_memory_adapter()` into the CLI/scheduler entry
   points and read back a real write/recall.
5. **Wire the scheduler into the CLI.** `forge graph` compiles a graph, but
   nothing runs it end-to-end from the CLI yet. Add `forge run-graph
   <goal.json>` that builds a scheduler with the selected memory backend.
6. **Second harness** (Codex or Claude Code) installed + smoke-tested, then a
   transfer run: same goal, fresh harness, validated playbook recalled from the
   fabric. This is the cross-harness proof point and it is still unproven.


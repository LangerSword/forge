# Forge Project Journal

This is the durable human-readable record of important discoveries, setbacks,
decisions, workarounds, and evidence. It exists for debugging, evaluator
trust, and the final pitch/demo narrative.

**Rule:** an entry records what actually happened. Hypotheses are labeled as
hypotheses. Metrics come from observed runs only. Temporary chatter and
secrets do not belong here.

---

## 2026-09-06 — Initial architecture boundary

- **Type:** decision
- **Status:** observed
- **Agents/harnesses:** AO, OpenCode, Hermes
- **Scope:** overall Forge architecture

### What happened

AO was installed and healthy, but its live supported/authorized catalog did not
include Hermes. OpenCode was installed and authorized, and AO had a `forge`
project plus an OpenCode orchestrator session.

### Evidence

- AO `/healthz`: `status=ok`
- AO `/readyz`: `status=ready`
- AO `/api/v1/agents`: OpenCode was the only installed/authorized agent
- AO project: `forge`
- AO session: `forge-1`, harness `opencode`
- OpenCode version: `1.18.25`
- Hermes version: `0.20.6`; `hermes doctor` passed

### Interpretation / root cause

AO currently provides the execution/worktree/supervision plane. Hermes cannot
honestly be presented as an AO worker without an adapter that does not exist in
the live catalog.

### Decision or action

Use AO/OpenCode for implementation. Use Hermes as a reflection specialist via a
bounded JSON inbox/outbox. Forge itself owns verification and promotion gates.

### Impact

- **Product/runtime:** clear authority boundary; no fake harness integration.
- **Evaluation:** cross-harness transfer requires a second AO-authorized
  harness; Hermes reflection is a separate condition.
- **Pitch/demo:** "AO executes, Hermes reflects, Forge validates."

### Pitch clip

> "We didn't pretend every agent was interchangeable. AO owns execution,
> Hermes proposes what the fleet should remember, and Forge decides whether
> that lesson actually works."

---

## 2026-09-06 — AO worker no-op on first implementation task

- **Type:** setback
- **Status:** observed; investigated
- **Agents/harnesses:** AO `forge-2`, OpenCode
- **Scope:** first schema/capture implementation slice

### What happened

AO spawned worker session `forge-2` on branch `ao/forge-2/root` with a scoped
implementation prompt. The session initially became idle without changing
files. A second explicit `ao send` transitioned it to `working`, but it again
ended idle with a clean worktree and no tests.

### Evidence

- Session: `forge-2`
- Worktree: `/home/lakshaya/.ao/data/worktrees/forge/forge-2`
- Branch: `ao/forge-2/root`
- Final status: `idle`, display `Awaiting PR`
- `git status --short`: empty
- `git diff --name-only`: empty
- `pytest`: `no tests ran`
- AO prompt file existed at `.ao/data/prompts/forge-2/system.md`
- OpenCode session records existed, but no implementation artifact was
  produced in the AO worktree

### Interpretation / root cause

**Unresolved hypothesis:** AO/OpenCode accepted the session and prompt routing,
but the worker's active turn did not produce an edit. The installed AO
surface exposes session state but not enough transcript detail in the CLI
response to identify whether this was a model/provider exit, prompt dispatch
issue, or session lifecycle issue.

### Decision or action

Do not claim AO implemented the task. Preserve the no-op as a real failure
signal. Continue locally with the same scoped implementation while retaining
AO as the execution integration under investigation.

### Impact

- **Product/runtime:** AO worker monitoring needs a stronger completion
  criterion than `status=idle`; clean worktree plus no artifact must be a
  failed/no-op result.
- **Evaluation:** no-op worker attempts belong in the failure corpus; they must
  not become successful trials.
- **Pitch/demo:** this is useful evidence for self-healing: Forge must detect
  silent/no-op agents rather than trusting a finished session status.

### Follow-up

- **Owner:** Forge controller/integration
- **Next verification:** run a minimal AO worker task that must create one
  known file; inspect OpenCode/AO transcript and session events.
- **Status:** unresolved

### Pitch clip

> "Our first worker appeared finished, but produced nothing. The system caught
> the difference between an idle session and a verified artifact—exactly the
> failure mode our evaluator is designed to expose."

---

## 2026-09-06 — Local fallback produced verified capture slice

- **Type:** milestone / workaround
- **Status:** resolved for local slice
- **Agents/harnesses:** local Forge, Chromium, pytest
- **Scope:** schemas and rendered Drawably benchmark boundary

### What happened

Because the AO worker produced no artifact, the schema and rendered-capture
slice was implemented locally without committing. The implementation uses the
installed Chromium binary and explicitly rejects source-clone operations.

### Evidence

- `uv run pytest -q`: `4 passed`
- Real Chromium command against `https://drawably.dev/` completed
- Captured DOM artifact size: `377322` bytes
- DOM contained: `drawably`, `Done`, `Retry`, `your name`
- Chromium stderr: `0` bytes
- Artifacts: `.forge/captures/drawably-rendered-repro-v1/`

### Decision or action

Use rendered observation only for the reproducibility benchmark. Do not clone,
fetch, or inspect the target source repository. Keep dynamic hand-drawn regions
as masked/tolerant visual-eval regions.

### Impact

- **Product/runtime:** first capture boundary is real and testable.
- **Evaluation:** target behavior can be compared without source leakage.
- **Pitch/demo:** demonstrates reproducibility as an outcome-eval problem,
  not a repository-copying problem.

### Pitch clip

> "The agent was given what a user can observe—not the target repository. It
> has to reconstruct the interface from rendered evidence and prove the result
> through behavior, geometry, and visual checks."

---

## 2026-09-06 — No-commit operating policy

- **Type:** decision
- **Status:** observed
- **Agents/harnesses:** project workflow
- **Scope:** repository changes during design and setup

### What happened

The user requested that we stop committing every update and commit only
important milestones.

### Decision or action

Keep implementation and research changes local and uncommitted until a
meaningful runnable milestone is verified. Before any future commit, report the
intended file set and milestone scope.

### Impact

- **Product/runtime:** faster iteration and easier rollback during the
  exploratory stage.
- **Evaluation:** prevents unverified scaffolding from being presented as a
  completed milestone.
- **Pitch/demo:** journal preserves the story even while Git history remains
  focused.

### Pitch clip

> "We kept the evidence trail separate from the release history: failed
> experiments remain visible, while commits represent verified milestones."

---

## 2026-09-06 — AO bootstrap must be self-contained

- **Type:** decision
- **Status:** resolved
- **Agents/harnesses:** AO, OpenCode, Forge controller
- **Scope:** worker initialization and package setup

### What happened

The `forge-2` AO worktree was created from the last committed repository
state. It could not see the uncommitted local `pyproject.toml`, `src/forge`
scaffold, or test dependencies. The worker then attempted to repair packaging
inside its worktree but produced malformed TOML twice.

### Evidence

- AO worktree: `/home/lakshaya/.ao/data/worktrees/forge/forge-2`
- Worktree base: committed revision `1ca57c4`
- Local main checkout had additional uncommitted runtime files
- First repair: TOML parse error at `package-dir`
- Second repair: TOML parse error at `- pydantic`
- Final worker state: terminated after bounded repair attempts

### Decision or action

Use **option 2**: the next AO task is a self-contained bootstrap worker. It
must create the minimal valid package metadata, install/sync its dependencies,
run a smoke test, and only then implement feature code. No milestone commit is
required before that bootstrap task; the worker must be able to establish its
own environment from the committed base.

Required bootstrap exit checks:

1. `pyproject.toml` parses successfully.
2. `uv sync --dev` succeeds.
3. `uv run python -c "import forge"` succeeds.
4. `uv run pytest -q` runs and reports an explicit result.
5. The worker reports exact exit codes and changed files.

### Impact

- **Product/runtime:** AO workers become reproducible from the repository
  state they actually receive.
- **Evaluation:** environment/bootstrap failure is separated from feature
  failure.
- **Pitch/demo:** shows the fleet learning an operational lesson from a real
  failed worker rather than hiding the failure.

### Follow-up

- **Owner:** Fleet Controller
- **Next verification:** spawn a fresh AO bootstrap worker from the current
  committed base and independently rerun all five exit checks.
- **Status:** pending

### Pitch clip

> "Our first worker could not see local uncommitted setup. Instead of making
> the controller depend on hidden machine state, we taught every worker to
> bootstrap and verify its own environment before doing product work."

---

## 2026-09-06 — Bootstrap contract passes after controller-assisted repair

- **Type:** milestone / workaround
- **Status:** observed
- **Agents/harnesses:** AO worktree `forge-2`, OpenCode worker, Forge controller
- **Scope:** isolated package bootstrap and schema test slice

### What happened

After the worker produced two malformed `pyproject.toml` repairs, the
controller corrected the isolated worktree directly. The corrected package
metadata uses PEP 621 project dependencies, a uv dependency group for pytest,
and a valid Hatchling `src/forge` wheel target. The controller also fixed the
Pydantic alias configuration and the test import path.

### Evidence

- AO worktree: `/home/lakshaya/.ao/data/worktrees/forge/forge-2`
- `uv sync --dev`: exit `0`
- `uv run python -c 'import forge; print(forge.__version__)'`: exit `0`
- Import output: `0.0.0`
- `uv run pytest -q`: exit `0`
- Test result: `3 passed in 0.08s`
- Worktree remains uncommitted: `pyproject.toml`, `src/`, `tests/`, `uv.lock`

### Interpretation / root cause

The bootstrap contract is valid. This is **not** evidence that the worker
independently repaired the task: the final successful edits were controller-
assisted after the worker's failed repairs.

### Decision or action

Keep option 2. The next worker task may use this bootstrap pattern, but its
bootstrap edits and verification must be independently attributable. The
controller must not silently convert direct repairs into worker success.

### Impact

- **Product/runtime:** the isolated AO worktree can now install, import, and
  test the benchmark slice.
- **Evaluation:** bootstrap success and worker autonomy remain separate
  dimensions in the ledger.
- **Pitch/demo:** shows transparent recovery rather than claiming autonomous
  self-healing where the controller had to intervene.

### Pitch clip

> "The environment eventually became healthy, but the controller had to
> repair two malformed agent-generated package files. We count that as
> recovery with intervention—not autonomous success—and preserve the exact
> distinction in the evidence trail."

---

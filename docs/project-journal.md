# Forge Project Journal

This is the durable human-readable record of important discoveries, setbacks,
decisions, workarounds, and evidence. It exists for debugging, evaluator
trust, and the final pitch/demo narrative.

---

## 2026-09-14 — Agent design principles from razorpay-agent vs ZapAI post-mortem

- **Type:** design decision
- **Status:** committed to spec
- **Scope:** architecture, agent rules, learning contract

### What happened

Compared our prior razorpay-agent (dual-agent commerce, LinUCB bandit, gated money path, in-memory state, property-fuzzed gate, YC-themed React frontend) against ZapAI by lviffy (WhatsApp-native agentic commerce with real Shopify/Razorpay/WhatsApp integrations, Neon PG, Redis, Gemini 2.5 Flash, 43 tests, 93 commits, full merchant dashboard).

### Evidence

- **razorpay-agent:** 127 commits, real Razorpay order→payment link→paid, 20k gate fuzzed 0 violations, LinUCB bandit, pure CSS zero UI libraries, keyless stub fallback, no persistence, no external webhooks
- **ZapAI:** 93 commits, 10 Razorpay API modules, Shopify OAuth/catalog sync, WhatsApp Cloud API, Neon PG, Redis locks, 43 passing tests, Next.js 15 dashboard, onboarding wizard, multi-tenant credentials, 8-stage cryptographic audit ledger, RFC 8785, Ed25519

### Interpretation / root cause

razorpay-agent's strength was safety formalism (property-fuzzed gate, clean LLM/money separation, principled bandit). ZapAI's strength was product completeness (real integrations, real persistence, real multi-tenant onboarding, more tests). Neither project did both well. The gap was not conceptual — it was execution: ZapAI connected to real systems while we kept everything in-memory and stubbed.

### Decision or action

Integrated 10 agent design principles into SPEC.md §13 and architecture.md:

1. Real integrations > conceptual elegance
2. Persistence is non-negotiable
3. LLM drives reasoning within guardrails
4. Safety + integrations (not either/or)
5. Multi-tenant from day one
6. Frontend is the product
7. Inventory locking is real
8. Cryptographic audit trails are compliance infrastructure
9. Scope = end-to-end journey
10. Tests cover integration scenarios

Version bumped 0.1.4 → 0.1.5.

### Impact

- **Architecture:** these principles now constrain every future Forge design decision
- **Evaluation:** any Forge agent or integration work is measured against these tenets
- **Honesty:** we explicitly recognize where razorpay-agent fell short (persistence, integrations, scope) rather than claiming it was "complete"

### Pitch clip

> "Forge was designed after a head-to-head post-mortem of two Razorpay buildathon entries — ours, which optimized for safety formalism, and ZapAI's, which optimized for integrations. Forge is the synthesis: real connections, real persistence, real safety."

**Rule:** an entry records what actually happened. Hypotheses are labeled as
hypotheses. Metrics come from observed runs only. Temporary chatter and
secrets do not belong here.

---

## 2026-09-08 — Hard runtime and live AO boundary audit

- **Type:** milestone / blocker
- **Status:** observed
- **Agents/harnesses:** Forge controller, AO daemon, OpenCode, local verifier
- **Scope:** AO spawn/readback, fleet resume, artifact freshness, liveness, task checkpoints

### What happened

Forge's hard-runtime path was extended beyond the initial fake-backed controller:
independent verifier authority is mandatory for pass, stale artifacts are rejected
by content fingerprint, real AO `spawned session <id>` output is parsed, AO Git
worktrees are discovered from observed `ao/<session>/root` branches, nested AO
activity timestamps are normalized, successful sessions are cleaned up, fleet
budgets stop polling, and task attempts persist typed SQLite checkpoints with
compare-and-set transitions. Candidate learning now has evaluator-owned
applicability, A/B, and held-out gates plus durable skill verdict records.

Four bounded live AO attempts were made against the healthy local daemon. The
first two exposed non-atomic spawn output and were reconciled without claiming
success; later attempts recovered real sessions and worktrees, but OpenCode
produced no changed files or requested artifact even after one bounded nudge.
Forge classified the worker as `no_op`, terminated it, and persisted the failure.

### Evidence

- `uv run pytest -q`: `102 passed`
- live AO health/readiness: `status=ok`, `status=ready`
- live authorized harness: OpenCode only
- live session recovery: `forge-11` / `forge-12` observed with isolated worktrees
- final live run: `fleet-c10318abd7:goal`
- final task verdict: `status=failed`, `classification=no_op`, `reason=no changed files after one nudge`
- final AO readback: session `forge-12`, `status=terminated`, `activity=exited`
- final checkpoint: attempt `1`, `state=failed`, `session_id=forge-12`, `verification_passed=false`, no artifact digest

### Interpretation / root cause

The controller/runtime boundary is now evidence-preserving and avoids duplicate
workers, false passes, stale artifacts, and leaked sessions. The remaining live
failure is downstream: AO/OpenCode creates and runs the worker session but does
not produce the bounded artifact in this environment. This is an observed
worker liveness/no-op blocker, not evidence that Forge completed the task.

### Decision or action

Do not add automatic retries or broaden permissions. Keep the live blocker
explicit. The next integration step is to inspect AO/OpenCode's own session
prompt/ACP path or run one manually approved minimal worker task through the AO
surface, then repeat the same artifact/verifier contract. No cross-harness claim
or autonomous-completion claim is made.

### Impact

- **Runtime:** Forge can now safely own a fleet lifecycle around real AO sessions,
  including recovery and cleanup, even when the worker fails.
- **Learning:** reflection/evaluation remains downstream of verified outcomes;
  this failed live run must not generate a validated skill.
- **Product claim:** the agent/controller implementation is real and tested;
  end-to-end AO artifact-producing success remains unverified.

### Pitch clip

> "Forge does not turn a live AO session into a success badge. It records the
> session, finds the real worktree, verifies a fresh artifact, nudges once, and
> kills a no-op worker when the evidence never arrives."

---

## 2026-09-07 — Forge agent/controller runtime slice

- **Type:** milestone
- **Status:** observed
- **Agents/harnesses:** local Forge controller, fake AO runner contracts, pytest
- **Scope:** `src/forge/fleet.py`, `src/forge/schema.py`, `src/forge/ledger.py`, `src/forge/cli.py`

### What happened

Forge gained its first bounded agent-runtime slice above the AO worker plane.
The controller accepts a strict `GoalSpec`, validates a dependency-aware
`TaskGraph`, assembles a fenced task-scoped `ContextPackage`, schedules
independent ready tasks up to `max_parallel`, records task verdicts in the
SQLite ledger, blocks dependent tasks after failure, and invokes a candidate
learning hook only after the run reaches a terminal state. `forge plan` and
`forge fleet --dry-run` expose the contract without spawning a worker.

### Evidence

- `uv run pytest -q tests/test_fleet.py tests/test_ledger_terminal_status.py`: `10 passed`
- `uv run pytest -q`: `70 passed`
- `uv run forge plan /tmp/forge-agent-goal.json`: schema-valid `forge.task-graph.v1`
- `uv run forge fleet /tmp/forge-agent-goal.json --dry-run`: terminal `planned` report
- concurrency regression: two independent ready tasks reached peak active workers `2`
- failure regression: runner exception closed the fleet run as `failed` with a terminal verdict event

### Interpretation / root cause

The repository previously had AO runner, verifier, ledger, watchdog, and
reflection primitives, but no top-level controller that made Forge itself an
agent responsible for a fleet run. This slice closes that architectural gap
without duplicating AO's worktree or process supervision.

### Decision or action

Keep AO as the execution/worktree plane. Forge now owns goal intake, bounded
task scheduling, context packaging, run lifecycle, evidence, and the handoff
to reflection/gating. Hermes remains an optional bounded reflection sidecar,
not an AO worker.

### Impact

- **Product/runtime:** Forge is no longer described only as a passive learning
  layer; it has a controller runtime that can own a bounded fleet run.
- **Evaluation:** live AO artifact-producing completion and cross-harness
  transfer remain unverified and are not implied by these local tests.
- **Pitch/demo:** "Forge is the agent that runs the fleet, verifies the work,
  and only then decides what the fleet may learn."

### Follow-up

- **Owner:** Forge controller/integration
- **Next verification:** run the controller against one explicitly approved
  tiny AO task and read back the artifact plus independent verifier result.
- **Status:** open

### Pitch clip

> "We moved Forge from a learning sidecar into the agent runtime itself: it
> accepts the goal, schedules bounded workers, verifies artifacts, and feeds
> only candidate evidence into learning. AO still owns the worker process; Forge
> owns the outcome."

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

## 2026-09-14 — Graph + memory refactor (0.2.0)

- **Type:** milestone / refactor
- **Status:** observed (tests only; no live worker run claimed)
- **Agents/harnesses:** Forge core, pytest (local)
- **Scope:** `src/forge/graph.py`, `src/forge/memory.py`, `src/forge/fleet.py`,
  `src/forge/cli.py`, `tests/test_graph.py`, `tests/test_memory.py`,
  `tests/test_fleet.py`

### What changed

- Added a typed execution graph: `NodeSpec` (planner / specialist / judge /
  verifier / reflector / evaluator / memory / aggregator), `GraphSpec` with
  bounded `max_parallel`/`max_depth`, typed edges (sequence, dependency, gate,
  parallel, judge), `compile_goal_graph()` and a `to_taskgraph()` bridge that
  rejects multi-level graphs loudly.
- Added the context fabric: `Observation`, the `MemoryAdapter` protocol
  (`write` / `recall` / `profile`), a deterministic `LocalMemoryStub`, and a
  bounded `render_recall`.
- Wired memory into `FleetController`: each task recalls into a fenced
  `<MEMORY_CONTEXT>` block before execution and writes an `outcome` observation
  after its verdict; `memory_recall` / `memory_write` ledger events are
  recorded. With `memory=None` behavior is unchanged.
- Added `forge graph <goal.json>` for graph readback.

### Evidence

```text
uv run pytest -q  →  150 passed (was 122; +28 new tests)
python3 -m py_compile  →  ok
git diff --check  →  clean
uv run forge graph /tmp/forge-graph-sample-goal.json  →  ok: true, node_count 2
```

### Interpretation

This is a structural refactor verified by tests. It does **not** include a
recursive scheduler, judge routing, or a live Supermemory backend — those are
specified as Tasks 1–7 in `docs/BUILD.md`. No live AO completion is claimed.

### Impact

- **Product:** the graph and memory vocabulary now exist in code, not only in
  planning documents; every later feature has a typed seam to plug into.
- **Build:** `docs/BUILD.md` lets a non-frontier model continue the build with
  exact steps, expected outputs, and failure modes.
- **Evidence honesty:** all claims remain test-scoped; the live AO blocker and
  the unconfigured Supermemory backend are stated as open.

---

## 2026-09-14 — Execution layer built (0.2.1): scheduler, judge routing, memory, resume

- **Type:** milestone / build
- **Status:** observed (193 tests; no live worker run claimed — AO daemon was down)
- **Agents/harnesses:** Forge core, pytest (local)
- **Scope:** `src/forge/scheduler.py`, `src/forge/supermemory_adapter.py`,
  `src/forge/ledger.py` (graph_nodes), `src/forge/schema.py` (TaskSpec.tools),
  `src/forge/graph.py`, `src/forge/fleet.py`, six new test files

### What was built

All seven tasks from `docs/BUILD.md`:

1. **Recursive scheduler** — planner nodes expand into subgraphs, bounded by
   `max_depth`; work nodes still execute through `FleetController` so the
   verification authority is unchanged.
2. **Judge-as-routing** — a judge node evaluates its dependency and returns
   `continue / retry / reroute / escalate / stop`; retry re-runs the judged
   node within a bounded budget; escalate/stop block it with the reason
   preserved. Verified end-to-end: a first-attempt failure was recovered into
   a passing graph purely through the judge's retry decision.
3. **Memory fabric at graph level** — planner recall, judge decision
   observations, graph-level outcomes, and `memory_recall`/`memory_write`
   ledger events; one-arg planners unchanged, two-arg planners receive the
   rendered recall block.
4. **Durable checkpoints + resume** — `graph_nodes` table with compare-and-set
   transitions; `resume=True` reuses nodes checkpointed as passed. Verified
   across a fresh process: a crash mid-build re-ran only the unfinished node.
5. **Learning hook** — runs only on failed graphs, after the graph closes;
   candidates only, never able to change a verdict (verified adversarially).
6. **Supermemory adapter** — protocol-conformant backend with fail-loud
   contracts; backend chosen explicitly via `build_memory_adapter()`.
7. **AO tool declarations** — `TaskSpec.tools` carries node declarations
   through the bridge; the unverified-worker rule is guarded at scheduler level.

### Two bugs found by controlled verification (fixed at the root)

- **Cross-run recall was impossible.** Recall filtered by an instance id used
  as a "task family" (`node_id` / `task_id`), so a run could only ever recall
  its own past attempts. Fixed at both call sites; regression tests added.
- **Observations were unmatchable.** Descriptions lacked the goal text
  (`task <id> passed: completed`), so later semantic queries could never find
  them. All write sites now carry the goal/rationale, bounded to 160 chars.

Sibling fix: a raising learning hook left `FleetController` runs stuck in
`running`; exceptions are now recorded as `reflection_error` and the run always
reaches a terminal state.

### Evidence

```text
uv run pytest -q → 193 passed (150 at 0.2.0; +43)
Commits: 028cdc7, cff30e6, b62d57d, e78e754, bc965e5, 130d086, 28544b8
Controlled checks: cross-run recall, judge-retry recovery, two-process resume,
adversarial learning hook, unreachable-backend fail-loud
```

### Interpretation

The graph engine the plan described now exists and is tested: typed nodes,
recursive expansion, judge routing, a memory fabric that carries context
across runs, durable resume, and a bounded learning hook. Everything is
deterministic — no LLM judge, no live memory service, no live AO worker.

### Impact / what stays open

- Live AO completion is **still blocked** (daemon was down; the OpenCode no-op
  worker was never resolved). No autonomous-completion claim is made.
- The Supermemory adapter is exercised against a fake client only.
- Cross-harness transfer remains unproven.
- Next work is listed in `docs/BUILD.md` §9.

---

## 2026-09-14 — Reverted: fabricated accuracy domain (0.2.2)

The `accuracy.py` module added earlier today applied the agent-accuracy-grading
skill to an **invented commerce scenario domain** (minimum discounts, add-on
shares, cart values) lifted from the skill's razorpay-project session
reference. That domain is not Forge's; the module graded nothing Forge had
built. Removed entirely (module, tests, CLI command, docs). The methodology
remains applicable and is re-applied to Forge's own verdict-producing
components instead. No history rewrite — a removal commit.

---

## 2026-09-14 — Deterministic review of Forge's own verdict systems (0.2.3)

- **Type:** milestone / evaluation harness
- **Status:** observed (205 tests; deterministic oracles, no LLM judge; re-runnable)
- **Agents/harnesses:** Forge core, pytest (local)
- **Scope:** `src/forge/review.py`, `tests/test_review.py`, `forge review` CLI

### What was built

`src/forge/review.py` applies the agent-accuracy-grading methodology
(Scenario Gen → system-under-test → grading fn → summary) to Forge's own
verdict-producing components. The correct verdict for every case is COMPUTED
from the inputs plus the documented rule (an oracle), never judged by an LLM:

- **`gate_suite`** — 1800 cases sweeping the promotion gate's
  `evaluate_candidate` boundaries: below/at/above every threshold, negative
  trial counts, held-out missing/regression, <3 evidence refs, anon candidates.
- **`verify_controller_verdicts`** — the controller's verifier-authority truth
  table (worker status × fresh artifact × independent verification); a worker
  pass counts only with both.
- **`routing_suite`** — judge decision × retry budget through the *real*
  scheduler: continue / retry (budget respected) / escalate / stop / invalid,
  cross-checked against `expected_routing_outcome`.

`run_review` persists every case and a per-dimension summary to the ledger with
failure detail; `forge review` exits nonzero unless every dimension is 100%.

### Bugs found by building the grader (all fixed at the root)

- **`all_dimensions_100` was constant `False`.** `_summary` folded
  `failure_count` (a raw count) into the same dict it ANDed to 1.0, so a
  perfect suite was reported as failing and `run_review` always marked the run
  `failed`. The flag is now computed over scored dimensions only.
- **Non-idempotent suites.** Child executions wrote `verdict-N` / `routing-N`
  runs into the *project* ledger, so a second `forge review` raised
  `run already exists: verdict-1` and stale `graph_id` state made routing
  retries fail. Child executions now run under a scratch root; the command is
  re-runnable and the project ledger stays clean.
- **Oracle/table mismatch on the invalid-decision case.** The suite scored
  judged/graph as failing for the `raises` contract, which no correct
  implementation could satisfy; the contract is now scored as declared.
- **Vacuous fail-detection test.** The regressed-gate test iterated `None`
  failures and asserted a substring the failure message never contained; it now
  guards `None` and asserts the real message.

### Evidence

```text
uv run pytest -q → 205 passed (12 new), green on repeat runs
forge review --run-id review-cli-A → ok: true, all 3 suites 100%, exit 0 (x2)
negative control: refs rule disabled → all_dimensions_100 False, 288 failures detected
positive control: real gate → all_dimensions_100 True
```

### Interpretation / what stays open

The grader is the infrastructure §9 item 3 needs: when a real (LLM) judge
lands, it plugs into the routing suite and its decisions are measured against
the same deterministic oracle. Live AO completion and cross-harness transfer
remain unproven.

---

## 2026-09-15 — Live AO autonomous completion verified (ao-live-smoke-20260915-v2)

- **Type:** milestone / live proof point
- **Status:** observed (two bounded live spawns; one clean `passed` verdict)
- **Agents/harnesses:** AO daemon (ready, `:3001`, pid 36164), opencode worker
  (chat mode), Forge `AORunner` + watchdog + verifier authority
- **Scope:** `evals/results/live-smoke-2026-09-15.json`, `.forge/ao-surface.json`
  `forge_daemon`, ledger runs `ao-live-smoke-20260915` / `-v2`

### What was proven

The blocked "AO autonomous execution" proof point landed:

1. Daemon ready; Forge resolves the live daemon binary via `/proc`
   (after the `resolve_binary` gating fix, commit `c0d53ec`).
2. Spawn: exact payload recorded (prompt redacted), exit 0, session
   `forge-14`, worktree discovered via branch match
   `refs/heads/ao/forge-14/root` → `.ao/data/worktrees/forge/forge-14`.
3. Bounded work: polls 1–4 `working/active`, artifact absent; poll 5
   `docs/SMOKE.md` exists, fingerprint fresh.
4. Independent verification: content check (SMOKE + date, bounded size) —
   `verification_passed: true`.
5. Watchdog: `working` → `passed` ("artifact and independent verification
   passed"); cleanup kill with reason `verified_artifact`; final verdict
   `passed`. ~11.5s spawn-to-verified. Session `exited/terminated`.

### The v1 lesson: the grader must be able to see its own errors

Attempt 1 (`forge-13`) produced the **byte-identical fresh artifact**
(same sha256) — the worker was correct. But the one-off verifier called
`Path.read_text(timeout=5)`; `Path.read_text()` takes no `timeout` kwarg, so
every call raised `TypeError` and the `except` swallowed it to `False`. The
runner faithfully reported `verification_passed: false` on all 40 polls and
killed at poll budget. Manually reading the artifact showed the correct
content. Root cause: swallowed exception in the verifier, not the agent, the
runner, or AO. Fixed (`read_text()`), re-ran as v2, clean pass. Same class as
the skill's pitfall list: a silent grader failure reads as an agent failure.

### Evidence

```text
evals/results/live-smoke-2026-09-15.json  → status passed, verification true
ledger runs ao-live-smoke-20260915(-v2)   → full event traces
.forge/ao-surface.json forge_daemon       → payload + completion signal
AO session forge-14                       → exited, isTerminated true
```

### What stays open

Cross-harness transfer (only opencode authorized), multi-worker fleet runs,
live Supermemory backend. No claims beyond one bounded autonomous completion.

## 2026-09-15 — Unified harness policy: variance pinned by construction (0.2.4)

- **Type:** milestone / policy layer
- **Status:** observed (227 tests; live rejection smoke vs real daemon)
- **Agents/harnesses:** Forge core, pytest, AO daemon (rejection smoke)
- **Scope:** `src/forge/harness_policy.py`, `tests/test_harness_policy.py`,
  `ao_runner.py`/`ao_cli.py` wiring, `review.py` policy suite,
  `.forge/harness-policy.json`

### Decision

Cross-harness transfer was replaced by a unified harness with explicit
guardrails. Cross-harness kills A/B confounds by measurement (second
environment); the policy kills them by construction (declared pins). For a
single-operator project that will never run a second CLI, construction is
the honest answer: every C0/C2 comparison becomes trustworthy because model,
harness, mode, and bounds are identical by pinning, not by hope. The
portability claim survives as a design property (harness-agnostic
`ContextPackage`/skill format), not a measured one.

### What was built

- `HarnessPolicy` — pinned opencode harness; explicit model allowlist
  (provider prefixes + `None` default so model-variant A/B stays first-class
  INSIDE the policy); chat-only session interface; poll/runtime bounds.
- `validate_request` — rejects violations loudly BEFORE any spawn touches
  the daemon; `policy_hash` pins comparability, recorded in the ledger as
  `policy_check` next to the actual spawn flags.
- `AORunRequest.model` + `AOCLI.spawn(--model)` — the documented AO
  per-session override, threaded through both spawn call sites.
- `review.py` fourth suite — `policy_suite` grades the contract (11-case
  boundary sweep against an oracle table) AND its enforcement order:
  violations must raise before spawn, observed via a recording CLI seam
  (`runner_factory(cli, client)`); a late-validating runner is DETECTED
  (violating model reached spawn), regression-tested.
- `.forge/harness-policy.json` — the declared contract, readable, hashed
  (`6630d9005689faf5` at this revision).

### Evidence

```text
uv run pytest -q → 227 passed (8 new: 12 policy + suite + wiring tests)
live rejection smoke (real daemon): model 'totally-sketchy-model' rejected
  with HarnessPolicyError BEFORE spawn; sessions before == after (zero
  sessions created)
policy file loads: harness opencode, models ('nvidia/', 'deepseek/',
  'local-lmstudio/', None), hash 6630d9005689faf5
```

### Bugs found while building (root-caused, not stacked)

- The `model` knob dead-ended in `AORunRequest` — `run()` never passed it to
  `spawn_command`/`spawn`; both call sites now thread it.
- First `policy_suite` design observed spawns only through an injected
  runner object (unobservable for regressed implementations); redesigned to
  `runner_factory(cli, client)` so spawn is always observable through the
  suite's recording CLI.

### What stays open

Model-variant A/B through the policy (next experiment), live Supermemory
backend, multi-worker fleet runs. Cross-harness transfer is retired as a
measured claim, not an open blocker.

## 2026-09-15 — Model-variant A/B through the harness policy (0.2.5)

- **Type:** milestone / experiment capability
- **Status:** observed (236 tests; live CLI runs — clean + rejection)
- **Agents/harnesses:** Forge core, pytest, local executor (live CLI)
- **Scope:** `experiment.py`, `model_ab.py`, `cli.py`, `evals/goals/model-ab-trial-v1.json`

### What was built

The §9 next experiment is now executable: **model-variant A/B** — same
harness (opencode, pinned), different allowlisted model, skill vs no-skill.

- `LearningExperiment` gains `baseline_model`/`candidate_model`/`policy`:
  both model conditions are validated against the policy BEFORE any trial
  executes (violating model → fail loud, zero trials), and a
  `model_condition` event (both models + `policy_hash`) is recorded to the
  ledger.
- `ModelABExecutor` (`src/forge/model_ab.py`) — the AO-backed executor:
  each trial is a bounded spawn through the real runner under the policy;
  unique run ids (`run_prefix:case_id:attempt`); verifier authority
  unchanged (fresh artifact + independent verifier required for a pass).
- CLI: `forge experiment <id> <goal.json> --model-baseline <m>
  --model-candidate <m>` — policy enforced at the CLI boundary too
  (nonallowlisted model → exit 1, `policy_violation`).

### Evidence

```text
uv run pytest -q → 236 passed (9 new)
forge experiment exp-model-ab-live evals/goals/model-ab-trial-v1.json
  --model-candidate nvidia/abacusai/dracarys-llama-3.1-70b-instruct
  → ok, model_condition {baseline: null, candidate: nvidia/…,
    policy_hash: 6630d9005689faf5}
forge experiment … --model-candidate totally-sketchy-model
  → exit 1, policy_violation: model is not allowlisted (before any trial)
```

### Bugs found while building

- The gate's evidence-refs rule requires >=3 refs: a 1-train/1-heldout
  sweep yields 2 refs → always rejected. The A/B test uses 2 train + 3
  heldout cases so the gate can validate.
- `parse_spawn_output` is fail-loud on empty spawn output (by design);
  fakes must emit a parseable session line.

### What stays open

Running the A/B for real: a live skill-vs-no-skill comparison through
`ModelABExecutor` (bounded AO spawns, both conditions), then the gate
measures the improvement. Supermemory live service, planner
checkpointing, `forge run-graph`, publish-npm fix.

## 2026-09-28 — AO wiring rebuilt: lifecycle owned by Forge, live smoke re-verified (0.2.6)

- **Type:** milestone / integration hardening
- **Status:** observed (258 tests; live headless daemon lifecycle; live bounded smoke)
- **Agents/harnesses:** Forge core, pytest, AO daemon (headless), opencode worker
- **Scope:** `ao_cli.py` (resolution + install), new `ao_daemon.py`, `cli.py`
  (`forge ao ...`), `scripts/ao_live_smoke.py`,
  `evals/results/live-smoke-2026-09-28.json`

### What was broken (three real breaks, found live on 2026-09-28)

1. `resolve_binary()` fell back to `~/.local/bin/agent-orchestrator-linux-x64.AppImage`
   — a path that does not exist (AppImageLauncher moved the app to
   `~/Applications`, hash-suffixed). Daemon down ⇒ every live path failed at
   resolution; a running daemon had masked it via the `/proc` scan.
2. No stable `ao` CLI existed on the machine: it lives only inside the
   running AppImage mount, and `ao doctor` warned it was missing from PATH.
3. Nothing owned the daemon lifecycle; the desktop app was assumed running.
   No headless start was documented — except the hidden `ao daemon` command
   (found by probing the extracted binary; the top-level help does not list
   it), which runs the same backend standalone.

### What was built (tasks 1–5, test-first, each commit gated on green)

- Resolution chain: env → explicit pin → live daemon via `/proc`
  (version-matched to the running daemon) → stable copy → actionable error.
- `forge ao install-cli`: extracts `resources/daemon/ao` from the AppImage to
  `~/.local/bin/ao` (sha256 `d5961fd1…`, app 0.12.11); idempotent, `--force`
  re-extracts; `ao` is now on PATH for workspace hooks.
- `forge ao status|start|stop`: headless daemon lifecycle. Start is detached
  and readyz-polled (log `~/.ao/forge-daemon.log`); stop verifies the
  endpoint actually closes; status works while the daemon is down.
- One `ao_runner_factory` for fleet/experiment wiring (the inline
  `__import__` hack is gone); live `forge fleet` preflights the daemon with
  an actionable error (`--dry-run` unaffected).
- `scripts/ao_live_smoke.py`: the repeatable bounded live proof.

### Evidence

```text
uv run pytest -q → 258 passed (22 new across the five tasks)
forge fleet <goal> (daemon down)  → ok:false, "start it with `forge ao start`" (exit 1)
forge ao start                    → started; daemon ready, :3001, pid 1045959
forge ao status                   → ready (down: stopped)
forge harnesses                   → live catalog (opencode authorized/installed)
uv run python scripts/ao_live_smoke.py → passed; session forge-15;
  docs/SMOKE.md sha256 3bf5f1f1…, content "SMOKE 2026-09-28"; 6 polls,
  ~26.7s spawn-to-verified; cleanup kill verified_artifact
```

### What stays open

The model-variant A/B for real (a live skill-vs-no-skill comparison through
`ModelABExecutor` — built, not yet wired into the CLI experiment path),
`forge run-graph`, the Supermemory live service, and the publish-npm fix
before pushing. The desktop entry `Exec=` still points at the stale
`~/.local/bin/agent-orchestrator-linux-x64.AppImage` (launching AO from the
app menu may fail; the daemon now starts via `forge ao start`).

## 2026-09-28 — Markdown goal ingestion + the forge-tui cockpit (0.2.7)

- **Type:** feature / product surface
- **Status:** observed (269 Python tests; go build/vet/test green; live runs)
- **Agents/harnesses:** Forge core, pytest, Go 1.27, bubbletea/lipgloss/bubbles
- **Scope:** `src/forge/goal_input.py`, `tests/test_goal_input.py`, `cli.py`
  wiring, `tui/`

### Why

Pointing `forge plan` at a human-written plan (a real OMH `.md`) failed twice
over: a relative path died as a bare `FileNotFoundError`, and the absolute
path died as pydantic speaking JSON at a markdown file. Human plans in,
machine graphs out — that is the contract now.

### What was built

1. **Markdown goal ingestion** (`bd80e0a`): deterministic mapping — front
   matter skipped; `Goal`/`Acceptance` sections; `Repo:` / `Harness:` /
   `Artifact:` / `Max minutes:` labels; repo defaults to cwd; harness falls
   back to `.forge/harness-policy.json`; `- [ ]` markers stripped. Fail-loud,
   never a guessed goal. Missing files name the path and the fix.
2. **`tui/` — forge-tui**: Go/bubbletea cockpit over the same JSON CLI
   surface (no second state model): status, runs + run detail (event
   viewport), AO daemon + harnesses, review self-grading, help. Spinner for
   loads, colored status cells, `--dump` snapshot mode for CI/verification.

### Evidence

```text
uv run pytest -q -> 269 passed (11 new)
forge plan <real plan>.md -> ok:true; 11 acceptance items; harness opencode; exit 0
forge plan nope.md        -> "goal file not found ... use an absolute path"
tui: go build OK · go vet OK · go test ok
forge-tui --dump -> live: 106 runs / 88673 events; daemon ok; review all_suites_100=true
pty run -> rendered frame (status page, 27-agent catalog) + clean quit on q
```

### What stays open

Model-variant A/B for real; `forge run-graph`; decision engine (Jev/Kev
contract); TUI next increments (glamour plan viewer, list/table widgets,
in-TUI plan compile). The cockpit's look is pending the user running it.

## 2026-09-28 — bare `forge` opens the cockpit (0.2.8)

- **Type:** UX / entry point
- **Status:** observed (274 tests; live pty run)

An empty invocation now hands the terminal to forge-tui via `os.execv` (no
Python wrapper lingers; signal handling belongs entirely to the TUI).
`forge tui` is the explicit form. Non-interactive contexts get a JSON
`not_a_tty` error naming a subcommand; a missing `forge-tui` names the build
command. Verified live: `cd ~ && forge` renders the status page and exits
clean on `q`; non-tty bare `forge` returns the actionable JSON.

## 2026-09-28 — `forge run-graph` live: goal → typed graph → workers → verified (0.2.9)

- **Type:** orchestration loop / live evidence
- **Status:** observed (graph-7fd57cd4 passed; sessions forge-19/forge-20; 281 tests)

`forge run-graph <goal.json | plan.md>` compiles the goal into its typed graph
(`compile_goal_graph`) and executes it through the recursive `GraphScheduler`
with live AO workers — every node runs behind its own deterministic
verification (`goal.verifier_commands`), and the graph passes only when every
node passes. Markdown plans can now carry verification: the first section whose
heading contains "verification" maps one bullet per command (a backticked span
wins over prose; ≤8 commands, ≤32 tokens each).

**Live proof:** `graph-7fd57cd4` — specialist + verifier nodes → sessions
forge-19 / forge-20; each wrote `docs/QUICKSTART.md` in its own worktree
(253 / 176 words) and passed all four deterministic checks; 2m04s end-to-end.

**Blockers found and fixed on the way:**

1. AO worktrees branch from `origin/main`, and the entire 0.2.x stack was
   unpushed — the first worker saw Sep-7 code, noticed the mismatch, and went
   investigating outside its worktree. Fixed by pushing main (`2e0cc6c..0617ef8`).
2. Headless opencode workers die on permission approvals: any command touching
   a path outside the worktree (even read-only) raises an approval; the session
   pauses (`needs_input`); ACP refuses the watchdog's nudge mid-turn ("turn in
   flight"); the session ends `blocked_hidden`. Cost: forge-16, forge-18.
3. Fix: project config `agentConfig.permissions = "bypass-permissions"` for
   `forge`. Note `ao project set-config` REPLACES the whole config — the first
   flag-only attempt dropped `defaultBranch` and the worker/orchestrator agent
   overrides; restored via a single `--config-json`.

**Follow-up:** the approval endpoint exists
(`POST /api/v1/sessions/{sid}/conversation/approvals/{rid}/resolve`;
allow_once / allow_always / reject). Runner-side handling — detect a pending
approval on `needs_input` and resolve it (deny outside-worktree by default)
instead of nudging into a wall — is the principled follow-up for environments
that keep permission gates on.

## 2026-09-28 (2) — the todo website: first run on a repo of its own making (0.2.10)

- **Type:** live orchestration on a new repo / three fixed blockers
- **Status:** observed — `graph-a40d2605` passed (both nodes); site committed to `~/projects/todo` (`606f1b9`)

`forge run-graph evals/goals/todo-website-v1.md` against `~/projects/todo`
(registered with `ao project add`; a remote-less local repo). `goal` (session
`todo-7`) wrote `index.html` + `styles.css` + `app.js` and passed all six
deterministic checks in 2m41s; `goal-verify` (session `todo-8`) re-produced the
artifact independently and passed in 4m16s; ~7 minutes end-to-end. The two
artifacts carry different hashes — same spec, two workers, two independent
reproductions — and the goal node's copy is what landed in the repo.

Three blockers, root-caused live and now covered by regression tests (284 total):

1. **Remote-less repos have no resolvable default branch** — `ao spawn` fails
   `DEFAULT_BRANCH_UNRESOLVED` unless the repo has a remote or a recorded
   default. Fix: `ao project set-config <id> --default-branch main` (full
   `--config-json`; `set-config` replaces the whole object).
2. **Worktree discovery searched the wrong repo** — `AOCLI.discover_worktree`
   ran `git worktree list` in Forge's cwd, so for any goal repo other than
   `~/forge` the worktree was never found and the watchdog killed healthy
   workers (`working without a worktree past liveness budget`). Fix:
   `discover_worktree(session_id, *, cwd=...)` + `AORunRequest.repo` plumbed
   from `FleetController` (commit `9dee4e4`).
3. **Nudge-then-instant-kill geometry** — the artifact checkpoint killed on
   the very next poll (~1s after the nudge), which no model can act on; the
   checkpoint was also a fixed 90s tuned for tiny tasks. Fix: kill only after
   a full second checkpoint (`2x max_idle_s`), and
   `max_idle_s = max(90, goal.max_minutes x 30)` (commit `5ca38eb`).

**Ops lesson:** a foreground `run-graph` whose wrapper timeout fires leaves an
orphaned worker and a ledger run stuck at `running` (`graph-73b66b26:work:1:goal-verify`
is that artifact). Long-bound runs belong in the background with ledger
collection.

**Observed bonus:** a verifier worker (session `todo-6`) went beyond the
deterministic gate on its own — it built a chromium acceptance harness under
`/tmp/opencode/verify`, found its own harness bugs, and was pinning down
focus/Enter semantics before the orphaned run was stopped. Independent
verification already reaches for a real browser; the typed graph's verifier
node is pointed the right way.

## 2026-09-28 (3) — the cockpit can launch work (0.2.11)

- **Type:** TUI control surface / live findings
- **Status:** observed (pty-verified: launched `quickstart-doc-v1.md` from
  page 3, streamed `forge-21`, verdict rendered, clean exit on `q`)

`forge` → page **3 orchestrate**: goal files from `evals/goals/`, enter launches
`forge run-graph` as the same CLI a human runs; the page then streams the live
run (node rows, event tail, final verdict) off `forge runs` / `forge run` JSON
on a 2s ticker. 3 Go tests added.

Two live findings while exercising it:

1. **Edit-tasks trip the freshness gate.** A todo-site fix run (session
   `todo-9`, launched by the user from `~`) edited `app.js`/`styles.css` for
   ten minutes — real fixes for real bugs (dead checkbox clicks, edit-focus
   loss) — but the checked artifact `index.html` never changed, so
   `stale_artifact` held for 358 polls and the run stopped at the 600s runtime
   budget. The fixes are preserved: `~/.ao/data/worktrees/todo/todo-9`
   (uncommitted, `+64/-11`, syntax-checked). The correct fix is verification
   design for edit tasks (behavioral checks/tests — todo plan phase 5), not a
   looser freshness rule; `artifact_fresh or changed_files` would rubber-stamp
   unverified edits.
2. **One `ao spawn` TimeoutExpired** under load (verify node of the
   pty-verified run) — retry/backoff on spawn is the follow-up.

Ops note: runs launched from `~` keep their ledger in `~/.forge`; the cockpit
(root `~/forge`) shows the forge ledger. Run from `~/forge`, or launch page 3.

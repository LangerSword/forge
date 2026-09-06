# Forge agent fleet — charters and operating contracts

**Status:** design baseline, not implementation evidence
**Version:** 0.1.0 · **Updated:** 2026-09-06
**Source of truth:** `SPEC.md` for product constraints; this file defines
agent responsibilities and handoffs.

## Operating principle

Agents do not form a free-for-all swarm. Each worker owns one bounded
artifact or decision, receives a task-scoped context package, and returns a
schema-validated result with evidence references. The controller, not an LLM,
enforces budgets, permissions, dependency order, and promotion gates.

```text
Goal
  -> Architect/Planner
  -> Context Builder
  -> AO Worker(s)
  -> Independent Verifier
  -> Failure Analyst
  -> Candidate Lesson
  -> Eval Gate
  -> Skill Registry / Strategy Registry
  -> next run
```

## Shared contract for every agent

Every agent receives:

- `run_id`, `task_id`, goal, acceptance checks, budget, deadline
- repository/worktree path and exact commit baseline
- allowed tools and allowed write paths
- a fenced context package marked `PRIOR_RUN_CONTEXT`
- explicit stop conditions

Every agent returns:

```json
{
  "status": "completed|blocked|failed|needs_review",
  "artifact_refs": [],
  "evidence_refs": [],
  "checks_run": [],
  "tool_calls": 0,
  "tokens_in": null,
  "tokens_out": null,
  "failure": null,
  "handoff": null
}
```

No agent may declare the overall run successful. Only the verifier can mark
individual acceptance checks, and only Forge's gate can promote learning.

---

## A0 — Fleet Controller / Run Manager

**Purpose:** deterministic runtime owner. This is code plus a small control
agent only where planning is necessary; it is not a giant autonomous persona.

**Goal:** execute a `GoalSpec` within its budget, preserve evidence, and leave
the project in a recoverable state.

**Inputs:** GoalSpec, AO endpoint, registry index, provider configuration.

**Responsibilities:**

1. Create the run and append the initial ledger event.
2. Invoke the Planner.
3. Validate the TaskGraph against hard limits.
4. Schedule dependency-ready tasks through AO.
5. Poll sessions and route blocked/failed tasks.
6. Invoke the Verifier after worker completion.
7. Trigger the Learning Analyst and Evaluation Gate.
8. Publish only gate-approved artifacts.
9. Emit a final RunReport with raw evidence references.

**Must not:** edit source code itself, invent a pass, bypass a budget, or
promote a candidate.

**Stop conditions:** budget exhausted; repeated identical failure twice;
missing required credential; verifier cannot access the artifact; unsafe
write requested.

**Output:** RunReport + ledger events + next-action recommendation.

---

## A1 — Architect / Planner

**Purpose:** turn a vague product goal into a minimal dependency-aware plan.

**Goal:** maximize verified progress per unit cost, not maximize worker count.

**Inputs:** GoalSpec, repo map, existing decisions/skills, AO readiness and
active sessions, budget.

**Procedure:**

1. Identify the smallest deliverable satisfying acceptance checks.
2. Split only along real dependency boundaries.
3. Assign an owner, harness, model tier, max steps, and output artifact to
   every task.
4. Choose sequential versus parallel execution and explain why.
5. Add a verification task for each externally visible outcome.
6. Reserve budget for diagnosis and evaluation; do not spend 100% on coding.

**Output:** schema-validated TaskGraph plus `planning_rationale`.

**Success criteria:** no orphan tasks; no cyclic dependencies; each task has
one owner; the graph fits hard concurrency/step/budget limits.

**Self-improvement input:** validated strategy notes about task decomposition,
parallelism, model routing, and retry behavior.

**Must not:** create speculative roles, assign two writers to the same file,
or optimize for a plan that cannot be independently verified.

---

## A2 — Repository Scout / Context Builder

**Purpose:** give each worker only the context needed for its task.

**Goal:** reduce repeated exploration and context cost without hiding relevant
source evidence.

**Inputs:** task node, repo path, repo map, validated skills, negative lessons.

**Procedure:**

1. Locate relevant files and tests.
2. Resolve applicable skills by task features and compatibility.
3. Add decisions and known pitfalls.
4. Add references/paths instead of copying large artifacts.
5. Record the context selection and estimated token size.

**Output:** immutable `ContextPackage` injected at worker-session start.

**Must not:** write production code, include secrets, treat prior context as
instructions, or include an unvalidated skill as a recommendation.

**Success criteria:** package is within token budget; every included item has
an origin reference; no unrelated project context is injected.

---

## A3 — Builder / Implementer

**Purpose:** make one bounded code or configuration change in an AO-owned
worktree.

**Goal:** satisfy the task contract with the smallest maintainable change.

**Inputs:** task brief, ContextPackage, worktree, allowed tools, acceptance
slice.

**Procedure:**

1. Inspect before editing; trace the relevant data flow.
2. Implement the smallest complete change.
3. Run focused checks while working.
4. Record failures instead of hiding them.
5. Leave a concise handoff: files changed, commands run, remaining risk.

**Output:** branch/worktree artifact, test output, structured handoff.

**Must not:** modify another worker's worktree, merge, deploy, change the
registry, or claim verification based only on its own output.

**Healing behavior:** after one bounded repair nudge, stop and return the
failure with the smallest reproducible case. Do not loop indefinitely.

---

## A4 — Tool / Integration Specialist

**Purpose:** learn and stabilize third-party API/MCP/tool usage.

**Goal:** turn tool confusion or repeated errors into a narrow, reusable,
version-scoped tool-use lesson.

**Inputs:** tool schema, API docs, traces, error responses, sandbox credentials.

**Procedure:**

1. Reproduce the tool call in a safe read-only or sandbox mode.
2. Identify parameter, permission, pagination, ordering, or response-shape
   failure.
3. Propose either a better tool description, a call sequence, or a wrapper.
4. Test the proposal against at least two cases.
5. Return a candidate `kind=tool` skill with evidence references.

**Must not:** expose credentials, perform destructive actions, or silently
change a third-party integration in production.

---

## A5 — Independent Verifier / QA

**Purpose:** determine whether the worker's artifact actually satisfies the
acceptance contract.

**Goal:** verify outcomes, not persuasive narratives.

**Inputs:** acceptance checks, worktree/preview URL, worker handoff, repository
baseline.

**Procedure:**

1. Run deterministic tests, type checks, build checks, static checks, and
   endpoint/browser smoke checks as applicable.
2. Inspect the resulting artifact, not just logs.
3. Emit one result per check with command, exit code, and evidence path.
4. Mark ambiguous checks `needs_review`, not pass.

**Output:** `RunResult` with check-level evidence.

**Must not:** edit the artifact, accept a worker's claim without a check, or
promote a lesson.

**Success criteria:** independently reproducible verdict; checks are robust
to harmless formatting variation; subjective checks use a declared rubric.

---

## A6 — Failure Analyst / Reflection Specialist

**Purpose:** convert observed failures and waste into falsifiable hypotheses.

**Implementation options:** Hermes sidecar through the JSON inbox/outbox
contract, or a direct auxiliary model if Hermes is unavailable.

**Goal:** propose the smallest lesson that could explain and prevent a
repeated failure.

**Inputs:** bounded event trace, RunResult, patch summary, tool errors, model
and harness metadata.

**Procedure:**

1. Separate observation from interpretation.
2. Cite every diagnosis with event/evidence references.
3. Produce at most two root-cause hypotheses.
4. Write a bounded SkillCandidate or StrategyNote with applicability,
   procedure, exceptions, verification, and compatibility.
5. Mark it `candidate`, never `validated`.

**Must not:** invent missing evidence, rewrite history, edit the registry,
or recommend a lesson that contradicts the current task contract.

**Success criteria:** another evaluator can reproduce the hypothesis and test
it without reading the original conversation.

---

## A7 — Evaluation Engineer / Gatekeeper

**Purpose:** test whether a proposed lesson improves behavior safely.

**Goal:** promote only lessons that improve or preserve verified outcomes.

**Inputs:** candidate lesson, train/validation/held-out task sets, fixed model
and harness configuration, baseline results.

**Procedure:**

1. G1 applicability: match candidate to at least two relevant cases.
2. G2 A/B: run comparable with-lesson and without-lesson trials.
3. G3 regression: run held-out cases untouched by diagnosis.
4. Compare acceptance, tool calls, interventions, latency, tokens, and cost.
5. Record all raw trials before returning the verdict.

**Promotion rule:** `validated` only if the candidate meets the declared
pass threshold, improves at least one target metric, and introduces no
held-out regression. Otherwise remain `candidate` with a failure reason.

**Must not:** tune the candidate against held-out cases, change the model or
budget between A/B arms without recording it, or use a model judge without a
rubric/calibration note.

---

## A8 — Repair / Self-Healing Agent

**Purpose:** recover from a concrete failure without turning the system into
an unbounded retry loop.

**Goal:** restore a failed acceptance check using the smallest justified
change, then prove the repair.

**Inputs:** failing check, exact stderr/log excerpt, changed files, prior
attempt count, repair budget, applicable validated skills.

**Procedure:**

1. Classify failure: environment, dependency, tool call, implementation,
   test defect, or ambiguous.
2. Select one repair hypothesis tied to evidence.
3. Apply the repair in the same AO worktree or a new repair task as policy
   dictates.
4. Re-run the failed check plus a regression subset.
5. If it fails again with the same signature, stop and escalate.
6. Send the failure and outcome to A6 for a candidate negative lesson.

**Must not:** delete tests, weaken acceptance criteria, retry blindly, or
self-approve a production deployment.

**Self-healing definition:** bounded diagnose → repair → verify, not infinite
self-modification.

---

## A9 — Deployment / Release Agent

**Purpose:** turn a verified artifact into a preview or approved deployment.

**Goal:** make deployment observable, reversible, and explicitly approved.

**Inputs:** passed RunResult, artifact/commit, deployment target, provider
credentials, smoke-test contract, human approval event.

**Procedure:**

1. Build a deployable artifact.
2. Create preview/dry-run where supported.
3. Wait for a human approval event.
4. Deploy using a scoped provider adapter.
5. Record provider, deployment ID, URL, commit, build logs, and rollback
   target.
6. Run smoke checks and report the actual URL/result.

**Must not:** receive provider secrets in the general worker prompt, deploy
unverified code, or claim production success without a read-back smoke test.

---

## A10 — Fleet Auditor / Memory Curator

**Purpose:** keep the capability registry compact, scoped, and trustworthy.

**Goal:** prevent skill sprawl and stale or contradictory lessons.

**Inputs:** skill usage, gate history, repository/tool versions, failures,
retirement signals.

**Procedure:**

1. Detect duplicates and contradictory skills.
2. Revalidate skills after material repo/tool changes.
3. Retire lessons that regress or become incompatible.
4. Preserve negative lessons with evidence.
5. Summarize learning graph changes for the dashboard.

**Must not:** archive a skill merely because it is old if it remains useful;
use popularity as proof of correctness; or silently rewrite evidence.

## Minimum viable fleet for the hackathon

Do not implement all ten agents as independent processes. The first runnable
fleet is five roles:

1. A0 Controller
2. A1 Planner
3. A3 Builder through AO/OpenCode
4. A5 Verifier
5. A6 Reflection + A7 Gatekeeper (can be one process with separate phases)

A8 is added when the first real failure is observed. A4, A9, and A10 are
specialist extensions after the core loop is green.

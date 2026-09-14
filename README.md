# Forge — a commander agent with verified, cumulative learning

**Syndicate by Maximor · Track 1: Automated Agent Engineering**

Forge compiles a goal into a **typed execution graph**, runs it as a bounded
fleet of specialist agents, carries context between handoffs through a shared
**memory fabric instead of raw transcripts**, and promotes only capabilities
that **measurably improve independently verified outcomes**.

Give it a goal, a repo, third-party tools, and a budget. Forge's target loop
plans, executes through [Agent Orchestrator](https://aoagents.dev) workers,
verifies the output, and **learns what it just proved**. Only lessons that
survive an A/B gate become portable skills; a fresh worker on a *different
harness* is intended to get the skill, not the conversation — and the
improvement is measured, not claimed.

The current checkout implements the graph and memory layers on top of the
bounded controller runtime: typed `NodeSpec`/`GraphSpec` compilation
(`forge graph`), the `MemoryAdapter` context-fabric protocol with a
deterministic local stub, memory recall/write wiring in the fleet controller,
plus the earlier controller (GoalSpec validation, dependency-aware scheduling,
fenced task context, verifier authority, task checkpoints, deadlines).

Scaffolding for what comes next is written for any model to execute:
`docs/BUILD.md` is a step-by-step plan (recursive scheduler, judge routing,
live Supermemory adapter) with exact tests, expected outputs, and failure
modes.

The current checkout verifies the local learning path, the graph/memory
refactor, and the controller's hard runtime safeguards. A real AO/OpenCode
session was spawned, recovered, and cleaned up, but the worker produced no
requested artifact after one bounded nudge. AO artifact-producing completion
and cross-harness transfer remain open proof points; no autonomous success
claim is made.

## Status and evidence boundary

- **AO autonomous execution — blocked proof:** AO health/readiness, live CLI
  spawn output, session IDs, branch-based worktree discovery, activity
  normalization, bounded nudge/kill, and cleanup are observed. The final live
  worker was a no-op with no artifact, so reliable artifact-producing
  autonomous completion is still unverified.
- **Cross-harness transfer — target:** the portable context-package contract is
  designed for a fresh worker on a different AO harness. Only OpenCode is
  currently observed authorized in AO, so no transfer result is claimed.
- **Hermes — reflection sidecar:** Hermes is external to AO. It reads bounded
  run evidence and may propose candidate skills or strategy notes; Forge, not
  Hermes, owns the promotion gate. Hermes is not presented as an AO worker.
- **Neatlogs — verified scope:** the SDK integration, local Doctor,
  authenticated probe, and readback of a real `forge openai-smoke` trace are
  verified for the OpenAI smoke/diagnostic path. This does not prove full AO
  worker or fleet trace coverage.
- **Supermemory — protocol implemented; backend planned:** the context-fabric
  contract (`MemoryAdapter`: write / recall / profile) and a deterministic
  `LocalMemoryStub` are implemented and wired into the fleet controller. A live
  Supermemory backend is not yet configured or read back; until it is, the
  local `.forge` registry, ledger, and stub remain authoritative.
- **Deterministic review — verified scope:** `forge review`
  (`src/forge/review.py`) grades Forge's own verdict systems against
  independent, code-computed oracles — the promotion gate (1800-case boundary
  sweep), the controller verifier-authority truth table, and the judge-routing
  matrix — with per-case failure detail in the ledger. It exits nonzero unless
  every dimension is 100%, is re-runnable, and detects a deliberately regressed
  gate rather than re-grading it green. This grades Forge's decision systems;
  it is not an LLM judge and proves nothing about live AO completion.

The tracked C0 submission report records a failing baseline and a passing
bounded repair, plus a `candidate` skill artifact; it explicitly does not claim
cross-domain or cross-harness transfer.

## The problem

Agent fleets are great at one-shot work and bad at accumulating experience.
Every session starts from zero: the API quirk discovered at 2am, the
orchestration choice that saved an hour, the tool sequence that actually
works — all trapped in a transcript nobody re-reads. More harnesses and more
agents make this worse, not better.

## What we built

Forge is the agent/controller runtime above AO, with learning and evidence as
first-class planes:

- **Agent/controller** — owns GoalSpec intake, dependency scheduling, bounded
  fleet lifecycle, and terminal run reports
- **Planner** — goal → task graph, with deterministic budget/harness guardrails
- **Context builder** — fenced, task-scoped context packages: repo map, decisions, and
  only *validated* skills (references, not copies)
- **Executor** — AO worker adapter (worktrees, PR/CI stay AO's); the
  current spawn/lifecycle contract is still unverified
- **Verifier** — independent-model acceptance checks; the only component that
  can mark a run passed
- **Learning loop** — observe → diagnose → candidate skill → **gate**
  (applicability + A/B benefit + held-out no-regression) → publish or reject
- **Economics** — per-run token/$/wall-time ledger; cost-per-verified-outcome
  including the skill that earned it
- **Evidence dashboard** — "what did it learn" drill-down: source trace →
  skill → gate results → later use

### Where Hermes fits

AO's current live catalog authorizes OpenCode only, and AO does not expose a
Hermes worker adapter. Hermes is therefore Forge's sidecar reflection
specialist: it analyzes bounded run evidence and proposes candidate skills or
strategy notes. Forge—not Hermes—runs the promotion gate, so reflection is
never mistaken for verified learning or autonomous execution.

## What improved across iterations

*(populated by `evals/results/` — baseline C0 vs learning-enabled C2,
cross-harness transfer run; raw run JSON in `evals/results/`)*

| Condition | Acceptance pass | Tool calls | Wall time | Cost |
|---|---|---|---|---|
| C0 baseline (no learning) | — | — | — | — |
| C2 + validated skills | — | — | — | — |

The table stays unpopulated until comparable C0/C2 runs and the transfer
condition have observed evidence. Do not replace the dashes with estimates.

## How to run

```bash
# 1. setup
cp .env.example .env      # add credentials only for an enabled path
uv sync

# 2. one run
python -m forge.cli run evals/goals/<goal>.json --condition C0

# 3. grade Forge's own verdict systems (deterministic oracles, no LLM judge)
python -m forge.cli review

# 4. dashboard
python -m forge.cli dashboard
```

## Product surfaces and deployment

Forge is packaged as a project-local Python CLI plus a local web dashboard;
it is not a second Kanban competing with AO. The target topology has AO
supervise workers and worktrees, while Forge owns the ledger, learning gate,
evidence, and deployment policy. In the current checkout, AO readiness is
observed but autonomous Forge spawn and lifecycle completion are not yet
verified. A future TUI will call the same API rather than introduce another
state model.

For generated web apps, the delivery path is explicit:

```text
build → verify → preview → human approval → deploy → smoke test → URL
```

The Forge product site is packaged as `@llangersword/forge@3.1.1` and is deployed
to Vercel at [web-rust-three-63.vercel.app](https://web-rust-three-63.vercel.app/).
It is a static product/docs/support site, not a live AO tracker or hosted Forge
backend. The public npm package installs the `forge` executable:

```bash
npm install @llangersword/forge
npx forge --port 4173
```

The first publish is a one-time maintainer action. Once the package exists on
npmjs.com, anyone can install it without logging in. Future releases run from
`.github/workflows/publish-npm.yml` using npm Trusted Publishing and GitHub OIDC.
The unscoped npmjs.com package `forge` is unrelated and is not modified.
No generated app deploys automatically without an approval event.

Full runbook: `SPEC.md` §10 and §15. AO must be running (`ao status`); Forge drives
it over the loopback API recorded in `.forge/ao-surface.json`.

## Evidence and project memory

Important discoveries, setbacks, workarounds, decisions, and verified
milestones are persisted in [docs/project-journal.md](docs/project-journal.md).
Use [docs/journal-template.md](docs/journal-template.md) for narrative entries.
Runtime events go to `.forge/ledger/journal.jsonl` through
`forge.journal.ProjectJournal`; entries require evidence and redact
secret-like fields. This journal is part of the product evidence: it helps
debug rough edges and gives the demo a truthful story of how the fleet learned
from failures.

## Roadmap

1. **Verify autonomous AO execution:** exercise an explicitly approved tiny
   spawn, record the exact payload and completion signal in
   `.forge/ao-surface.json`, and accept only an independently verified artifact.
2. **Prove transfer:** authorize a second AO harness, give it the same bounded
   task/context contract with a validated skill, and report the fresh-worker
   result separately from the OpenCode run.
3. **Keep reflection gated:** Hermes remains a sidecar proposal source; only
   Forge's applicability, A/B, and held-out checks can promote a skill.
4. **Add Supermemory later:** implement and read back an external mirror only
   after the local registry/ledger path is stable.

## How AO was used

AO was used during the build for readiness checks and isolated worker attempts.
OpenCode was the only observed authorized harness. Some bootstrap work was
independently observed, while other attempts were no-ops or controller-assisted;
the Forge autonomous spawn/lifecycle contract therefore remains unverified.
This section is not a claim of end-to-end autonomous execution.

## Stack

Python 3.11 · uv · SQLite ledger · AO daemon (target execution layer; spawn/
lifecycle unverified) · TensorMux inference (`glm-4-7-flash` for workers) ·
Supermemory (future integration) · Neatlogs (verified OpenAI smoke/diagnostic
trace path)

**Docs:** [SPEC.md](SPEC.md) (source of truth, incl. AI working rules §14) ·
[architecture.md](architecture.md) · [docs/yc-positioning.md](docs/yc-positioning.md) ·
[docs/hermes-analysis.md](docs/hermes-analysis.md) · [docs/agent-charters.md](docs/agent-charters.md) ·
[docs/autoresearch-harness-evals.md](docs/autoresearch-harness-evals.md)

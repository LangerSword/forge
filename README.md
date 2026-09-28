# Forge — a commander agent with verified, cumulative learning

**v0.2.11** · every claim in this repo is marked *observed* or *target* — the
journal is the receipt trail: [docs/project-journal.md](docs/project-journal.md)

Forge compiles a goal into a **typed execution graph**, runs it as a bounded
fleet of specialist agents on [Agent Orchestrator](https://aoagents.dev)
workers, carries context between handoffs through a shared **memory fabric
instead of raw transcripts**, and promotes only capabilities that
**measurably improve independently verified outcomes**.

Give it a goal, a repo, and a budget. Forge plans, executes bounded workers in
isolated worktrees, verifies every node with deterministic checks, and
**learns what it just proved** — only lessons that survive an A/B gate become
portable skills, and the improvement is measured, not claimed.

**Start here → [docs/QUICKSTART.md](docs/QUICKSTART.md)** — install the CLI,
bring up the AO daemon, open the cockpit.

## Give it something to do

```bash
forge run-graph evals/goals/quickstart-doc-v1.md    # any .md plan or .json goal
```

One command, the whole loop: goal → compiled typed graph (specialist behind a
verifier gate) → live AO workers in isolated worktrees → per-node
deterministic verification → ledger. The graph passes only if every node
passes, and every event is replayable with `forge run <run_id>`.

**Verified live (2026-09-28):** `graph-7fd57cd4` — sessions `forge-19` /
`forge-20`, each wrote `docs/QUICKSTART.md` in its own worktree and passed
all four deterministic checks; 2m04s end-to-end. That file is in this repo
now, promoted from a worker's worktree after review.

**Or drive it from the cockpit:** bare `forge` → page **3 orchestrate** —
pick a goal file, hit enter, and the same run streams live (node rows,
events, verdict).

## Status and evidence boundary

- **Orchestrated live execution — verified (2026-09-28):** `forge run-graph`
  compiles a goal (JSON or a markdown plan) into its typed graph and executes
  it through the recursive scheduler with live AO workers. Every task runs
  behind its own deterministic verifier (`goal.verifier_commands`); a run
  passes only when every node passes. Markdown plans carry verification: a
  `## Verification` section maps one command per bullet. Live proof:
  `graph-7fd57cd4` (sessions `forge-19` / `forge-20`; 281-test suite green).
- **AO lifecycle — Forge-managed, verified (2026-09-28):** `forge ao
  install-cli|status|start|stop` own the daemon lifecycle (stable CLI at
  `~/.local/bin/ao`; headless `ao daemon`, readyz-polled; stop verifies the
  endpoint closes). Repeatable bounded proof: `scripts/ao_live_smoke.py` →
  session `forge-15`, `docs/SMOKE.md` sha256 `3bf5f1f1…`, `passed`.
- **Cross-harness transfer — retired as a measured claim (0.2.4):** replaced
  by the unified harness policy: variance is pinned by construction (declared
  `HarnessPolicy`, enforced before spawn, `policy_hash` comparability in the
  ledger) rather than measured on a second harness Forge does not run. The
  skill format (`ContextPackage` + validated skills) remains harness-agnostic
  by design, so a transfer run stays one spawn away if a second CLI is ever
  installed.
- **Hermes — reflection sidecar:** Hermes is external to AO. It reads bounded
  run evidence and may propose candidate skills or strategy notes; Forge, not
  Hermes, owns the promotion gate. Hermes is not presented as an AO worker.
- **Neatlogs — verified scope:** the SDK integration, local Doctor,
  authenticated probe, and readback of a real `forge openai-smoke` trace are
  verified for the OpenAI smoke/diagnostic path. This does not prove full AO
  worker or fleet trace coverage.
- **Supermemory — protocol implemented; backend planned:** the context-fabric
  contract (`MemoryAdapter`: write / recall / profile) and a deterministic
  `LocalMemoryStub` are implemented and wired into the fleet controller. A
  live Supermemory backend is not yet configured or read back; until it is,
  the local `.forge` registry, ledger, and stub remain authoritative.
- **Deterministic review — verified scope:** `forge review`
  (`src/forge/review.py`) grades Forge's own verdict systems against
  independent, code-computed oracles — the promotion gate (1800-case boundary
  sweep), the controller verifier-authority truth table, the judge-routing
  matrix, and the harness-policy contract — with per-case failure detail in
  the ledger. It exits nonzero unless every dimension is 100%, is re-runnable,
  and detects a deliberately regressed gate rather than re-grading it green.
  This grades Forge's decision systems; it is not an LLM judge.
- **Not claimed:** fleet-scale results, cross-harness transfer, autonomous
  deployment. Anything not proven above stays a roadmap item.

The tracked C0 learning report records a failing baseline and a passing
bounded repair, plus a `candidate` skill artifact; it explicitly does not
claim cross-domain or cross-harness transfer.

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
- **Planner** — goal → task graph, with deterministic budget/harness
  guardrails; the recursive scheduler expands `planner` nodes into subgraphs,
  bounded by `max_depth`
- **Context builder** — fenced, task-scoped context packages: repo map,
  decisions, and only *validated* skills (references, not copies)
- **Executor** — AO worker adapter: bounded spawn, worktree discovery,
  watchdog (nudge/kill classifications), fresh-artifact enforcement — verified
  live
- **Verifier** — independent acceptance checks; the only component that can
  mark a run passed. Deterministic command checks lead; the model grader never
  overrides a deterministic failure
- **Operator cockpit** — Go/bubbletea TUI (`tui/` → `forge-tui`) reading the
  same CLI JSON surface; bare `forge` opens it
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
strategy notes. Forge — not Hermes — runs the promotion gate, so reflection is
never mistaken for verified learning or autonomous execution.

## What improved across iterations

*(populated by `evals/results/` — baseline C0 vs learning-enabled C2; raw run
JSON in `evals/results/`)*

| Condition | Acceptance pass | Tool calls | Wall time | Cost |
|---|---|---|---|---|
| C0 baseline (no learning) | — | — | — | — |
| C2 + validated skills | — | — | — | — |

The table stays unpopulated until comparable C0/C2 runs have observed
evidence. Do not replace the dashes with estimates.

## How to run

```bash
# 1. setup
cp .env.example .env      # add credentials only for an enabled path
uv sync

# 2. AO lifecycle (once): stable CLI + headless daemon before any live run
uv run forge ao install-cli   # extracts ao to ~/.local/bin/ao (AppImage required)
uv run forge ao start         # readyz-polled; `forge ao status` / `forge ao stop` companion

# 3. one run
python -m forge.cli run evals/goals/<goal>.json --condition C0

# 4. grade Forge's own verdict systems (deterministic oracles, no LLM judge)
python -m forge.cli review

# The unified harness policy (declared in .forge/harness-policy.json) is
# enforced before every spawn: harness pinned to opencode, explicit model
# allowlist, chat-only sessions, bounded polls/runtime.

# 5. dashboard
python -m forge.cli dashboard

# 6. cockpit (Go TUI): build once — then bare `forge` opens it
cd tui && go build -o ~/.local/bin/forge-tui . && forge

# 7. give it something to do — compile a plan, run workers live, verify every node
uv run forge run-graph evals/goals/quickstart-doc-v1.md    # or any .md plan / .json goal
```

## Product surfaces and deployment

Forge is packaged as a project-local Python CLI, a local web dashboard, and a
Go/bubbletea cockpit (`tui/` → `forge-tui`, reading the same CLI JSON
surface — not a second state model); it is not a second Kanban competing with
AO. The target topology has AO supervise workers and worktrees, while Forge
owns the ledger, learning gate, evidence, and deployment policy. In the
current checkout, Forge owns the AO lifecycle
(`forge ao install-cli|start|stop`), and bounded autonomous spawn plus
orchestrated graph runs are verified end-to-end (2026-09-15 / 2026-09-28).

For generated web apps, the delivery path is explicit:

```text
build → verify → preview → human approval → deploy → smoke test → URL
```

The product site is deployed to Vercel at
[web-rust-three-63.vercel.app](https://web-rust-three-63.vercel.app/) — a
static product/docs site, not a live AO tracker or hosted Forge backend. The
npm install path (`@llangersword/forge`) is **pending its first publish**;
until it lands on npmjs.com, install from source — see
[docs/QUICKSTART.md](docs/QUICKSTART.md). The unscoped npmjs.com package
`forge` is unrelated and is not modified. No generated app deploys
automatically without an approval event.

Full runbook: `SPEC.md` §10 and §15. AO must be running (`forge ao start`;
raw `ao status`); Forge drives it over the loopback API recorded in
`.forge/ao-surface.json`.

## Evidence and project memory

Important discoveries, setbacks, workarounds, decisions, and verified
milestones are persisted in [docs/project-journal.md](docs/project-journal.md).
Use [docs/journal-template.md](docs/journal-template.md) for narrative entries.
Runtime events go to `.forge/ledger/journal.jsonl` through
`forge.journal.ProjectJournal`; entries require evidence and redact
secret-like fields. This journal is part of the product evidence: it helps
debug rough edges and gives the project a truthful story of how the fleet
learned from failures.

## Roadmap

1. **Decision-engine slot:** a `DecisionEngine` protocol with a local
   [Kev](https://github.com/jaredpalmer/kev)-class backend first (drop-in
   `/v1/systemone` contract; one env var swaps to a hosted endpoint) — this is
   where judge routing stops being a stub.
2. **Runner-side approval handling:** when a headless worker raises a
   permission request, resolve it from the runner (deny outside-worktree by
   default) instead of letting the session stall; the daemon's resolve
   endpoint is known.
3. **Model-variant A/B, for real:** the prepared
   `evals/goals/model-ab-trial-v1.json` gate has not been run live yet — run
   it and record it.
4. **Prove transfer:** authorize a second AO harness, give it the same bounded
   task/context contract with a validated skill, and report the fresh-worker
   result separately from the OpenCode run.
5. **Add Supermemory later:** implement and read back an external mirror only
   after the local registry/ledger path is stable.

## How AO was used

AO is Forge's execution layer, Forge-managed end-to-end: `forge ao install-cli`
extracts a stable CLI from the Agent Orchestrator AppImage, and
`forge ao start|status|stop` drive the headless daemon (verified live
2026-09-28). OpenCode is the only observed authorized harness. Live runs span
the first bounded completion (`forge-14` / `forge-15`) through orchestrated
graph runs (`forge-19` / `forge-20`, `graph-7fd57cd4`). Workers run in
isolated git worktrees cut from `origin/main`; the `forge` project runs with
`permissions=bypass-permissions` because unbounded interactive approval stalls
headless sessions — root-caused in the journal.

## Stack

Python 3.11 · uv (editable uv-tool install) · SQLite ledger · AO daemon
(Forge-managed lifecycle) · Go/bubbletea cockpit · TensorMux inference
(`glm-4-7-flash` for workers) · Supermemory (future integration) · Neatlogs
(verified OpenAI smoke/diagnostic trace path)

**Docs:** [SPEC.md](SPEC.md) (source of truth, incl. AI working rules §14) ·
[docs/QUICKSTART.md](docs/QUICKSTART.md) ·
[docs/project-journal.md](docs/project-journal.md) ·
[docs/BUILD.md](docs/BUILD.md) · [architecture.md](architecture.md) ·
[docs/agent-charters.md](docs/agent-charters.md) ·
[docs/yc-positioning.md](docs/yc-positioning.md) ·
[docs/hermes-analysis.md](docs/hermes-analysis.md)
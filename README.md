# Forge — a learning layer for agent fleets

**Syndicate by Maximor · Track 1: Automated Agent Engineering**

Give an agent fleet a goal, a repo, third-party tools, and a budget — it
plans, builds through [Agent Orchestrator](https://aoagents.dev) workers,
verifies its own output, and **learns what it just proved**. Only lessons
that survive an A/B gate become portable skills; a fresh worker on a
*different harness* gets the skill, not the conversation — and the
improvement is measured, not claimed.

## The problem

Agent fleets are great at one-shot work and bad at accumulating experience.
Every session starts from zero: the API quirk discovered at 2am, the
orchestration choice that saved an hour, the tool sequence that actually
works — all trapped in a transcript nobody re-reads. More harnesses and more
agents make this worse, not better.

## What we built

Forge is a control plane above AO:

- **Planner** — goal → task graph, with deterministic budget/harness guardrails
- **Context builder** — budgeted context packages: repo map, decisions, and
  only *validated* skills (references, not copies)
- **Executor** — spawns and drives AO workers (worktrees, PR/CI stay AO's)
- **Verifier** — independent-model acceptance checks; the only component that
  can mark a run passed
- **Learning loop** — observe → diagnose → candidate skill → **gate**
  (applicability + A/B benefit + held-out no-regression) → publish or reject
- **Economics** — per-run token/$/wall-time ledger; cost-per-verified-outcome
  including the skill that earned it
- **Evidence dashboard** — "what did it learn" drill-down: source trace →
  skill → gate results → later use

### Where Hermes fits

AO currently executes the coding work through OpenCode. Hermes is used as a
sidecar reflection specialist because AO does not expose a Hermes worker
adapter: it analyzes bounded run evidence and proposes candidate skills or
strategy notes. Forge—not Hermes—runs the promotion gate, so reflection is
never mistaken for verified learning.

## What improved across iterations

*(populated by `evals/results/` — baseline C0 vs learning-enabled C2,
cross-harness transfer run; raw run JSON in `evals/results/`)*

| Condition | Acceptance pass | Tool calls | Wall time | Cost |
|---|---|---|---|---|
| C0 baseline (no learning) | — | — | — | — |
| C2 + validated skills | — | — | — | — |

## How to run

```bash
# 1. setup
cp .env.example .env      # fill in TENSORMUX_API_KEY, SUPERMEMORY_API_KEY, GITHUB_PAT
uv sync

# 2. one run
python -m forge.cli run evals/goals/<goal>.json --condition C0

# 3. dashboard
python -m forge.cli dashboard
```

Full runbook: `SPEC.md` §10. AO must be running (`ao status`); Forge drives
it over the loopback API recorded in `.forge/ao-surface.json`.

## How AO was used

AO ran the build from hour 0: workers, worktrees, PRs, and CI for this repo;
every session is visible in the AO dashboard (screenshot + session count in
the demo video).

## Stack

Python 3.11 · uv · SQLite ledger · AO daemon (loopback HTTP) · TensorMux
inference (`glm-4-7-flash` for workers) · Supermemory (skill mirror) ·
Neatlogs (traces)

**Docs:** [SPEC.md](SPEC.md) (source of truth, incl. AI working rules §14) ·
[architecture.md](architecture.md) · [docs/yc-positioning.md](docs/yc-positioning.md) ·
[docs/hermes-analysis.md](docs/hermes-analysis.md) (how Forge differs from Hermes's built-in learning loop)

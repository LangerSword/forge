# Forge — a learning layer for agent fleets

**Syndicate by Maximor · Track 1: Automated Agent Engineering**

Give an agent fleet a goal, a repo, third-party tools, and a budget. Forge's
target loop plans, executes through [Agent Orchestrator](https://aoagents.dev)
workers, verifies the output, and **learns what it just proved**. Only lessons
that survive an A/B gate become portable skills; a fresh worker on a
*different harness* is intended to get the skill, not the conversation — and
the improvement is measured, not claimed.

The current hackathon artifact verifies a bounded local
failure → repair → reflection → verification path. AO autonomous spawn/lifecycle
and cross-harness transfer are core roadmap targets, not completed claims in
this checkout.

## Status and evidence boundary

- **AO autonomous execution — target:** AO health/readiness and the read-only
  catalog/session surface are observed, but Forge's exact spawn payload and
  reliable worker-completion/lifecycle signal are currently unverified. An
  idle or listed session is not counted as autonomous success.
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
- **Supermemory — future integration:** Supermemory is planned as an external
  skill/context adapter. The local `.forge` registry and ledger remain
  authoritative until that integration is implemented and read back.

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

Forge is a control plane above AO:

- **Planner** — goal → task graph, with deterministic budget/harness guardrails
- **Context builder** — budgeted context packages: repo map, decisions, and
  only *validated* skills (references, not copies)
- **Executor** — target AO worker adapter (worktrees, PR/CI stay AO's); the
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

# 3. dashboard
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

The Forge product site is packaged at the repository root as `forge@3.1.0` and is
deployed to Vercel at [web-rust-three-63.vercel.app](https://web-rust-three-63.vercel.app/).
It is a static product/docs/support site, not a live AO tracker or hosted Forge backend.

```bash
npm install forge
forge --port 4173
```

The npm package is published from `.github/workflows/publish-npm.yml` on a `v*`
tag or by manual workflow dispatch. npm requires Trusted Publishing for this
package, so configure a GitHub Actions trusted publisher for the `forge` package:

```text
Provider: GitHub Actions
User/organization: LangerSword
Repository: forge
Workflow filename: publish-npm.yml
Environment: blank
Permission: direct npm publish
```

The workflow uses GitHub OIDC and publishes provenance without an npm token. The
package does not connect to a live Forge backend. Android/APK and store
deployment are later adapters, not part of the core Track 1 learning claim.
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

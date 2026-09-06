# Forge — Stack and Runtime Boundaries

**Version:** 0.1.0 · Companion to `SPEC.md` and `architecture.md`

This file records the implementation stack, evidence status, and target integrations. It is intentionally explicit about what is live versus what is still a target.

## Current implementation

| Layer | Technology | Current evidence |
|---|---|---|
| Control plane | Python package, `uv`, Hatchling, Pydantic | `uv build` succeeds; `uv run pytest -q` reports 49 passed |
| CLI | `forge` console entrypoint | `status`, C0 verification, submission MVP, ledger readback, dashboard scaffold exercised |
| Run state | SQLite ledger + project JSONL journal | Unique submission runs persist goal, baseline, repair, skill candidate, and verdict events |
| Candidate verification | Frozen verifier-owned pytest bundle in a temporary sandbox | C0 baseline fails, one bounded repair passes, independent final verification passes |
| Reflection | OpenAI SDK, pinned `gpt-5-nano`, Responses Structured Outputs | Real reflection call returned a schema-valid `SkillCandidate` with `status=candidate` |
| Execution plane | Agent Orchestrator daemon over loopback + OpenCode | AO health/readiness/catalog/session reads observed; isolated worker worktrees created |
| Observability | Neatlogs Python SDK, `neatlogs.init`, `neatlogs.wrap`, workflow/tool spans | Fresh `submission-mvp --reflect` trace readback passed: 7 persisted spans and required application I/O |
| Local fallback | JSONL trace sink and SQLite evidence | Authoritative when hosted trace delivery is unavailable |
| Website model | Static HTML/CSS/JS in sibling `/home/lakshaya/forge-web` | `node --check app.js` and local HTTP 200 smoke passed |

## Target autonomous fleet

The production topology is:

```text
Goal
  → Forge planner
  → AO orchestrator
  → isolated workers on supported harnesses
  → independent verifier
  → bounded repair
  → reflection / candidate skill
  → G1/G2/G3 promotion gate
  → portable context package
  → fresh worker / second harness
```

AO remains the execution and worktree plane. Forge owns the learning contract, evidence ledger, verifier, repair budget, and promotion gate. A worker's final message never counts as success without an artifact and independent verification.

## Harness strategy

- **Current:** OpenCode is the only AO harness observed authorized on this machine.
- **Required for novelty:** authorize a second supported harness, preferably Codex or Claude Code, then run a fresh related task with the same context-package contract and no conversation transfer.
- **Transfer proof:** compare a no-skill baseline, the OpenCode learned-skill condition, and a fresh second-harness condition on the same held-out acceptance checks. Record accuracy, tool calls, interventions, wall time, and reported tokens/cost.
- **Boundary:** the current AO spawn/completion lifecycle has produced stuck `working` sessions without artifacts in bounded proof attempts. That is a recorded blocker, not a successful autonomous fleet run.

## Memory strategy

- **Current source of truth:** `.forge/skills/`, `evals/results/`, SQLite, and the project journal.
- **Candidate lifecycle:** reflection may create `candidate`; only Forge's applicability, A/B, and held-out regression gates may promote `validated`.
- **Future:** Supermemory as a read/write external skill and context adapter after local registry semantics are stable and readback is verified. Supermemory is not claimed as integrated in this submission.

## Neatlogs contract

The current Python integration follows the official direct-SDK pattern:

```python
neatlogs.init(...)
client = neatlogs.wrap(OpenAI(...))
# application workflow/tool spans around genuine orchestration
neatlogs.flush()
neatlogs.shutdown()
```

`flush()` runs before `shutdown()` in the outer CLI lifecycle. The wrapped OpenAI client owns the canonical LLM span; Forge does not add a duplicate manual LLM span around it. The verified completion gate used a fresh UUID marker, exercised the real reflection workflow, and read back the exact `submission-mvp` trace through the Neatlogs wizard verifier.

Official references:

- https://docs.neatlogs.com/quickstart/instrument-your-code
- https://docs.neatlogs.com/sdk/python
- https://docs.neatlogs.com/instrumentation

## Deployment target

Forge itself is local-first for the hackathon. The sibling website is a static evidence/control-plane model that can be hosted on any static host. The generated-app target path is:

```text
build → independent verification → preview → human approval → deploy → smoke test → URL
```

Vercel is the first web deployment adapter target. Android/APK and hosted multi-tenant Forge are later adapters, not current completion claims.

## Non-negotiable evidence boundary

The following are observed now:

- 49 passing local tests.
- Successful package build.
- Real GPT-5 Nano reflection.
- C0 failure → bounded repair → final pass.
- Fresh Neatlogs readback of the full submission workflow.
- AO daemon health/readiness and isolated worktree creation.

The following remain required future proof, not observed completion:

- Reliable autonomous AO spawn → artifact → verifier lifecycle.
- Cross-harness transfer using a second authorized harness.
- G1/G2/G3 promotion across multiple relevant cases.
- Supermemory external read/write integration.
- Production deployment of generated applications.

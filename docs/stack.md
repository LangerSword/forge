# Forge — Stack and Runtime Boundaries

**Version:** 0.1.1 · Companion to `SPEC.md` and `architecture.md`

This file records the implementation stack, evidence status, and target integrations. It is intentionally explicit about what is live versus what is still a target.

## Design influences (2026-09-14)

Forge's architecture is informed by a head-to-head comparison of two Razorpay
Buildathon 2026 entries:

| | razorpay-agent (LangerSword) | ZapAI (lviffy) |
|---|---|---|
| Commits | 127 | 93 |
| Stack | FastAPI + React + LinUCB + Pydantic | Next.js 15 + Bun + Express + Gemini |
| Razorpay | Orders + Payment Links only | 10 modules: Orders, Payment Links, UPI QR, GST Invoices, AutoPay, Offers, Route, Refunds, Disputes, Webhooks |
| External APIs | Razorpay SDK only | WhatsApp Cloud, Shopify OAuth, Neon PG, Redis |
| Persistence | In-memory Python dicts | Neon PostgreSQL + migrations + Redis |
| Audit | Simple audit log | 8-stage SHA-256 hash chain + Ed25519 + RFC 8785 |
| Safety | Property-fuzzed gate (20k, 0 violations) | Business guardrails, HMAC verification |
| Tests | pytest suite, gate fuzzing | 43 tests across 5 suites |
| Frontend | YC-themed React, pure CSS, zero UI libs | Next.js 15 dashboard, Radix, Framer Motion |
| Degradation | Keyless stub fallback | Requires real API keys |
| Merchant tooling | Single store, no onboarding | Multi-tenant, onboarding wizard, per-store settings |
| Scope | Dual-agent demo | Full merchant platform |

**What we learned:** ZapAI won on product completeness because it connected to
real systems. Our razorpay-agent won on safety formalism (property-fuzzed gate,
clean LLM/money separation, principled bandit). Forge's design synthesizes
both: real connections, real persistence, real safety.

---

## Current implementation

| Layer | Technology | Current evidence |
|---|---|---|
| Control plane | Python package, `uv`, Hatchling, Pydantic | `uv build` succeeds; fleet controller contracts and full regression suite exercised |
| Typed graph | `src/forge/graph.py` — `NodeSpec`/`GraphSpec`, edge types, `compile_goal_graph`, `to_taskgraph` | 16 tests: validation (dupes, cycles, unknown deps, bounds), deterministic compilation, CLI readback |
| Context fabric | `src/forge/memory.py` — `Observation`, `MemoryAdapter`, `LocalMemoryStub`, bounded `render_recall` | 9 tests: write/recall/profile, task-family filtering, deterministic ordering, bounded rendering |
| CLI | `forge` console entrypoint | `status`, `harnesses`, `plan`, `graph`, dry-run `fleet`, C0 verification, submission MVP, experiment commands, ledger readback, dashboard scaffold exercised |
| Run state | SQLite ledger + project JSONL journal | Unique submission runs persist goal, baseline, repair, skill candidate, and verdict events; fleet tasks record `memory_recall`/`memory_write` events when a memory adapter is attached |
| Candidate verification | Frozen verifier-owned pytest bundle in a temporary sandbox | C0 baseline fails, one bounded repair passes, independent final verification passes |
| Reflection | OpenAI SDK, pinned `gpt-5-nano`, Responses Structured Outputs | Real reflection call returned a schema-valid `SkillCandidate` with `status=candidate` |
| Execution plane | Agent Orchestrator daemon over loopback + OpenCode | AO health/readiness and live spawn/session/worktree readback observed; Forge recovered real sessions and enforced no-op cleanup, but live artifact-producing completion remains blocked |
| Observability | Neatlogs Python SDK, `neatlogs.init`, `neatlogs.wrap`, workflow/tool spans | Fresh `submission-mvp --reflect` trace readback passed: 7 persisted spans and required application I/O |
| Local fallback | JSONL trace sink and SQLite evidence | Authoritative when hosted trace delivery is unavailable |
| Website model | Private repository `LangerSword/forge-website` (split from core) | Root-layout build and route smoke verified in the private repo; Vercel production readback on the previous deployment |

## Target autonomous fleet

The product topology is:

```text
Goal
  → Forge commander
  → typed execution graph (GraphSpec: planner / specialist / judge / verifier)
  → recursive scheduler (bounded depth, judge routing)
  → per-node RECALL from the context fabric (Supermemory protocol)
  → fenced context package + memory block
  → AO orchestrator
  → isolated workers on supported harnesses
  → per-node WRITE of structured observations
  → independent verifier
  → bounded repair
  → reflection / candidate skill
  → G1/G2/G3 promotion gate
  → portable context package
  → fresh worker / second harness
```

Forge is the commander: graph scheduler and memory fabric sit side by side,
both above the node layer. AO remains the execution and worktree plane. Forge
owns the learning contract, evidence ledger, verifier, repair budget, and
promotion gate. A worker's final message never counts as success without an
artifact and independent verification.

## Harness strategy

- **Current:** OpenCode is the only AO harness observed authorized on this machine.
- **Required for novelty:** authorize a second supported harness, preferably Codex or Claude Code, then run a fresh related task with the same context-package contract and no conversation transfer.
- **Transfer proof:** compare a no-skill baseline, the OpenCode learned-skill condition, and a fresh second-harness condition on the same held-out acceptance checks. Record accuracy, tool calls, interventions, wall time, and reported tokens/cost.
- **Boundary:** the current AO spawn/completion lifecycle has produced stuck `working` sessions without artifacts in bounded proof attempts. That is a recorded blocker, not a successful autonomous fleet run.

The read-only readiness command is:

```bash
uv run forge harnesses
```

It reports supported, installed, authorized, and explicitly smoke-tested states. `cross_harness_pass` is false unless two distinct harnesses satisfy all four conditions. AO status, catalog presence, or authorization alone never counts as a smoke test.

## Memory strategy

- **Current source of truth:** `.forge/skills/`, `evals/results/`, SQLite, and the project journal.
- **Candidate lifecycle:** reflection may create `candidate`; only Forge's applicability, A/B, and held-out regression gates may promote `validated`.
- **Context fabric (implemented 2026-09-14):** `src/forge/memory.py` defines the `MemoryAdapter` protocol (`write` / `recall` / `profile`) and a deterministic `LocalMemoryStub`. Nodes recall relevant observations before acting and write structured `Observation`s after acting, so handoffs carry memory references instead of transcripts. `FleetController` accepts an optional `memory` adapter and emits `memory_recall`/`memory_write` ledger events.
- **Live backend (planned):** the Supermemory adapter sits behind the same protocol — see `docs/BUILD.md` Task 6. It is not claimed as integrated until implemented, configured, and read back.

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

Forge itself is local-first for the hackathon. The tracked `web/` package is a static product/docs/support site that can be hosted on any static host. It presents repository-backed evidence and installation guidance; it does not connect to a live AO tracker or Forge backend. The generated-app target path is:

```text
build → independent verification → preview → human approval → deploy → smoke test → URL
```

Vercel is the first web deployment adapter target. Android/APK and hosted multi-tenant Forge are later adapters, not current completion claims.

## Non-negotiable evidence boundary

The following are observed now:

- 102 passing local tests.
- The bounded AO Runner/readiness contract, real AO spawn/worktree/session readback, and fake-backed tests.
- Successful package build.
- Real GPT-5 Nano reflection.
- C0 failure → bounded repair → final pass.
- Fresh Neatlogs readback of the full submission workflow.
- AO daemon health/readiness, isolated worktree creation, live session cleanup, and a recorded no-op blocker.

The following remain required future proof, not observed completion:

- Reliable autonomous AO spawn → artifact → verifier lifecycle.
- Cross-harness transfer using a second authorized harness.
- G1/G2/G3 promotion across multiple relevant cases.
- Supermemory external read/write integration.
- Production deployment of generated applications.

# Forge — Architecture

**Version:** 0.1.2 · Companion to `SPEC.md` (which wins on conflict)
**Read order for any AI agent working here:** `AGENTS.md` → `SPEC.md` → this file.

---

## 1. System diagram

```
                        ┌─────────────────────────────────────────────┐
                        │                 FORGE CONTROL PLANE         │
   GoalSpec             │                                             │
 ───────────────────►   │  ┌───────────┐    ┌──────────────────────┐  │
   (goal, repo,         │  │  PLANNER  │───►│   CONTEXT BUILDER    │  │
    acceptance,         │  └─────┬─────┘    └──────────┬───────────┘  │
    tools, budget)      │        │ TaskGraph           │ context pkg  │
                        │  ┌─────▼─────────────────────▼───────────┐  │
                        │  │          EXECUTOR (AO adapter)        │  │
                        │  │  ao spawn / send / session state      │  │
                        │  └─────┬─────────────────────────────────┘  │
                        └────────┼────────────────────────────────────┘
                                 │ loopback HTTP (127.0.0.1)
                        ┌────────▼────────────────────────────────────┐
                        │            AO DAEMON (as-is, no fork)       │
                        │  workers in worktrees · PR · CI · review    │
                        │  harnesses: opencode / claude / codex / ... │
                        └────────┬────────────────────────────────────┘
                                 │ tool calls / artifacts / git state
        ┌────────────┬───────────┴──────┬──────────────┬──────────────┐
        ▼            ▼                  ▼              ▼              ▼
    GitHub       third-party      Supermemory     Neatlogs      event ledger
   (repo/CI/    tools/APIs/MCPs  (skill + ctx    (traces for   (SQLite,
    issues)     (the app under   memory store)   the demo)     source of
               automation)                                     truth)
        │            │                  │              │              │
        └────────────┴───────┬──────────┴──────────────┘              │
                             ▼                                        │
                    ┌─────────────────────┐                           │
                    │      VERIFIER       │◄──────────────────────────┘
                    │ (independent model, │
                    │  acceptance checks) │
                    └─────────┬───────────┘
                              │ RunResult
                              ▼
                    ┌─────────────────────┐        ┌─────────────────┐
                    │  LEARNING AGENT     │───────►│ SKILL REGISTRY  │
                    │ diagnose→candidate  │ gated  │ (local mirror + │
                    └─────────┬───────────┘   A/B  │  Supermemory)   │
                              │                    └────────┬────────┘
                              ▼                             │
                       StrategyNotes ──────► planner        │ inject into
                                               (next run)   │ next context
                                                          ──┘
```

**Layering rule:** the control plane never parses agent transcripts itself.
It consumes (a) the event ledger, (b) verifier output, (c) AO session state.
Anything the ledger doesn't have is not "seen".

### Evidence boundary (2026-09-07)

The diagram is the target topology, not a claim that every edge is live. AO
health/readiness and read-only catalog/session reads are observed, but the
Forge-to-AO spawn payload and reliable completion/lifecycle signal remain
unverified. The live authorized AO catalog currently contains OpenCode only, so
cross-harness transfer is a core target rather than an observed result. Hermes
is a reflection sidecar outside AO. Neatlogs is verified on the real OpenAI
`forge openai-smoke` smoke/diagnostic path (SDK, local Doctor, authenticated
probe, and trace readback); that does not establish full AO-worker trace
coverage. Supermemory is a future external integration; local Forge files and
the ledger remain authoritative for the current design.

## 2. Component contracts

### 2.1 Planner
- **Input:** `GoalSpec` + context store (decisions, strategy notes, skill
  index) + AO live state (active workers, open PRs, CI status).
- **Output:** `TaskGraph` (schema in SPEC §7). Must pass schema validation;
  one bounded repair retry on failure; then hard stop with the error logged.
- **Model:** strong model (planning quality > cost here). Temperature 0.
- **Deterministic guardrails (NOT LLM-decided):** max parallel workers ≤ 3,
  max tasks ≤ 12, per-task max steps, total budget cap, harness allowlist.
  LLM proposes composition; code enforces limits.
- **Learning hook:** consumes `strategy`-kind notes (e.g. "don't parallelize
  schema-migration tasks with API tasks that read it").

### 2.2 Context builder
- **Input:** task node + skill registry + repo map.
- **Output:** context package, budgeted (default ≤ 8k tokens):
  1. task brief (title, acceptance slice, ownership)
  2. repo map entries (file → one-line role) for touched areas only
  3. matching validated skills (scored by `applies_when` overlap —
     deterministic score, top-k=3, ties broken by recency)
  4. decision records + negative lessons ("don't: …")
- **Rule:** references, not copies. Large artifacts handed by path/handle.
- **Repo map:** generated once at P0 by a cheap map-agent over the target
  repo; refreshed only when HEAD moves past a commit that touched the
  mapped files. Never the full codebase in context.

### 2.3 Executor (AO adapter; core target, currently unverified)
- **Transport:** target loopback HTTP to the AO daemon; `ao` CLI as fallback.
  The documented surface includes `POST /api/v1/sessions` (spawn),
  `POST /api/v1/sessions/{id}/send`, `GET /api/v1/sessions`,
  `GET /api/v1/sessions/{id}`, `POST /api/v1/sessions/{id}/kill`,
  `POST /api/v1/sessions/{id}/agent-switches`, and
  `POST /api/v1/sessions/{id}/pr/claim`. The exact spawn payload and
  completion semantics are not verified; record the actually-working surface
  in `.forge/ao-surface.json` and code against that, not this doc.
- **Responsibilities:** spawn worker (task brief + context package as the
  first message), poll session state, detect completion/blocked, return
  session id + workspace path. No transcript parsing.
- **Worktrees:** AO owns them. Forge records `session_id → worktree path`
  so the verifier can point tests at the right checkout.
- **Failure policy:** blocked/timeout ⇒ record `RunResult(status=blocked)`,
  one bounded nudge (same session, `send`), then escalate to ledger + stop.
- **Autonomy gate:** health/readiness, a listed session, or an idle status is
  insufficient. The adapter needs observed spawn, artifact, lifecycle, and
  independent verifier evidence before it reports autonomous execution.

### 2.4 Verifier
- **Input:** `RunResult`-in-progress, acceptance checks, worktree path,
  session id.
- **Behavior:** runs checks in the worktree (tests, build, probes, artifact
  existence). Each check ⇒ `{check, pass, evidence}`. Evidence is a path or
  command + exit code — never prose about what the worker *said*.
- **Model:** different model family than the worker (prevents self-approval
  bias). Verifier is the only component allowed to mark a run passed.
- **Anti-loop:** a check is deterministic code unless it is explicitly an
  LLM-judge check (max 1 per run, logged as such).

### 2.5 Learning agent (the product)

The learning agent may be implemented by Hermes as an external specialist;
it is not required to be an AO worker. AO's current live catalog has no
Hermes adapter, while OpenCode is the authorized worker for `forge-1`.
Forge calls the learning specialist through a narrow file/JSON contract:
`RunResult` + bounded ledger slice in, schema-validated diagnosis/candidate
out, then Forge's deterministic gate decides promotion. This prevents
Hermes's reflective suggestion from becoming an unverified skill.
Runs per completed (pass or fail) run:

1. **Observe** — pull the run's ledger slice: tool calls, errors, patches,
   spend, wall time, verifier verdict. Bounded size (truncated with marker).
2. **Diagnose** — LLM, strong model: "what caused the failure / waste?
   Propose ≤2 root causes with ledger evidence refs." No evidence ref ⇒
   hypothesis rejected at parse time.
3. **Candidate** — LLM writes a `SkillCandidate` (SPEC §7) or a
   `StrategyNote`. Candidate must fill `applies_when`, `procedure`,
   `verification`, `evidence_refs` — missing fields ⇒ not a candidate,
   logged as raw reflection only.
4. **Gate** (deterministic harness, LLM inside only as judge):
   - G1 applicable: candidate matches ≥2 cases in the validation set
     (deterministic matcher on `applies_when` features).
   - G2 benefit: A/B on validation set — worker WITH skill injected vs
     WITHOUT, same model, same task family. WITH must pass ≥ without, and
     win on ≥1 of {pass rate, tool calls, cost}.
   - G3 no regression: held-out mini-set (2 tasks, never touched by
     diagnosis) must not drop below baseline pass rate.
   - Verdicts recorded in `gate_results`. Any failure ⇒ stays `candidate`,
     with the failure reason stored (that reason is itself a lesson).
5. **Publish** — `validated` ⇒ written to registry (file + Supermemory
   container) ⇒ eligible for context injection.
6. **Decay** — on target-repo HEAD change or tool contract change: re-run
   G3 for affected skills; fail ⇒ `retired` (kept, surfaced as negative
   lesson with the failure evidence).

**Why this is "learning" and not "logging":** injection eligibility is
earned through G1–G3; a wrong lesson is detectable (G3 regression),
retirable, and its retirement is visible in the evidence UI.

### 2.6 Registry
- **Source of truth:** `.forge/skills/*.json` (versioned, gitignored at
  runtime; promoted skills also committed under `skills/` for the demo repo
  so judges can read them).
- **Future mirror:** Supermemory container `forge:<project>` is a planned
  write-through/read-through adapter. It is not enabled or verified in the
  current runtime; local files and the ledger remain authoritative until a
  read-back-verified integration exists.
- **Lifecycle states:** `candidate → validated → retired` (terminal; a new
  skill can supersede with `supersedes` ref).

### 2.7 Event ledger (source of truth)
SQLite, `.forge/ledger/ledger.db`. Append-only. Tables:

```sql
events(run_id TEXT, ts TEXT, kind TEXT, actor TEXT, payload TEXT)
  -- kind: goal|plan|spawn|tool_call|error|patch|nudge|check|verdict|
  --       reflection|candidate|gate|publish|retire|spend
runs(run_id TEXT PRIMARY KEY, goal TEXT, condition TEXT, harness TEXT,
     status TEXT, wall_s REAL, cost_usd REAL, tokens_in INT, tokens_out INT,
     skills_used TEXT)   -- cost/tokens NULL when unreported — never estimated
skills(skill_id TEXT PRIMARY KEY, status TEXT, json TEXT,
       created_run TEXT, validated_run TEXT, retired_run TEXT)
```

Every LLM call that costs money emits a `spend` event with
`{model, tokens_in, tokens_out, cost_usd|null, purpose}`.

### 2.8 Dashboard
Static HTML + `/api` on a local port. Pages:
1. **Runs** — table, filter by condition/run/status.
2. **Run detail** — trace (from ledger), verifier evidence, spend breakdown.
3. **Skills** — lifecycle board; click ⇒ candidate JSON, gate results,
   later-use refs (the "what did it learn" drill-down).
4. **Compare** — C0 vs C2 table (the numbers that go in the video).
No auth, no persistence beyond the ledger.

## 3. Data flow for one run (happy path)

```
GoalSpec ──► planner ──► TaskGraph ──► [per task, in dep order]
   context_builder(task) ──► context pkg
   executor.spawn(task+pkg) ──► AO session
   worker executes (AO tracks PR/CI) ──► session done
   verifier(worktree, acceptance) ──► RunResult
   ledger: verdict event
   learning.observe(run) ──► diagnose ──► candidate ──► gate(A/B+held-out)
     pass ──► publish ──► registry ──► next run's context pkg
```

## 4. Cost & speed model (the "economics" answer for judges)

- **Total cost per verified outcome** = planning + execution + verification
  + learning (per-run, from `spend` events). Skill creation cost is charged
  to the run that earned it; later runs get amortized credit in the
  Compare view.
- **Cheapest-first routing:** planner picks harness/model per task from
  (a) harness readiness, (b) task complexity features (files touched,
  test surface), (c) strategy notes. Default: cheap model (`glm-4-7-flash`)
  for leaf tasks, strong model for planning/verification/diagnosis.
- **Parallelism is a learned decision**, not a default: planner reads
  strategy notes on which task pairs regressed when parallel.
- **Stopping rules:** budget cap ⇒ planner re-plans on remaining tasks;
  per-task step cap ⇒ bounded nudge ⇒ escalate; 2 consecutive failed
  attempts at the same check ⇒ stop run, log, learn.

## 5. AO integration — target surface, verified subset & unknowns

AO autonomous execution is a core Forge target, but it is not a verified
end-to-end capability in this checkout.

**Observed locally (2026-09-06):** `GET /healthz` and `/readyz` returned
healthy/ready on port 3001; `GET /api/v1/agents` reported `opencode` as the
only installed and authorized agent; `GET /api/v1/projects` reported project
`forge` with orchestrator `opencode`; and `GET /api/v1/sessions` reported
`forge-1`, an idle OpenCode session. The AO daemon and read-only surface are
real observations; they are not proof of autonomous Forge execution.

**Core target / must verify at P0 (record in `.forge/ao-surface.json`):**
- Exact spawn payload (agent/model flags, project binding) and its response.
- How Forge learns a session *finished* (status field, terminal exit, artifact,
  or PR state) and how it distinguishes a no-op or `needs_input` state.
- An independently verified artifact from a Forge-requested worker session.
- A second AO-authorized harness and a fresh-worker transfer run. Until then,
  OpenCode is the only observed execution harness and no transfer claim is
  valid.

**Implemented control contract:** `forge.ao-runner.v1` now wraps the documented
AO CLI spawn flags, polls the session through the AO client, checks an expected
worktree artifact, optionally invokes an independent verifier, records
`spawn/poll/check/send/kill/verdict` events, and applies at most one watchdog
nudge before terminating no-op or hidden-blocked work. The contract is
fake-tested; the real AO proof remains open until an artifact-producing worker
run passes independently.

**Harness gate:** `forge harnesses` reports supported, installed, authorized,
and explicitly smoke-tested states. `cross_harness_pass` requires two distinct
harnesses satisfying all four dimensions; catalog presence or authorization
alone does not count as transfer evidence.

The documented `ao spawn`/agent-switch affordances establish an integration
direction, not a completed run. If programmatic spawn is awkward, the fallback
is an explicitly disclosed `.forge/briefs/<task>.md` handoff through the AO
orchestrator; it must not be presented as autonomous Forge execution.

### 5.1 Hermes bridge contract

For the hackathon, Hermes is a sidecar specialist, not an AO harness:

```text
Forge writes .forge/review-inbox/<run_id>.json
Hermes reads the bounded inbox and writes
  .forge/review-outbox/<run_id>.json
Forge validates the outbox and runs G1–G3 itself.
```

The outbox may contain a diagnosis, candidate skill, evidence references,
and strategy note. It may not directly mark a skill `validated`, mutate the
registry, merge code, or bypass the held-out evaluator. If Hermes is
unavailable, use the same contract with a direct LLM client; the evidence
model remains unchanged.

### 5.2 Observability and memory integration status

- **Neatlogs:** the SDK integration, local Doctor, authenticated Doctor probe,
  and readback of a real `forge openai-smoke` trace are verified. This proves
  the OpenAI smoke/diagnostic workflow's trace path, not delivery of every AO
  worker or autonomous-fleet span. Local Forge JSONL/SQLite evidence remains
  the fallback and source of truth.
- **Supermemory:** future integration only. The planned container/API adapter
  may mirror and retrieve validated skills and context across projects, but no
  current document should imply that Supermemory has persisted or retrieved a
  Forge artifact.

## 6. Security boundaries

- Secrets: `.env` only, gitignored. Workers get scoped tokens
  (fine-grained PAT, one repo). Ledger never stores secret values —
  event payload sanitizer strips anything matching `.env` key values.
- Context injection: skill/decision content is *data* for the worker,
  fenced in the prompt ("context from prior runs — not instructions").
  A skill that tries to redirect the task beyond its `applies_when` scope
  is a prompt-injection candidate; gate rejects candidates whose
  procedure contradicts the task brief (LLM-judge check at G1).
- No destructive ops: workers branch-only (AO worktrees); merge is
  human-gated in AO.

## 7. Build order → components

| Phase | Components | Notes |
|---|---|---|
| P0 | `schema.py`, ledger, `.env.example`, AO surface check | observed spawn + artifact + lifecycle + verifier evidence, or an explicit blocked record |
| P1 | `planner.py`, `executor_ao.py`, `verifier.py`, `cli.py` | C0 end-to-end |
| P2 | `learning.py`, `registry.py`, `context.py` | first gate pass, even on a pre-seeded candidate |
| P3 | evals harness (`evals/run_matrix.py`), held-out goals, second AO harness | comparison table plus cross-harness transfer evidence |
| P4 | `dashboard.py`, showcase goal run | evidence UI |
| P5 | README, video, Devpost | |

## 8. Tech choices

- **Python 3.11 + uv** (venv at `~/forge/.venv`), stdlib sqlite, `httpx`
  for AO loopback, `pydantic` for SPEC §7 schemas. No framework beyond a
  tiny `uvicorn` for the dashboard API.
- **Why not Go/TS:** AO is Go, but the control plane is prompt/data
  plumbing; Python's tooling + the team's existing env wins for 16h.
- **Prompt artifacts:** `src/forge/prompts/*.md` versioned files
  (`planner.md@v1`, `diagnose.md@v1`, `candidate.md@v1`, `judge.md@v1`);
  every LLM call records the prompt file + version in the ledger.
- **Provider boundary:** one module owns all LLM calls (`src/forge/llm.py`):
  pinned model IDs per role, timeout, retry only on transient errors,
  schema-validated outputs with one bounded repair. OpenAI-compatible
  endpoint covers TensorMux; a second client for the strong model.

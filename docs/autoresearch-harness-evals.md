# Autoresearch goal: real harnesses, evals, and self-improving agents

**Status:** research plan + observed findings; not implementation evidence
**Started:** 2026-09-06 · **Validator:** Forge's G1/G2/G3 gate

## Research objective

Determine the smallest real, locally installed harness stack that can run Forge
workers, preserve tool/session traces, execute reproducible tasks, and support
bounded self-healing and self-learning experiments within the hackathon window.

## Source boundaries

### Observed local sources

- AO daemon at `http://127.0.0.1:3001`
- AO API responses from `/healthz`, `/readyz`, `/api/v1/agents`,
  `/api/v1/projects`, `/api/v1/sessions`
- Local OpenCode CLI (`1.18.25`)
- Local Hermes CLI (`0.20.6`) and `hermes doctor`
- Forge repository and current runtime scaffold

### Official external sources retrieved

- Anthropic, **Demystifying evals for AI agents**:
  https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, **Create custom subagents**:
  https://code.claude.com/docs/en/sub-agents
- AO CLI source documentation was previously retrieved from the AO GitHub
  repository: https://github.com/Untrivial-ai/agent-orchestrator/blob/main/docs/cli/README.md
- OpenCode web docs and OpenAI docs were attempted but unavailable through the
  current keyless retrieval providers. Their claims remain unverified here.

## Observed local findings

| Component | Observed fact | Confidence |
|---|---|---|
| AO | `/healthz` and `/readyz` return healthy/ready | high, live local response |
| AO | `forge` project exists at `/home/lakshaya/forge` | high, live local response |
| AO | `forge-1` exists as an idle OpenCode orchestrator session | high, live local response |
| AO | Only OpenCode is installed and authorized in the live catalog | high, live local response |
| OpenCode | CLI `1.18.25` is installed | high, local command |
| OpenCode | `opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'` succeeded | high, observed run |
| OpenCode | four credentials are configured locally (names only; secrets not read) | high, local command |
| Hermes | CLI `0.20.6` and `hermes doctor` succeed | high, local command |
| Hermes | Nous Portal auth, memory, skills, SQLite state, and venv are healthy | high, doctor output |
| Forge | local `forge status` reads AO and local ledger | high, observed run |

## Research conclusions so far

### 1. Harness strategy

Use **AO/OpenCode as the real implementation harness** now. Use Hermes as a
reflection specialist through a file/JSON contract, not as an invented AO
adapter. Add a second AO-supported harness only after its installation and
authorization are observed locally.

The useful experimental matrix is:

```text
H0: AO/OpenCode, learning disabled
H1: AO/OpenCode, Forge validated skills enabled
H2: second AO harness, same validated skill package
```

H2 is the cross-harness transfer claim; it is not valid until the second
harness is actually installed, authorized, and smoke-tested.

### 2. What an eval must record

Anthropic's official eval guidance defines the important units:

- task: input plus success criteria
- trial: one attempt; run multiple trials because outputs vary
- grader: checks for transcript and/or outcome
- transcript/trace: complete tool and intermediate interaction record
- outcome: final environment state, not the agent's claim
- evaluation harness: runs tasks, records steps, grades, aggregates

Forge therefore needs both transcript and outcome evidence. A green final
message without a green artifact check is a failure, not a pass.

### 3. Grader composition

Use a ladder, cheapest and most objective first:

1. deterministic code checks: tests, build, lint, typecheck, endpoint status,
   file existence, git diff constraints
2. tool-call checks: required tool used, forbidden tool not used, parameters
   valid, redundant-call count
3. static outcome checks: schema, security scan, dependency policy
4. model grader: only for nuanced quality/rubric checks, with explicit rubric
5. human calibration: sample model-graded cases and compare judgments

Capability evals seek difficult improvements; regression evals protect already
working behavior. A promoted skill must pass both.

### 4. Self-healing contract

A failure becomes a repair task only if the verifier provides:

```json
{
  "failure_id": "...",
  "check": "...",
  "signature": "stable normalized failure signature",
  "evidence": ["path or command result"],
  "attempt": 1,
  "repair_budget": {"max_attempts": 2, "max_minutes": 5}
}
```

The repair agent may change implementation/configuration, but cannot modify
the acceptance check or delete a failing test. It must rerun the failed check
and a regression subset. A repeated signature stops the loop and becomes a
negative lesson candidate.

### 5. Self-learning contract

A reflection output is not a memory write. It becomes a candidate only if it
has:

- a scoped applicability condition
- a bounded procedure
- exceptions
- verification checks
- evidence references to observed traces/outcomes
- compatible repo/tool/harness versions

It becomes `validated` only after:

- G1: applies to at least two relevant cases
- G2: with-lesson A/B improves a declared target metric
- G3: held-out regression suite does not worsen

The learning agent may propose a prompt/tool/skill/routing change. Forge's
code owns the gate and registry mutation.

## Proposed initial eval suite

### Task family E1 — tool-use recovery

A local mock third-party API returns a realistic parameter error on the first
call and a successful result after the correct namespaced call. Measures:

- eventual outcome
- invalid calls
- redundant calls
- whether the learned tool-use skill transfers

### Task family E2 — small web artifact

Build a tiny React/Vite page with a form, validation, test, and preview.
Measures:

- build/test pass
- changed-file scope
- tool calls
- repair count
- wall time/tokens/cost
- preview smoke test

### Task family E3 — contextual decision

Given issue metadata, dependency state, and a policy note, decide whether a
change is safe to proceed and draft the next action. Include a documentation-
only exception. Measures contextual logic, not keyword matching.

### Dataset split

- `train`: failures available to the reflection agent
- `validation`: used to decide promotion
- `heldout`: frozen before diagnosis; never shown to the learning agent

## Research loop and stopping rule

Each cycle must close named evidence gaps:

1. verify installed harness/version/auth
2. run smoke task and capture raw trace
3. define one task family and deterministic grader
4. run baseline trials
5. introduce one candidate lesson
6. run A/B and held-out regression
7. accept, reject, or retire with evidence

Stop when either:

- H0/H1 plus one promoted candidate and one held-out result are observed, or
- the remaining gap is explicitly recorded as unavailable (for example, no
  second AO harness authorized), with a next-step command.

## Current unresolved gaps

1. Only OpenCode is currently authorized in AO; cross-harness transfer is not
   yet observed.
2. Exact AO programmatic spawn payload still needs a live smoke test through
   the daemon/CLI; the current Forge client only reads status.
3. Supermemory, TensorMux, and Neatlogs are not configured; they are optional
   for the first local eval and should not block H0/H1.
4. OpenCode official documentation retrieval failed through the current
   keyless web backend; local CLI behavior is the stronger source for now.

## Recommended next implementation order

1. Add a `GoalSpec`/`RunResult` schema and goal loader.
2. Add AO session creation/polling using the exact live CLI/API surface.
3. Add deterministic verifier for E1 or E2.
4. Add Hermes inbox/outbox reflection adapter.
5. Add G1/G2/G3 evaluator with raw JSON trial records.
6. Add bounded repair loop after the first observed failure.
7. Add dashboard pages only after the ledger contains real runs.

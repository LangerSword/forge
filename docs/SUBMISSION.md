# Forge — Devpost Submission Copy

**Track:** Track 1 — Automated Agent Engineering
**Project:** Forge
**Team:** Syndicate by Maximor
**Submission date:** 2026-09-07

> **Submission boundary:** This copy reports the observed local MVP and its evidence. It does not turn the target architecture into a completed capability. In particular, AO autonomous completion and cross-harness transfer are future proof points, not claims about this checkout.

## Paste-ready project card

### Project title

**Forge — a learning layer for agent fleets**

### One-line description

Forge turns a bounded agent failure into an inspectable repair, an evidence-linked candidate skill, and a verifiable run record—without confusing reflection with learning or an idle worker with success.

### Short description

Agent fleets can execute tasks, but their useful experience is usually trapped in transcripts. Forge is a local-first control plane that adds an evidence ledger, independent verification, bounded repair, structured reflection, and a skill lifecycle around agent work. In the submission MVP, a frozen C0 task starts red, one bounded repair makes it green, GPT-5 Nano produces a schema-valid **candidate** skill from the observed evidence, and the complete workflow is read back in Neatlogs. AO is used as the execution/worktree target; OpenCode is the only AO harness observed authorized here. The demo is intentionally honest about what is still unproven.

### Track 1 explanation

Forge is built for automated agent engineering because it treats an agent run as an outcome that must be measured, not as a transcript that should be remembered. The control plane records the goal, baseline failure, repair attempt, verifier result, reflection output, and final verdict. A candidate lesson carries provenance and stays `candidate` until separate applicability, A/B, and held-out gates promote it. This is the missing learning/evidence layer around an execution orchestrator.

The observed MVP proves the narrow vertical slice:

```text
frozen failing task
  → independent baseline verification
  → one bounded repair
  → independent final verification
  → structured reflection
  → candidate skill artifact
  → SQLite/JSONL evidence + Neatlogs trace
```

It does **not** claim that the full target fleet loop, autonomous AO completion, or cross-harness transfer has already been proven.

## The problem

More agents do not automatically create a better engineering organization. A worker may discover an API quirk, a reliable tool order, or a failure signature, but the useful part is normally left in a transcript. Replaying the transcript is expensive, hard to audit, and tied to one harness.

The dangerous shortcut is to call any remembered prompt a skill, any final message a pass, or any `idle` AO session a successful worker. Forge is designed to reject those shortcuts. It asks:

- Did the acceptance check actually fail and then pass?
- What artifact changed?
- Which component is allowed to declare the verdict?
- Did reflection produce a bounded, provenance-linked candidate?
- Has the candidate passed the promotion gates, or is it still only a hypothesis?

## What we built

Forge is a local Python CLI and evidence layer above an agent execution plane:

- **Planner/context contract:** a task brief, repository references, budget, and compatible lessons can be assembled without dumping an entire repository into a prompt.
- **Verifier:** runs frozen acceptance checks in a verifier-owned sandbox. Worker narration is never sufficient for success.
- **Bounded repair:** a failure may receive one bounded repair attempt; repeated or unverified work stops rather than looping.
- **AO Runner contract:** `forge.ao-runner.v1` records documented spawn, session polling, artifact checks, independent verification, one nudge, and watchdog kill decisions. Its fake-backed tests pass; a real artifact-producing AO lifecycle remains an explicit open proof.
- **Reflection:** a structured model response can describe a failure and propose a candidate skill, but it cannot promote itself.
- **Evidence ledger:** SQLite and JSONL preserve goal, baseline, repair, candidate, and verdict events.
- **Observability:** the real OpenAI/reflection path is instrumented with Neatlogs; local Forge evidence remains the fallback/source of truth.
- **AO boundary:** AO owns worker sessions and worktrees in the target topology. Forge records readiness/session evidence and refuses to infer autonomous success from health, readiness, or session state alone.

The current submission uses a small C0 name-normalizer fixture so the before/after result is quick, deterministic, and inspectable. The frozen verifier starts with `NotImplementedError`, and the repair changes only `c0_target.py` before the same checks are run again.

## Architecture

```text
                         FORGE CONTROL PLANE
        GoalSpec → planner/context → task contract
                              │
                              ▼
                  verifier ← bounded repair
                     │             │
                     ▼             ▼
               RunResult      reflection
                     │             │
                     └──────┬──────┘
                            ▼
                    candidate skill + gates
                            │
                  SQLite ledger / JSONL trace
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
       AO execution plane              Neatlogs
    sessions + worktrees             external trace
    (OpenCode observed)             (verified scope)
```

The target layering is deliberate:

1. AO is the worker/process and worktree plane; Forge does not fork AO or replace its Kanban.
2. Forge owns evidence, verification, repair policy, learning artifacts, and promotion policy.
3. Reflection is a proposal source. The verifier and promotion gates remain authoritative.
4. Neatlogs observes the configured application/provider path. Its verified trace is not presented as proof that every AO worker or fleet span was externally delivered.

### Where Hermes fits

Hermes is an external reflection/development-sidecar boundary, not an AO harness. The repository contract gives the sidecar bounded run evidence and a JSON inbox/outbox shape; Forge validates the output and owns promotion. The final observed submission run used the configured GPT-5 Nano/OpenAI structured-reflection provider and produced a `candidate` artifact. It is not presented as a Hermes worker completing an AO task.

## Observed demo result

The exact final run used for the evidence card is `submission-c0-82dffafc`.

| Check | Observed result | Evidence |
|---|---|---|
| Regression suite | **61 passed** | `uv run pytest -q`; recorded in `docs/stack.md` and the final verification notes |
| C0 baseline | **Failed** with exit code `1`; four frozen checks failed on `NotImplementedError` | `uv run forge run submission-c0-82dffafc` and `evals/results/submission-c0-82dffafc.json` |
| Repair | **One bounded attempt** changed `c0_target.py` | ledger `repair_verdict` event for the run |
| Final verification | **Passed** with exit code `0`; four checks passed | same run readback and tracked eval report |
| Reflection | `reflection_error=None`; structured output produced a skill artifact with status **`candidate`** | `.forge/skills/failure_bound_from_evidence.json` and run event `skill_candidate` |
| Persisted run | status **`passed`**, five ledger events in the CLI readback | `uv run forge run submission-c0-82dffafc` |
| Neatlogs | trace `6f969ec0305657630aeb0b959cc189ab`; **7 persisted spans** and required application input/output present | fresh final verification readback |
| AO readiness | health `ok`, readiness `ready`; OpenCode was the only installed/authorized harness observed | `uv run forge status` and `.forge/ao-surface.json` |
| AO proof attempts | `forge-6` and `forge-7` stayed working without the requested proof artifact and were terminated | AO session/worktree readback and final verification notes |

The C0 result is a before/after verification result, not a claim that a production agent fleet has generalized the repair. The candidate skill is intentionally **not** called validated or promoted.

## AO usage

AO was used during development and for explicitly bounded worker proof attempts:

- The daemon's health/readiness and read-only agents, projects, and sessions surfaces were exercised.
- The bounded AO Runner contract was implemented and tested without treating the stalled proof workers as successful completion.
- `uv run forge harnesses` reports readiness dimensions separately; the cross-harness gate requires two distinct supported, installed, authorized, and explicitly smoke-tested harnesses.
- The `forge` project and OpenCode orchestrator were observed.
- OpenCode was the only authorized harness in the live catalog, so no second-harness comparison was possible.
- Two explicitly approved proof workers (`forge-6` and `forge-7`) were created in isolated worktrees. Both remained `working` without producing the requested proof artifact and were terminated.
- Forge therefore does not claim autonomous AO execution for the final submission workflow. The local C0 repair path is evidence of Forge's verifier/repair/reflection slice, not evidence that AO independently completed that task.

This failure is part of the product story: `working`, `idle`, `ready`, and `healthy` are lifecycle observations, not artifact verification.

## Neatlogs usage

The Forge CLI initializes Neatlogs, wraps the real OpenAI client, and creates workflow/application spans around the submission path. The final fresh `submission-mvp --reflect` run was read back through the Neatlogs verification workflow:

- trace ID: `6f969ec0305657630aeb0b959cc189ab`
- persisted spans: `7`
- required application input/output: present
- verification result: pass

The scope of that claim is exact: the instrumented Forge submission/reflection workflow was read back. It is not a claim of full AO-worker or full-fleet external trace coverage. Forge's SQLite ledger and JSONL trace remain the authoritative local evidence when hosted trace delivery is unavailable.

## Why this is useful

Forge makes a small but important contract explicit: **experience is not learning until it survives evidence and gates**. The same control plane can later compare a no-skill baseline with a validated-skill run and a fresh worker on another harness, while reporting acceptance, tool calls, interventions, wall time, tokens, and cost only when the harness actually observed them.

The current artifact demonstrates the enforcement boundary and a real bounded loop. The next proof step is not a larger prompt; it is a second authorized AO harness, a fresh worker with no conversation transfer, and a held-out comparison.

## Setup and demo

> Replace angle-bracket values before publishing. These are intentionally placeholders, not fabricated links.

- **Repository:** [Forge source](https://github.com/LangerSword/forge)
- **Demo video:** [3-minute demo](<DEMO_VIDEO_URL>)
- **Live evidence website:** [Forge Evidence Control Plane](https://web-rust-three-63.vercel.app/)
- **Neatlogs trace:** [trace readback](<NEATLOGS_TRACE_URL_FOR_6F969EC0305657630AEB0B959CC189AB>)
- **AO evidence:** [AO session/worktree evidence](<AO_EVIDENCE_URL_OR_LOCAL_CAPTURE>)
- **Architecture:** [`architecture.md`](../architecture.md)
- **Evidence and runbook:** [`README.md`](../README.md), [`SPEC.md`](../SPEC.md)

### Local setup

```bash
git clone https://github.com/LangerSword/forge.git
cd forge
uv sync
cp .env.example .env
# Fill credentials locally only for the enabled provider/trace paths.
# Never paste .env contents into a recording, prompt, ledger, or commit.
uv run pytest -q
uv run forge status
```

### Run the observed submission workflow

With the local provider/trace credentials configured:

```bash
uv run forge submission-mvp --reflect
```

The command creates a fresh run ID. Preserve the emitted ID, then read that exact run back:

```bash
uv run forge run <RUN_ID>
```

For the final captured evidence, the exact readback is:

```bash
uv run forge run submission-c0-82dffafc
uv run python -m json.tool evals/results/submission-c0-82dffafc.json
uv run python -m json.tool .forge/skills/failure_bound_from_evidence.json
```

For a local Neatlogs envelope check (not the hosted trace readback):

```bash
uv run python -m neatlogs doctor --local --json
```

## Honest limitations and next proof steps

The following remain open and are deliberately not hidden in the pitch:

1. **AO autonomous lifecycle:** the exact Forge-to-AO spawn payload and reliable completion signal are not yet verified end to end. A healthy daemon, ready daemon, or terminated/idle session is insufficient without an artifact and independent verification.
2. **Cross-harness transfer:** only OpenCode is observed authorized in the live AO catalog. No Codex/Claude Code or other second-harness transfer result is claimed.
3. **Skill promotion:** the observed reflection output is `candidate`; G1 applicability, G2 A/B benefit, and G3 held-out no-regression promotion evidence are not complete for this submission.
4. **Neatlogs scope:** the seven-span readback covers the instrumented submission/reflection workflow, not every AO worker or fleet span.
5. **Supermemory:** planned, not integrated or read-back verified. Local Forge files and the ledger are authoritative.
6. **Deployment:** the static evidence website is deployed on Vercel; Forge's runtime/control plane remains local-first. No unattended generated-app deploy, Android/APK store publication, or hosted multi-tenant Forge service is claimed.
7. **Metrics:** no cost, token, speed, or percentage improvement is reported unless the underlying run observed it. The current evidence is a bounded pass/fail transition, not a statistical evaluation.

## Claims we make—and do not make

**We make these claims:**

- Forge records a real, bounded C0 failure → repair → final verification → structured reflection path.
- The final captured run passed its verifier, persisted a ledger record, and produced a schema-valid `candidate` skill artifact.
- The configured OpenAI/reflection workflow was read back in Neatlogs with the trace and span evidence above.
- AO readiness and OpenCode-only authorization were observed, and failed proof attempts were preserved rather than relabeled as success.

**We do not make these claims:**

- that AO autonomously completed the final C0 task;
- that Forge has demonstrated cross-harness transfer;
- that the candidate skill is validated, promoted, or broadly generalizable;
- that Neatlogs contains complete fleet/AO-worker coverage;
- that Supermemory is integrated;
- that a generated app was deployed to production or an app store.

That boundary is the product's point: if the evidence is missing, Forge reports the gap instead of filling it with agent narration.

## Technologies

Python, `uv`, Pydantic, SQLite, JSONL, AO, OpenCode, OpenAI Responses/Structured Outputs, Neatlogs, and a local-first CLI. The repository also contains the target design for a verifier-owned promotion gate and portable context packages.

# Agent harnesses — implementation design

**Status:** build specification, local uncommitted work
**Target benchmark:** `https://drawably.dev/`

## What a harness means in Forge

A harness is not a prompt wrapper. It is the runtime contract around an agent:

```text
input contract
  → controlled context/tool surface
  → bounded execution loop
  → trace + artifacts
  → independent outcome verification
  → repair/retry policy
  → structured handoff
```

Each harness must make the agent more capable by providing focused tools,
state, feedback, and stop conditions. It must not hide failures or grant all
agents the same unrestricted tool surface.

## Harness matrix

| Agent | Harness | Capability added | Write authority |
|---|---|---|---|
| A0 Controller | `control_harness` | state machine, budgets, dependency scheduling, cancellation | `.forge/ledger`, run state |
| A1 Planner | `planning_harness` | repo map, acceptance parsing, strategy memory, graph validation | task graph only |
| A2 Context Builder | `context_harness` | task retrieval, skill compatibility, token budget, provenance | context package only |
| A3 Builder | `ao_worker_harness` | AO worktree, OpenCode session, terminal, browser preview, CI feedback | assigned worktree |
| A4 Tool Specialist | `tool_probe_harness` | isolated mock API/MCP, schema probes, call replay, error corpus | probe fixtures only |
| A5 Verifier | `verification_harness` | deterministic tests, browser assertions, diff/security checks, evidence capture | verifier artifacts only |
| A6 Reflection | `reflection_harness` | bounded trace summaries, Hermes sidecar, structured candidate output | review outbox only |
| A7 Gatekeeper | `eval_harness` | controlled A/B trials, held-out set isolation, grader aggregation | gate results only |
| A8 Repair | `repair_harness` | failure signature, bounded patch loop, regression rerun | assigned worktree |
| A9 Deployment | `deployment_harness` | preview, approval, provider deploy, smoke test, rollback record | deployment metadata |
| A10 Curator | `curation_harness` | dedupe, compatibility decay, retirement, learning graph | registry state after gate |

## Harness invariants

1. **One agent, one authority.** A builder cannot modify the registry. A
   reflection agent cannot mark a skill validated. A verifier cannot repair.
2. **Stable context at session start.** Inject context once before the worker
   begins; do not mutate the system prompt during execution.
3. **Every tool call is traced.** Record tool name, normalized arguments,
   result class, duration, error signature, and artifact references. Redact
   credentials before persistence.
4. **Outcome beats narration.** A final text response never passes a task;
   the verifier checks the artifact/environment.
5. **Bounded retries.** Every harness has max steps, max minutes, and max
   repair attempts. Repeated signatures stop the loop.
6. **Provenance everywhere.** Skills and context entries carry source run,
   source event, compatible versions, and validation status.
7. **No target-repo cloning for visual eval.** The Drawably benchmark may use
   public rendered observations, screenshots, DOM/accessibility metadata,
   interaction traces, and permitted public assets. It must not clone or read
   the target source repository.

## H0/H1/H2 real harness stack

### H0 — AO/OpenCode worker harness

**Installed evidence:** AO daemon is healthy; project `forge` exists;
OpenCode `1.18.25` is installed and authorized; one-shot smoke succeeded.

**Startup:**

1. Forge validates AO readiness and authorized agent.
2. Forge creates a run ledger record.
3. Forge creates an AO task/session with the task brief and context package.
4. AO owns the worktree and OpenCode owns the coding loop.
5. Forge polls session state and captures AO/session references.
6. On completion, Forge passes the worktree to the verifier.

**Capability elevation:** task-scoped repository context, prior validated
skills, acceptance checks, browser preview, and CI feedback—not a larger
prompt dump.

**Fallback:** if programmatic AO spawn is not yet available, write an exact
`.forge/briefs/<task>.md` and have the AO orchestrator launch it; the same
trace and verifier contract still applies, disclosed in the report.

### H1 — Hermes reflection harness

Hermes is not an AO worker. It is a sidecar harness for bounded reflection:

```text
.forge/review-inbox/<run_id>.json
  → Hermes reads bounded trace and prior candidate context
  → .forge/review-outbox/<run_id>.json
  → Forge schema validation + G1/G2/G3
```

Hermes receives no deployment credentials and cannot directly modify the skill
registry. It may propose:

- root-cause hypotheses
- candidate skills
- negative lessons
- strategy notes
- verifier/test suggestions

**Capability elevation:** Hermes brings durable memory, skill authoring, source
hygiene, and curation patterns. Forge adds evidence references and promotion
gates around those suggestions.

### H2 — second AO harness

Install and authorize a second harness only after H0 is green. Preferred
candidate: Codex or Claude Code, subject to the live AO catalog and local auth.
The harness adapter must pass the same task, context package, budget, and
acceptance checks as H0. Only the execution identity changes.

**Transfer claim is valid only if:** a fresh H2 worker uses a validated skill
created from H0/H1 evidence and succeeds on a related task.

## Drawably visual-reproducibility harness

### Input

```json
{
  "target_url": "https://drawably.dev/",
  "viewport": {"width": 1440, "height": 1000},
  "routes": ["/", "#install", "#api"],
  "no_source_clone": true,
  "allowed_observation": ["rendered_dom", "computed_style", "screenshot",
                           "accessibility_tree", "public_asset_urls",
                           "interaction_outcomes"]
}
```

### Agent task

> Build a React/Vite implementation that reproduces the observed public
> experience of the target page. Do not clone, fetch, or inspect the target
> repository. Use only the captured rendered observations and public page
> behavior. Reproduce layout, typography, responsive behavior, interactive
> states, and the hand-drawn visual language. Use original implementation and
> permitted assets; do not copy proprietary source code.

### Capture protocol

The observer records:

1. viewport screenshots at desktop/tablet/mobile widths
2. full-page screenshot and section crops
3. DOM semantic outline and accessibility roles
4. bounding boxes for headings, controls, sections, and code blocks
5. computed style tokens: colors, fonts, spacing, borders, radii, shadows
6. public image/font/stylesheet URLs as references, not source cloning
7. interaction traces: click, hover, focus, checkbox/radio changes, text input
8. URL/hash behavior and scroll position after navigation
9. console errors and network failure classes

The target is observed at fixed timestamps and the capture manifest is frozen
before the builder starts.

### Graders

**Deterministic:**

- required sections and semantic controls exist
- required interaction states reachable
- route/hash links resolve
- no runtime console errors
- build/typecheck/test pass
- responsive overflow absent at all required viewports
- visual asset/font loading policy respected

**Geometry/style:**

- screenshot comparison after masking dynamic sketch noise
- perceptual similarity / SSIM or pixel-diff thresholds by region
- bounding-box deviation for key elements
- color/typography token deviation

**Behavior:**

- replay the frozen interaction trace against the candidate
- compare state transitions and visible labels/roles
- verify refresh/mount behavior where target is intentionally randomized

**Human/model rubric only for residual quality:**

- visual hierarchy
- fidelity of hand-drawn visual language
- accessibility and usability
- whether implementation appears independently authored

The model grader never overrides a deterministic failure.

## Self-healing loop per harness

```text
failure event
  → normalize signature
  → retrieve only compatible validated lessons
  → propose one repair hypothesis
  → apply bounded repair
  → rerun failed check + regression subset
  → pass: record repair success
  → repeated failure: stop and create negative lesson candidate
```

## Self-learning loop per harness

```text
trace + outcome
  → reflection hypothesis
  → candidate artifact
  → applicability test
  → A/B trial
  → held-out regression
  → validated / rejected / retired
```

A learned item must be portable as a data artifact, not hidden in a harness
transcript. The package includes procedure, exceptions, verification,
provenance, and compatibility metadata.

## Harness acceptance checklist

A harness is ready only when it has:

- real installed runtime or a documented blocked dependency
- smoke task with observed output
- structured trace file
- deterministic stop/budget policy
- independent verifier path
- failure injection or real failure case
- repair path
- candidate lesson path
- eval task and grader
- no unauthorized target-repo access

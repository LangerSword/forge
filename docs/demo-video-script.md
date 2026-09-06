# Forge — truthful 3-minute demo-video script

**Target length:** exactly 3:00
**Audience:** Track 1 — Automated Agent Engineering judges
**Primary evidence run:** `submission-c0-82dffafc`
**Recording rule:** show observed output or a clearly labelled captured readback. Do not invent a new run ID, trace URL, worker success, or promotion result during editing.

## Before recording

- Record from `/home/lakshaya/forge`.
- Hide `.env`, credential prompts, browser cookies, API keys, and any terminal history containing secrets.
- Use a clean terminal with a large font and a second window for the architecture/evidence files.
- Prefer the captured final run for deterministic footage. A fresh `submission-mvp --reflect` run creates a new ID and may require configured provider credentials; it will not reproduce the observed ID by itself.
- Fill the link placeholders in the closing card only after the repository, video, and any trace/share URLs actually exist.
- The hosted Neatlogs readback was verified through the official workflow. Do not invent a repo-local CLI command for that hosted screen; show the captured dashboard/readback instead.

## Shot list and narration

The timecodes below add to **180 seconds**. Narration is written as spoken copy; bracketed text is an action or on-screen direction, not narration.

### 00:00–00:15 — Hook: memory is not learning

**Screen:** Title card, then split view of `README.md` heading and the Forge architecture diagram.

**On-screen text:**

```text
FORGE
A learning layer for agent fleets
AO executes · Forge verifies · experience stays gated
```

**Narration:**

> Agent fleets can do one-shot work, but their useful experience usually dies in a transcript. Forge turns a failure into inspectable evidence, a bounded repair, and a candidate lesson—without calling an unverified story learning.

### 00:15–00:35 — Architecture and authority boundaries

**Screen:** Scroll the architecture diagram. Highlight planner/context, verifier, repair, reflection, ledger, AO, and Neatlogs.

**Exact screen to show:** `architecture.md`, then the “Evidence boundary” paragraph.

**Narration:**

> Forge is the control plane around an execution layer. The verifier owns the pass decision. A repair is bounded. Reflection can propose a skill, but it cannot promote one. AO is the worker and worktree plane; Neatlogs observes the configured application path.

### 00:35–01:05 — Run the real bounded MVP

**Screen:** Terminal at the repo root. Use the captured terminal recording, or run the command below only with the configured local credentials.

**Exact command:**

```bash
cd /home/lakshaya/forge
uv run forge submission-mvp --reflect
```

**Highlight in output:** `baseline` failed, `repair` passed after one attempt, `final` passed, `reflection_error: null`, and the emitted `run_id`.

**Narration:**

> This is the submission vertical slice. The frozen C0 fixture starts with a NotImplementedError. Forge runs the baseline, applies one bounded repair, runs the same verifier again, and then asks the structured reflection provider for a lesson from the observed evidence. The important detail is that the final pass comes from the verifier, not from the model’s final message.

### 01:05–01:30 — Read the persisted run back

**Screen:** Terminal showing the exact final run’s JSON envelope. Scroll from the run header to the five events: goal, baseline, repair verdict, skill candidate, verdict.

**Exact command:**

```bash
uv run forge run submission-c0-82dffafc
```

**Highlight:** `status: "passed"`, `event_count: 5`, baseline `exit_code: 1`, repair/final `exit_code: 0`, and `skill_candidate` with `status: "candidate"`.

**Narration:**

> This is a ledger readback, not a screenshot of a claim. The run is passed, the red baseline is preserved, the repair took one attempt, and the reflection output is explicitly a candidate. It is not promoted just because a model generated JSON.

### 01:30–01:50 — Show the artifact and the gate boundary

**Screen:** Pretty-printed candidate JSON, then the tracked eval report.

**Exact commands:**

```bash
uv run python -m json.tool .forge/skills/failure_bound_from_evidence.json
uv run python -m json.tool evals/results/submission-c0-82dffafc.json
```

**Highlight:** `"status": "candidate"`, the evidence reference to the run, and `baseline_passed: false` / `final_passed: true`.

**Narration:**

> The artifact carries a run reference and a bounded procedure. Forge keeps it in the candidate state because applicability, A/B benefit, and held-out no-regression gates have not been demonstrated here. That is the difference between memory growing and learning being earned.

### 01:50–02:10 — Neatlogs readback

**Screen 1:** Terminal local envelope check.
**Exact command:**

```bash
uv run python -m neatlogs doctor --local --json
```

**Screen 2:** Captured Neatlogs verification dashboard/readback for the final submission workflow.

**On-screen text:**

```text
trace 6f969ec0305657630aeb0b959cc189ab
7 persisted spans
required application input/output: present
verification: pass
```

**Narration:**

> The local Doctor checks the instrumentation envelope. The captured readback for this exact workflow shows seven persisted spans and the required application input/output. This is verified Neatlogs coverage for the submission/reflection path—not a claim that every AO worker span is present.

### 02:10–02:35 — AO Runner, harness gate, and honest failure

**Screen:** First show the read-only harness readiness JSON, then AO status with health/readiness and authorized agent fields highlighted; finally show the session entries for `forge-6` and `forge-7` showing terminated state and no proof artifact.

**Exact command:**

```bash
uv run forge harnesses
uv run forge status
```

**Highlight:** `cross_harness_pass: false`, `opencode` installed/authorized, other harnesses not ready, health `ok`, readiness `ready`, and the captured worker outcome.

**Narration:**

> Forge now has an AO Runner contract: documented spawn, session polling, artifact checks, independent verification, one bounded nudge, and a watchdog kill. The readiness command refuses to call transfer ready until two harnesses are explicitly smoke-tested. AO was used for readiness checks and isolated OpenCode worker proof attempts. OpenCode was the only authorized harness observed. The two final proof workers stayed working without producing the requested artifact and were terminated. We do not edit that story into autonomous success: health, readiness, or an idle session is not an artifact.

### 02:35–03:00 — Close with the actual claim

**Screen:** Closing card with the repository, live Vercel evidence website, demo, and trace links. Show `docs/SUBMISSION.md` limitations briefly.

**On-screen text:**

```text
Observed: failure → repair → verification → candidate → trace
Not claimed: AO autonomy · cross-harness transfer · promoted skill
```

**Narration:**

> Forge’s result is a trustworthy learning boundary: a real failure became a verified repair, a traceable candidate, and a read-back run. The next proof is a second authorized harness and a held-out comparison. Until those exist, Forge reports them as open work. AO executes, Forge validates, and unsupported success claims stay out of the submission.

## Recording checklist

- [ ] The terminal shows `/home/lakshaya/forge`, not a secret-bearing setup screen.
- [ ] The final run ID is exactly `submission-c0-82dffafc` wherever the captured evidence is referenced.
- [ ] The C0 baseline is shown as failed before the repair; do not show only the green result.
- [ ] The skill is visibly labelled `candidate`, never `validated` or `promoted`.
- [ ] Neatlogs trace ID and seven-span readback are shown with their exact scope.
- [ ] AO health/readiness and OpenCode authorization are shown alongside the missing-artifact worker outcome.
- [ ] No second harness is shown as authorized or successful.
- [ ] No Supermemory, production deployment, store publication, or full-fleet trace claim appears in voiceover or overlays.
- [ ] The final links are real before publishing; placeholders are not presented as URLs.

## Claims not to make

Do **not** say any of the following:

- “AO autonomously completed the C0 task.” The final C0 evidence is the local Forge verifier/repair path; the explicitly approved AO proof workers had no artifact and were terminated.
- “Forge transferred the skill to another harness.” Only OpenCode was observed authorized; no cross-harness run exists.
- “The skill is validated,” “promoted,” or “generalizes.” The observed skill status is `candidate`; G1/G2/G3 evidence is open.
- “Neatlogs traced the whole fleet” or “all AO workers are covered.” The verified scope is the seven-span submission/reflection workflow.
- “Hermes was an AO worker.” Hermes is an external sidecar/development boundary, not present in AO’s authorized catalog.
- “Supermemory stores Forge’s memory.” It is a future integration; local Forge files and the ledger are authoritative now.
- “Forge deployed an app to production,” “published an APK,” or “runs a hosted multi-tenant service.” Those are outside this observed submission.
- Any percentage, cost, speedup, token saving, or statistical improvement not present in an observed comparison table.

## Optional end-card evidence references

Use only after checking the target exists:

- Repository: `https://github.com/LangerSword/forge`
- Live evidence website: `https://web-rust-three-63.vercel.app/`
- Video: `<DEMO_VIDEO_URL>`
- Neatlogs trace: `<NEATLOGS_TRACE_URL_FOR_6F969EC0305657630AEB0B959CC189AB>`
- AO evidence capture: `<AO_EVIDENCE_URL_OR_LOCAL_CAPTURE>`

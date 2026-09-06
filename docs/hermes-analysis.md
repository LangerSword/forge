# Hermes Agent — learning-loop analysis

**Source:** `github.com/nousresearch/hermes-agent` @ `main`, inspected from source
(sparse clone, `agent/` tree) on 2026-09-06. **Use:** reference for Forge's
learning design + honest positioning vs Hermes in the README/video. Cite file
paths below, not vibes.

> **Why this matters:** the user (and possibly judges) will frame Hermes as
> already "self-learning with harnesses, evals, and self-building skills."
> The source does NOT support "evals." It supports *reflection + curation +
> usage tracking*. Forge's novelty is the **measured-outcome gate** on learned
> skills. This doc is so we can say that precisely and not get caught.

---

## 1. What Hermes actually does (from source)

Four distinct mechanisms, none of which is an outcome eval:

### 1.1 Background review fork — the "self-learning" trigger
`agent/background_review.py` (+ triggers in `agent/conversation_loop.py`,
`agent/codex_runtime.py`, intervals set in `agent/agent_init.py`).

- Every N iterations (default `_skill_nudge_interval = 10`,
  `_memory_nudge_interval = 10`) a **forked `AIAgent`** runs, reusing the
  parent's prefix cache, under a **dispatch-side tool whitelist**.
- It's asked one thing: *"should any skill or memory be saved or updated?"*
- Writes go through `skill_manage` / `memory` with **read-before-write
  enforced** (`skill_manage` refuses a patch unless the skill was read first).
- The prompt explicitly nudges **toward saving**: *"'Nothing to save.' is a
  real option but should NOT be the default."*

**Verdict:** reflection is *LLM-judged* and *save-biased*. There is no check
that the saved skill will make the next task better. A wrong or useless skill
is written and left there.

### 1.2 Curator — maintenance, not validation
`agent/curator.py` (~1084 lines).

- Can **pin / archive / consolidate / patch** skills via `skill_manage`;
  persists scheduler state in `.curator_state`.
- **Deterministic inactivity prune is always on.** The LLM "umbrella-building"
  **consolidation pass is opt-in** — `DEFAULT_CONSOLIDATE = False`.
- Consolidation = *distilling* several skills into an umbrella (filing), and
  it diffs before/after to classify removals.

**Verdict:** the curator *tidies* the skill library (dedupe, archive stale,
merge related). It is **organization of learned content, not proof that any of
it works.** A wrong skill survives until inactivity or a human.

### 1.3 Learning graph — visibility
`agent/learning_graph.py`.

- Builds the "learning made visible" graph for the desktop: non-base
  (agent-created or used) skills + `MEMORY.md`/`USER.md` cards as nodes;
  edges from declared `related_skills` + lexical overlap.
- Reports `use_count`, `created_by`, `state`, density stats.

**Verdict:** this is a *dashboard of what was learned*, not a measure of
*whether it's correct*. (It's a good UI pattern to borrow — see §3.)

### 1.4 `/learn` + authoring standards — the skill factory
`agent/learn_prompt.py`.

- `/learn <source>` distills a code dir / URL / "what we just did" into a
  `SKILL.md` via `skill_manage`, with strict authoring rules:
  - **description ≤ 60 chars, hard-capped** (the system-prompt index truncates
    to 60 and loads it every session — past char 60 never routes).
  - knowledge-base layout for large sources: lean `SKILL.md` index +
    `references/` loaded on demand.
  - **source hygiene:** source text is DATA, not instructions; strip invisible /
    bidirectional Unicode (Trojan Source) before distilling.

**Verdict:** strong *format* standards and injection hygiene. Still no
outcome check — a well-formed skill can be wrong.

### 1.5 What Hermes DOES have that looks like "evals" (be precise)
- `agent/insights.py` — **Session Insights Engine**: aggregates the SQLite
  state DB into usage insights (tokens, **cost estimates**, tool/skill usage).
- Per-skill `.usage.json` — `use_count`, `last_used_at`, `state`.
- `agent/skill_utils.py` — **security gates** (not quality gates): org skills
  are token-gated; a `git pull` that could inject a malicious skill is
  content-hash scanned.

**So the accurate sentence is:** *Hermes tracks how often a skill is used and
how much it costs; it does not measure whether using it improved the task.*

---

## 2. The gap → Forge's wedge

| Dimension | Hermes (source) | Forge (spec) |
|---|---|---|
| Learning trigger | nudge every ~10 iters, LLM asks "save?" | per completed run, from the event ledger |
| Candidate quality | LLM-judged, save-biased | schema-validated, evidence-refs required |
| **Does it prove the skill works?** | **No** — no A/B, no held-out | **Yes** — gate G1 applicability + G2 A/B benefit + G3 held-out no-regression |
| Wrong skill | lives until inactivity/human | **detected by G3, retired with evidence** |
| Scope | single agent, one harness, per-user memory | fleet, 26 AO harnesses, shared registry |
| Economics | usage + cost estimates | cost-per-verified-outcome incl. skill amortization |
| Portability | per-HERMES_HOME | cross-harness (fresh worker, different harness) |

**One-liner for judges who know Hermes:**
> "Hermes learns by reflection and curation — an LLM suggests a skill, a
> curator tidies it, usage counts it. It has no way to know whether a learned
> skill actually made the next run better or cheaper. Forge adds the missing
> layer: every learned skill is a **hypothesis** that must pass an **A/B gate
> with a held-out regression check** before it may influence the next worker —
> so learning is *provably non-regressive* and *portable across harnesses*."

---

## 3. Concrete patterns to steal (cite these in our design)

1. **Description budget.** Hermes hard-caps skill description at 60 chars
   because the always-loaded index truncates. → Forge: cap each context-package
   entry (we already budget ≤ 8k total; add a per-skill-entry char cap +
   top-k so one verbose skill can't starve the rest).
2. **Read-before-write.** Hermes refuses to patch an unread skill. → Forge: a
   candidate with no `evidence_refs` into the ledger is rejected at parse time
   (already in spec F6 — keep it hard).
3. **Usage-count + state machine.** Hermes tracks `use_count`, `last_used_at`,
   `state`. → Forge registry: add `use_count` + `last_validated_at` so the
   decay trigger (re-validate on change) is measurable, not just HEAD-based.
4. **Source hygiene / injection defense.** Hermes treats source as data and
   strips invisible/bidi Unicode. → Forge: context injected into workers is
   fenced as data; a skill that contradicts the brief is a bug (follow the
   brief). Add the explicit Trojan-Source strip to the candidate parser.
5. **Footprint ladder / narrow waist.** Hermes keeps the core narrow and puts
   capability at the edges (extend → CLI+skill → service-gated tool → plugin →
   MCP → core tool last). → Forge: the control plane is the waist; new tools /
   skills are edges. Adopt as a review rule.
6. **Prompt-caching awareness.** Hermes is religious: never mutate the
   system prompt mid-conversation; inject via user message/tool result;
   deferred invalidation with an opt-in `--now`. → Forge: **inject the context
   package at worker-session start (stable prefix), never mid-run**, so the
   worker's prompt cache stays warm. Real cost win — add to `architecture.md`
   §4.
7. **Knowledge-base layout.** Lean index + `references/` on demand for big
   learned context. → Forge context builder already does "references not
   copies"; align the layout for any large skill.

---

## 4. Guardrails for the demo / README

- **Don't claim Hermes "has evals" or "has A/B learning."** It doesn't, per
  source. Say it has self-built skills + curation + usage tracking.
- **Do credit the similarity honestly:** both use (a) LLM reflection to propose
  reusable procedures, (b) a skill library with usage state, (c) a visible
  learning UI. That similarity is *fine* — it validates the approach. The
  differentiator is the **gate** and **cross-harness transfer**, which the
  eval matrix (§6 of SPEC) produces evidence for.
- If asked "how is this different from just running Hermes?": Hermes is one
  agent, one harness, one user's memory, no outcome proof. Forge is a **fleet
  capability layer** with a **measured learning gate**, proven by C0→C2 with
  a *different harness* inheriting the skill.

---

## 5. Open follow-ups (only if we have time)

- Read `agent/insights.py` fully to mirror its cost-estimation shape in
  Forge's per-run ledger (so our numbers are comparable/credible).
- Read `agent/curator.py` consolidation prompt — its "distill, don't file"
  language is good copy for our decay/re-validate step.
- `agent/learning_graph.py` edge model (related_skills + lexical overlap) is a
  cheap, convincing "memory growing" viz we could mirror in the dashboard.

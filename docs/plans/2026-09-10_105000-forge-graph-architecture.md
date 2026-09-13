# Forge — Full System Graph & Context/Memory Architecture

> **Date:** 2026-09-10  
> **Status:** Planning document — no build.  
> **Purpose:** Define Forge as a **graph execution engine** where nodes are agents, judges, and verifiers connected by typed edges, with Supermemory as the **context fabric** that sits alongside the scheduler — every node recalls relevant memory before acting and writes structured observations after acting, so context survives across handoffs without bloating the token window.

---

## 1. The core insight

The research doc and the metacognition site converge on the same missing piece:

> **Agents lose context at handoffs because we pass transcripts. We should pass structured memory — consolidated, linked, recall-tuned.**

MetaCognition's mechanism:

```text
Capture → Consolidate → Link → Recall
```

Supermemory's promise: one API, persistent user/project memory across agents and sessions.

Forge's opportunity: **make the execution graph *itself* the memory-carrying structure**. Every node produces structured observations that feed into Supermemory. Every node's context is *built from* Supermemory recall — not from the previous node's raw output.

---

## 2. The graph model

Forge defines a **directed execution graph** where:

- **Nodes** are units of agentic work
- **Edges** carry memory references, not raw outputs
- **Subgraph expansion** happens recursively at any node
- **Routing** between nodes is done by judges (deterministic or LLM)

### Node types

| Node | Executes | Produces |
|---|---|---|
| `Planner` | Decomposes goal into subgraph | `GraphSpec` — subgraph definition |
| `Specialist` | Works on a bounded task with tools | `NodeResult` — structured output + evidence refs |
| `Judge` | Evaluates a `NodeResult` against a criterion | `RoutingDecision` — continue/retry/reroute/escalate |
| `Verifier` | Runs deterministic checks on artifacts | `VerificationResult` — passed/failed + evidence |
| `Reflector` | Analyzes failure evidence, proposes skill | `SkillCandidate` — strict candidate only |
| `Evaluator` | Runs A/B + held-out comparison | `GateVerdict` — validated/rejected |
| `MemoryNode` | Writes to / reads from Supermemory | `RecallContext` — structured context for next node |
| `Aggregator` | Collects results from parallel branches | `AggregatedResult` — merged outputs |

### Runtime graph semantics

```
Forge Commander
    │
    ├─ expands goal into GraphSpec (recursive, multi-level)
    │
    ├─ dispatches ready nodes (dependencies satisfied)
    │
    ├─ each node:
    │     ├─ RECALL context from Supermemory
    │     ├─ EXECUTE (agent work, tool calls, verifier checks)
    │     ├─ CAPTURE structured observations to Supermemory
    │     └─ returns NodeResult
    │
    ├─ JudgeNode inspects NodeResult:
    │     ├─ passed → next sibling/dependency
    │     ├─ failed → retry/reroute/reflect
    │     └─ ambiguous → escalate model or human
    │
    └─ Node may self-expand (PlannerNode creates subgraph)
```

### Key structural properties

1. **Recursive subgraph expansion:** any `Planner` node returns a `GraphSpec` that Forge executes as a sub-execution with its own scheduler, deadlines, and memory context.

2. **Bounded breadth and depth:** `max_parallel` and `max_depth` are hard constraints per graph level. A deep subgraph inherits its parent's budget minus used budget.

3. **Deterministic routing edges:** edges are typed:
   - `sequence` — run B after A
   - `dependency` — run B after A completes (any status)
   - `gate` — run B only if A passed
   - `parallel` — run A and B concurrently, wait for both
   - `judge` — run Judge on A's result, route based on decision

4. **Failure isolation:** a failed node blocks dependents but does not fail the entire graph unless no alternative path exists. Alternatives: retry, substitute node, escalate, fail-with-evidence.

5. **Budget inheritance:** each subgraph receives `remaining_budget = parent.goal.max_minutes * 60 - elapsed`. Deadline-exceeded nodes persist `stopped` as terminal evidence.

---

## 3. The context-loss problem and the architectural fix

### The standard pattern (broken)

```
Specialist A finishes
    │
    ├─ writes artifact
    ├─ full transcript grows to 500K tokens
    │
    ▼
Handoff to Specialist B:
    "Here is everything A did. Continue."
    │
    ├─ Specialist B never reads it all
    ├─ critical context is buried in noise
    ├─ lost at the next handoff anyway
    └─ every handoff bleeds context
```

### MetaCognition's diagnosis

The metacognition model identifies the same failure:

> **Context is lost at handoffs because we pass flat transcripts instead of structured memories.**

Their mechanism (capture → consolidate → link → recall) solves this by:

1. **Capture** — every interaction becomes a *memory with an activation level*, not a text blob
2. **Consolidate** — replay strengthens what keeps being used, cools the rest
3. **Link** — related memories stay connected; recalling one brings up relevant neighbours
4. **Recall** — sharpness tuned at moment of use; nothing rewritten or retrained

### Forge + Supermemory architectural fix

The key change: **nodes do NOT pass transcripts to each other.**
Supermemory sits **alongside the Graph Scheduler**, not below the nodes.
Every node's lifecycle is:

```text
     ┌─────────────────────────────────┐
     │        FORGE COMMANDER          │
     │  ┌────────────┐ ┌────────────┐  │
     │  │   Graph    │ │Supermemory │  │
     │  │ Scheduler  │ │ (context   │  │
     │  │ dispatch   │ │  fabric)   │  │
     │  │ routing    │ │ recall /   │  │
     │  │ judges     │ │ write      │  │
     │  └─────┬──────┘ └─────┬──────┘  │
     └───────┼───────────────┼─────────┘
             │               │
             ▼               ▼
     Node starts:
       ① RECALL context from Supermemory
       ② EXECUTE (agent work, tool calls)
       ③ WRITE observations to Supermemory
       ④ Return NodeResult
```

This is the corrected architecture. Supermemory is the **context brain of the commander** — every node consults it before acting and writes into it after acting. The scheduler dispatches; Supermemory provides the context. They are peers at the commander level, not stacked.

### How this solves the token burden problem (the critical mechanism)

The user's question: *"How does Supermemory enlarge and lengthen context without burdening the token window every time it recalls?"*

Supermemory's actual published mechanism answers exactly this:

1. **learner-1** extracts structured learnings from raw interaction data — not raw transcripts — and stores them in a **vector-graph database** (dense, interconnected, time-aware memories, not blob storage).

2. **Update, merge, infer, forget:** Supermemory does not accumulate everything. It:
   - Updates existing memories when new information supersedes old
   - Merges related memories into consolidated representations
   - Infers connections across memories (graph linking)
   - Forgets memories that decay or become irrelevant (temporary facts expire after their date passes)
   - Resolves contradictions automatically

3. **Injection via hooks (not dumping):** When a node recalls, Supermemory does NOT dump a large memory store into the prompt. Instead:
   - **SuperRAG (Retrieval)** pulls only semantically relevant context — the facts that matter to the current query, not the full history
   - **Profiles** surface concise project/user summaries instead of raw history
   - The result is "a smaller, denser context that costs less and performs better" (Supermemory's own documentation)
   - The actual token injection is bounded and selective

4. **No vector DB config, no embedding pipelines, no chunking strategies** — Forge just calls a single API: `client.memory.write()` and `client.profile()` / `client.search()`. The hard infrastructure (embedding, indexing, consolidation, forgetting) is handled by Supermemory's service.

**Result for Forge:** A node that recalls receives exactly the relevant memories — consolidated, linked, and activated — injected as a compact token budget. Not the full history, not the raw transcript, not a 200K token dump. The context window is *enlarged in effective capability* without being *expanded in raw token cost*.

### What Supermemory provides in this architecture (corrected position)

| Function | Where it sits in Forge |
|---|---|
| **Write** | Every node, on completion, writes structured observations to Supermemory via API |
| **Link** | Supermemory's vector-graph DB links memories across nodes automatically |
| **Consolidate** | learner-1 merges, updates, forgets — the store stays sharp |
| **Recall** | Every node, on start, queries Supermemory for relevant context — returns compact, semantically-relevant memories only |
| **Cross-agent** | Supermemory sits at the commander level; all node types (Planner, Specialist, Judge, etc.) share the same fabric |
| **Profile** | Supermemory maintains a compact user/project profile that acts as a dense summary instead of raw history |

The old section 4 table ("What Supermemory provides") positioned Supermemory as a below-layer store. The corrected position is: **Supermemory is the commander-side context fabric alongside the scheduler, above the nodes.**

---

## 4. A concrete example: product-build task through the graph

This is the full execution trace for a user asking "Build a feature similar to drively.dev into my project."

### Top-level graph (Forge Commander expands)

```text
Goal: "Study drively.dev, understand its style, implement in my project"
    │
    ├─ [Planner] Decompose into:
    │     ├─ Research (study the reference site)
    │     ├─ Inspect (read the user's project)
    │     ├─ Plan (determine what to build)
    │     ├─ Implement (build the feature)
    │     └─ Verify (check acceptance criteria)
    │
    ├─ [Judge] inspect Plan quality
    │     ├─ passed → dispatch Implement
    │     └─ failed → reroute back to Planner with feedback
    │
    ├─ [Implement] executes
    │     └─ self-expands into its own subgraph:
    │           ├─ [Specialist] Frontend component
    │           ├─ [Specialist] Styling/SASS
    │           ├─ [Specialist] Integration
    │           └─ [Verifier] Check each artifact
    │
    ├─ [Verifier] independent acceptance check
    │     └─ passed/failed/blocked
    │
    ├─ [Reflector] if failure → propose candidate skill
    │
    └─ [Evaluator] if candidate exists → A/B + heldout
```

### What Supermemory carries across handoffs

When the Research node finishes, it does NOT dump its transcript into the Inspection node.

It writes structured memory to Supermemory:

```json
{
  "node_id": "research-1",
  "goal": "understand drively.dev visual style and interaction model",
  "observations": [
    {"kind": "design_pattern", "description": "card-based layout with frosted glass", "source_url": "https://drively.dev"},
    {"kind": "design_pattern", "description": "pastel color palette, heavy use of rounded corners"},
    {"kind": "tech_used", "description": "Next.js 14, Tailwind, framer-motion"},
    {"kind": "interaction", "description": "page transitions via route-based animations"}
  ],
  "evidence_refs": ["run:research-1", "artifact:observation.json"],
  "activation": "high"  // recent, relevant to the user's goal
}
```

When the Implement node starts, it recalls:

```text
query: "What design patterns and constraints are relevant to implementing the feature?"
response from Supermemory:
  - research-1's observations (activated, linked to the project)
  - inspect-1's project structure (linked because same goal)
  - plan-1's architecture decisions (linked because they depend on research)
```

The Implement node receives **only what is relevant** — not the research agent's full transcript, not the raw DOM of drively.dev, not the scroll positions. The context is smaller, sharper, and provenance-tracked.

---

## 5. Where the current Forge code fits

| Current module | Maps to graph node | Status |
|---|---|---|
| `FleetController` | Graph scheduler | ✅ Works, needs edge typing |
| `ToolRegistry` | Tool executor inside Specialist nodes | ✅ Works |
| `Verifier` | `Verifier` node | ✅ Works |
| `PlaybookRegistry` | Skill/playbook retrieval layer | ✅ Works |
| `evaluate_candidate` | `Evaluator` node | ✅ Works |
| `reflect_failure` | `Reflector` node | ✅ Works |
| `Ledger` | Evidence store | ✅ Works |
| `tracing.py` / `neatlogs.py` | Observation capture (first step) | ✅ Works |
| `schema.GoalSpec` | Graph input | ✅ Works |
| `schema.TaskGraph` | Graph spec (needs expansion for node types, edge types, subgraph recursion) | ⚠️ Partial |
| `schema.RunResult` | NodeResult (needs expansion for memory refs, recall context) | ⚠️ Partial |
| — | Supermemory adapter | 🔴 Missing |
| — | Node runtime (`PlannerNode`, `SpecialistNode`, `JudgeNode` etc.) | 🔴 Missing |
| — | Graph executor (recursive subgraph dispatch) | 🔴 Missing |
| — | Memory write/recall protocol | 🔴 Missing |

---

## 6. Build order (prioritized)

### Phase 0 — Graph execution core (P0)

The existing `FleetController` is already a graph scheduler — it dispatches `TaskGraph` nodes with dependencies and parallelism. But it needs:

1. **Node types** — `Planner`, `Specialist`, `Judge`, `Verifier`, `Reflector`, `Evaluator`, `MemoryNode` — each with its own runtime behavior (LLM call, tool execution, deterministic check, memory query).
2. **Edge types** — `sequence`, `dependency`, `gate`, `parallel`, `judge`. A judge edge does not just pass/fail — it routes to different downstream nodes based on the verdict.
3. **Recursive subgraph expansion** — a `Planner` node returns a `GraphSpec`, not a single result. The scheduler must dispatch that subgraph with inherited budget and context.
4. **`NodeResult`** — the universal output contract. Must include:
   - `status` (passed/failed/blocked/stopped)
   - `observations` (structured memory entries for Supermemory)
   - `evidence_refs` (links back to the ledger)
   - `subgraph` (if the node expanded, the subgraph's result)

### Phase 1 — Supermemory adapter (P0)

1. **Memory write protocol** — every node, on completion, writes structured observations to Supermemory:
   - Node type + ID
   - Goal + task family
   - Observations (typed: `design_pattern`, `tech_used`, `interaction`, `failure`, `decision`, `artifact`)
   - Evidence refs (ledger run IDs, artifact paths)
   - Activation level (high for completion, medium for side observations)
2. **Memory recall protocol** — every node, on start, queries Supermemory:
   - Current goal + task family
   - Relevant node types
   - Time window
   - Returns consolidated, linked, activated memories
3. **Context construction** — the combined recall output becomes the node's injected context, replacing the old transcript-passing pattern.

### Phase 2 — Judge-as-routing (P0)

1. **Typed judge edges**: `Judge` node evaluates a `NodeResult` and returns a `RoutingDecision`:
   - `continue` (proceed to next node in sequence)
   - `retry` (re-execute this node)
   - `reroute` (dispatch a different node)
   - `escalate` (stronger model or human)
   - `stop` (fail the branch with evidence)
2. **Deterministic judges first** — schema validation, artifact-exists checks, tool-call-count limits. LLM judges second — evidence-quality, design-coherence, plan-correctness.

### Phase 3 — Reflective learning on graph runs (P0)

Same as the current `LearningExperiment` pattern, but now integrated into the graph:
- A `Reflector` node observes *all* node results in a failed graph run
- Proposes a candidate skill that applies to specific node types or edge patterns
- `Evaluator` gates it across repeated graph executions
- Validated playbooks live in Supermemory and are recalled on matching task families

### Phase 4 — Persist graph state (P1)

- `GraphRun` — durable record of the full execution graph: nodes, edges, subgraphs, decisions, timing, budget
- `NodeAttempt` — compare-and-set checkpoint per graph node (extends existing `task_attempts` table)
- `GraphResume` — reconstruct incomplete graph execution after process restart

### Phase 5 — AO integration (P1)

- `Specialist` node dispatches to AO worker for long-running tasks
- `Judge` node monitors AO progress (via existing `watchdog.py`)
- Graph scheduler treats AO sessions as long-lived node executions

### Phase 6 — Cross-agent, cross-harness transfer (P2)

- Validated playbooks from Supermemory are recalled by different harnesses
- `Specialist` node adapts context to harness-specific prompt format

---

## 7. Verified vs aspirational — every node classified

| Node / Edge | Current Forge | Graph plan status | Evidence |
|---|---|---|---|
| Graph scheduler (dependency, parallel) | `FleetController` | ✅ Verified | 122 tests |
| ToolRegistry + allowlist | `tooling.py` | ✅ Verified | 2 tests |
| Deterministic verifier | `verifier.py` | ✅ Verified | 1 test |
| ComparisonResult (baseline vs learned) | `schema.py` | ✅ Verified | 9 tests |
| LearningExperiment runner | `experiment.py` | ✅ Verified | 3 tests |
| PlaybookRegistry (select by family) | `playbook.py` | ✅ Verified | 2 tests |
| CLI experiment commands | `cli.py` | ✅ Verified | Full suite passes |
| Edge types (sequence/dependency/gate/parallel/judge) | — | 🟡 Planned — not built | Design only |
| Recursive subgraph expansion | — | 🟡 Planned — not built | Design only |
| Node types (Planner, Specialist, Judge, Memory) | — | 🟡 Planned — not built | Design only |
| Judge-as-routing (continue/retry/reroute/escalate) | — | 🟡 Planned — not built | Design only |
| Supermemory write protocol | — | 🔴 Missing — next build | No code |
| Supermemory recall protocol | — | 🔴 Missing — next build | No code |
| MemoryNode as a first-class graph node | — | 🔴 Missing — next build | No code |
| Context construction from recall (not transcript) | — | 🔴 Missing — next build | No code |
| Multi-judge disagreement → escalation | — | 🔴 Research | No code |
| Cross-harness transfer via Supermemory | — | 🔴 P2 | No code |

---

## 8. Open questions for discussion

1. **Supermemory adapter: local vs SaaS.** Supermemory offers a local mode (`pip install supermemory`, local server at `http://localhost:6767`) and a cloud API. A local adapter lets Forge develop the graph-memory integration without provisioning remote infra or an API key. The plan assumes: **local adapter first**, then cloud API as a configurable backend behind the same adapter interface.

2. **Memory schema design:** what observation types does the graph need? The draft includes `design_pattern`, `tech_used`, `interaction`, `failure`, `decision`, `artifact` — but this should grow as we find what the graph actually needs to recall.

3. **What Supermemory operations does Forge call?** Supermemory's API includes at minimum:
   - `memory.write(text, source, metadata)` — write a structured observation
   - `profile(tag, query)` — get a compact user/project profile
   - `search(query, tags)` — search memories semantically
   - The `MemoryNode` type wraps these operations.

4. **Write timing:** every node writes on completion. Should long-running nodes also write mid-execution (e.g., per-tool-call) so a Judge can detect stagnation early? The plan suggests mid-execution writes for Specialist nodes, completion-only for fast nodes (Planner, Verifier).

5. **Supermemory vs existing Ledger:** the Ledger stores deterministic evidence (tool calls, verifier checks, trials). Supermemory stores contextual memory (observations, patterns, user preferences). They are complementary — Ledger is the authoritative evidence record, Supermemory is the context retrieval layer. Both survive across sessions. Neither replaces the other.

6. **Multi-judge architecture:** the metacognition approach favors specialized judges (ProgressJudge, EvidenceJudge, PolicyJudge) combined with deterministic policy routing. Should Forge start with one general Judge or build multiple specialized judges from the start?

---

## 9. Verification

After any Phase is built:

```bash
# Run the full suite
uv run pytest -q

# Run the graph executor tests
uv run pytest tests/test_graph.py -v

# Run the memory adapter tests
uv run pytest tests/test_supermemory.py -v

# Run a sample graph from CLI
uv run forge graph goals/sample-graph.json
```

All 122 existing tests must remain green after each phase. New graph tests add to the count, never subtract.

---

## 10. Summary

The graph architecture has two peers at the commander level, with evidence below:

```text
                         GOAL
                           │
                           ▼
             ┌─────────────────────────────┐
             │      FORGE COMMANDER        │
             │                             │
             │  ┌────────────┐ ┌────────┐  │
             │  │   Graph    │ │Super-  │  │
             │  │ Scheduler  │ │memory  │  │
             │  │ dispatch,  │ │context │  │
             │  │ routing,   │ │fabric  │  │
             │  │ judges     │ │recall/ │  │
             │  │            │ │write   │  │
             │  └─────┬──────┘ └───┬────┘  │
             └────────┼────────────┼───────┘
                      │            │
                      ▼            ▼
             ┌─────────────────────────────┐
             │       NODE LAYER            │
             │  Planner | Specialist       │
             │  Judge | Verifier           │
             │  Reflector | Evaluator      │
             │  Aggregator                 │
             │                             │
             │  Each node:                 │
             │  ① Recall from Supermemory  │
             │  ② Execute with tools/AO    │
             │  ③ Write to Supermemory     │
             └───────────┬─────────────────┘
                         │
                         ▼
             ┌─────────────────────────────┐
             │       EVIDENCE LAYER        │
             │  Ledger (authoritative)     │
             │  Neatlogs (trace mirror)    │
             └─────────────────────────────┘
```

The critical difference from the current codebase:

| Current | Graph plan |
|---|---|
| `FleetController` dispatches `TaskGraph` with one-level tasks | Graph scheduler dispatches recursive, typed-node graphs with edge routing |
| Context passed via `ContextPackage.to_prompt()` — string serialization | Context built from Supermemory recall — structured memory, not flat text |
| `learning_hook` returns candidate names | `Reflector` node writes to Supermemory, `Evaluator` node gates |
| No memory layer between executions | **Supermemory as commander-side context fabric** — peers with scheduler, not below nodes |
| Handoffs pass full transcripts → token bloat | Handoffs pass memory references. Supermemory injects only compact, semantically-relevant context tokens via SuperRAG + profiles |
| Token cost grows with every handoff (transcript accumulates) | Token cost stays bounded — SuperRAG pulls selective context, learner-1 consolidates/forgets, profiles give dense summaries |
| Context lost at handoffs | Context persists across handoffs via Supermemory's linked memory graph |

The core insight: **the execution graph and Supermemory together form the Forge Commander — one dispatches nodes, the other provides context.** Nodes never pass transcripts; they write observations to Supermemory and recall only what is relevant. This solves context loss at handoffs without growing the token window.
# Step 5: Identify and Decorate Orchestration Functions

This project calls LLM SDKs directly (no agent framework). The LLM client was wrapped with `neatlogs.wrap()` in Step 4; here you decorate YOUR orchestration functions.

## The One Rule That Matters Most

Ask for EVERY function: **"Is this directly triggered by the user (CLI command, HTTP endpoint, job), or is it internal?"**

- User-triggered → `@neatlogs.span(kind="WORKFLOW")` — this is the TRACE ROOT
- Internal orchestrator (calls other functions, no LLM call itself) → `@neatlogs.span(kind="CHAIN")`
- Contains meaningful multi-step orchestration around one or more captured calls → `@neatlogs.span(kind="CHAIN")`. A function that only forwards one wrapped provider call needs no decorator.
- Discrete I/O or tool capability → `@neatlogs.span(kind="TOOL")` (Step 7)
- Pure utility (<3 lines, formatting, config) → no decorator

## WRONG vs RIGHT — Classification

```python
# ❌ WRONG — run_pipeline is NOT a WORKFLOW. It's internal. Nobody calls it directly.
@neatlogs.span(kind="WORKFLOW")
def run_pipeline(text, settings):
    return asyncio.run(process_document(text, settings))

# ✅ RIGHT — the click command IS the user-facing entry point. THIS is the WORKFLOW.
@cli.command()
@click.argument("file_path")
@neatlogs.span(kind="WORKFLOW", name="process")
def process(file_path: str):
    text = read_document(file_path)
    result = run_pipeline(text, settings)
    write_document(result.report, output_path)

# ✅ RIGHT — internal orchestrators are CHAIN
@neatlogs.span(kind="CHAIN", name="run_pipeline")
def run_pipeline(text, settings):
    return asyncio.run(process_document(text, settings))
```

## Why This Matters: Trace Context Binding

All spans in one execution MUST share one trace. Spans inherit their parent's trace context. If a decorated function is called from an UNDECORATED function, it starts a NEW orphan trace.

```
# WITHOUT decorating the entry point:
process() [no span]
  ├── run_pipeline()   → orphan trace A
  └── summarize()      → orphan trace B (lost!)

# WITH the entry point as WORKFLOW:
process() [WORKFLOW span — trace root]
  ├── run_pipeline()   → child (same trace!)
  │     └── summarize() [CHAIN] → grandchild (same trace!)
  │           └── LLM call (on wrapped client) → same trace!
  └── write_document() → child (same trace!)
```

## Decision Tree

1. **User-facing entry point?** (click command, FastAPI route, celery task, `main()`)
   → `@neatlogs.span(kind="WORKFLOW")`
2. **Contains a direct LLM API call?** (`client.chat.completions.create`, `client.messages.create`, etc.)
   → `@neatlogs.span(kind="CHAIN")` only when the function performs real multi-step orchestration; never add an LLM trace around an already captured provider call.
   Exception: skip if the function ONLY does `return client.chat.completions.create(...)` with zero other logic — the call on the wrapped client is already traced.
3. **Orchestrates multiple child functions, no LLM call?**
   → `@neatlogs.span(kind="CHAIN")`
4. **Discrete I/O / external API?**
   → `@neatlogs.span(kind="TOOL")` (Step 7)
5. **Pure utility?**
   → no decorator

## Decorator Placement

```python
# Below click/typer decorators, closest to def:
@cli.command()
@click.argument("file_path")
@neatlogs.span(kind="WORKFLOW", name="process")
def process(file_path: str):
    ...

# Below @retry, closest to def:
@retry(stop=stop_after_attempt(3))
@neatlogs.span(kind="CHAIN", name="summarize_chunk")
async def summarize_chunk(text, settings):
    ...
```

## Action

1. Read ALL source files from the entry point outward.
2. Each CLI command / endpoint / job → `@span(kind="WORKFLOW")`.
3. Each internal function with an LLM call → `@span(kind="CHAIN")`.
4. Each internal orchestrator (no LLM, calls children) → `@span(kind="CHAIN")`.
5. Add `import neatlogs` to each file that gets decorators.

## Verify BEFORE moving to Step 6

1. Every CLI command / route handler has `@span(kind="WORKFLOW")`. Count them.
2. No internal function (run_pipeline, process_document) has kind="WORKFLOW" — those are CHAIN.
3. The WORKFLOW span is the outermost decorated function; everything else runs beneath it.

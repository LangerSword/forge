# Step 7: Decorate Tool Functions

## Action

Scan the project for functions that act as discrete tools/capabilities the pipeline invokes — file I/O, external API calls, search, parsing — and decorate them with `@neatlogs.span(kind="TOOL", tool_name="...", description="...")`.

This project uses LLM SDKs directly (no agent framework), so there are no framework-managed `@tool` functions to worry about. Every tool-like function is yours to decorate.

## What Qualifies as a TOOL

A function is a TOOL if it:
- Performs a single discrete operation (read file, search, parse, count tokens, call an external API)
- Has a clear input/output contract
- Is called by orchestration functions as a capability
- Wraps an external service, API, or I/O operation NOT captured by the wrapped LLM client

## Examples

```python
# ✅ RIGHT — standalone tool function
@neatlogs.span(kind="TOOL", tool_name="read_document", description="Read document from disk")
def read_document(file_path: str) -> str:
    with open(file_path, 'r') as f:
        return f.read()

# ✅ RIGHT — external API call, not captured by the wrapped LLM client
@neatlogs.span(kind="TOOL", tool_name="web_search", description="Search the web")
def web_search(query: str) -> list[str]:
    return search_api.search(query)

# ✅ RIGHT — vector retrieval (use RETRIEVER, not TOOL, when fetching context)
@neatlogs.span(kind="RETRIEVER", tool_name="similarity_search")
def fetch_context(query_embedding: list[float]) -> list[str]:
    return vector_store.query(query_embedding, top_k=5)
```

## What is NOT a TOOL

- The LLM call itself — the wrapped client owns that canonical LLM span. Do not add a manual LLM or TOOL span around it.
- Pure utility helpers (string formatting, list manipulation)
- Functions with < 3 lines of trivial logic
- Internal helper functions only called by one parent
- Config loaders, logger setup, validation-only functions

## Decorator Placement

```python
# Below any other decorators, closest to def:
@retry(stop=stop_after_attempt(3))
@neatlogs.span(kind="TOOL", tool_name="web_search", description="Search the web")
def web_search(query: str) -> list[str]:
    ...
```

## Verification

- Functions that perform I/O, API calls, or significant standalone computation have `@span(kind="TOOL")`.
- Each TOOL span has `tool_name` and `description` parameters set.
- LLM call functions are NOT marked TOOL. Their wrapped/instrumented provider call owns the LLM span; add CHAIN only for genuine multi-step orchestration.
- Pure utility functions are NOT decorated.

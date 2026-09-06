# Span Kinds Reference

## WORKFLOW
Top-level entry that orchestrates the full pipeline. One per program/request.
```python
@neatlogs.span(kind="WORKFLOW")
def run_pipeline(input): ...
```

## AGENT
Autonomous decision-maker with a role/goal. Makes LLM calls, invokes tools.
```python
@neatlogs.span(kind="AGENT", name="researcher", role="Research Analyst", goal="Find papers")
def researcher(topic): ...
```

## CHAIN
Sequential processing step. Pre-process → LLM call → post-process.
```python
@neatlogs.span(kind="CHAIN")
async def summarize_and_format(text, settings): ...
```

## TOOL
Discrete capability. Does ONE thing with clear input/output.
```python
@neatlogs.span(kind="TOOL", tool_name="web_search", description="Search the web")
def web_search(query): ...
```

## RETRIEVER
Fetches context for LLM consumption. Query in, documents out.
```python
@neatlogs.span(kind="RETRIEVER")
def retrieve_docs(query, top_k=5): ...
```

## EMBEDDING
Text to vector conversion.
```python
@neatlogs.span(kind="EMBEDDING")
def embed_texts(texts): ...
```

## GUARDRAIL
Validates/filters/sanitizes LLM output.
```python
@neatlogs.span(kind="GUARDRAIL")
def check_safety(text): ...
```

## MCP_TOOL
MCP protocol tool handlers.
```python
@neatlogs.span(kind="MCP_TOOL", tool_name="get_weather")
async def get_weather(location): ...
```

# Step 6: Verify One Capture Owner Per LLM Call

## Wrapped or instrumented providers

`neatlogs.wrap(client)` and provider instrumentors already emit the canonical LLM span, including the actual request/response, model, usage, latency, status, and streaming lifecycle. Call the captured client normally.

```python
client = neatlogs.wrap(OpenAI())
response = client.chat.completions.create(model="gpt-4o", messages=messages)
```

Do not add `with neatlogs.trace(..., kind="LLM")`, an LLM decorator, or a second provider instrumentor around that call. Do not rewrite the user's messages merely to instrument them.

## Custom orchestration

Use `@neatlogs.span(kind="WORKFLOW"|"CHAIN"|"AGENT")` only when a function performs meaningful orchestration—several captured calls, tools, retrieval, or custom processing. A single wrapped call does not need a manual parent to render because the capture layer auto-roots it.

## Unsupported or raw LLM calls

Use a manual `neatlogs.trace(..., kind="LLM")` only when no wrapper, callback handler, hook, processor, or instrumentor owns the call, such as raw HTTP or an unsupported SDK. The manual span must record canonical input, output, model, token usage, status, streaming completion, and errors. Do not rewrite unrelated user code solely for instrumentation.

Put the LLM span under an eligible orchestration root; a parentless manual LLM span is not a valid finalized trace. Set canonical attributes directly:

```python
from opentelemetry.trace import Status, StatusCode

with neatlogs.trace("raw_provider_request", kind="WORKFLOW"):
    with neatlogs.trace(
        "unsupported_provider.chat",
        kind="LLM",
        **{"neatlogs.internal": False},
    ) as span:
        span.set_attribute("neatlogs.llm.provider", provider)
        span.set_attribute("neatlogs.llm.model_name", model)
        span.set_attribute("neatlogs.llm.input_messages.0.role", "user")
        span.set_attribute("neatlogs.llm.input_messages.0.content", prompt)
        try:
            response = call_unsupported_provider(prompt)
            span.set_attribute("neatlogs.llm.output_messages.0.role", "assistant")
            span.set_attribute("neatlogs.llm.output_messages.0.content", response.text)
            span.set_attribute("neatlogs.llm.token_count.prompt", response.usage.input_tokens)
            span.set_attribute("neatlogs.llm.token_count.completion", response.usage.output_tokens)
            span.set_attribute("neatlogs.llm.token_count.total", response.usage.total_tokens)
            span.set_attribute("neatlogs.llm.finish_reason", response.finish_reason)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
```

For streaming, also set `neatlogs.llm.is_streaming = True` and keep the context open until the stream is fully consumed, cancelled, or fails; set final accumulated output and usage before leaving it.

## Verification checklist

- [ ] Every supported provider call uses exactly one wrapper or instrumentor.
- [ ] No manual LLM trace/decorator surrounds a wrapped or instrumented call.
- [ ] Manual LLM spans exist only for unsupported/raw calls and record complete LLM semantics.
- [ ] Orchestration decorators represent genuine multi-step application logic.
- [ ] A runtime trace has one LLM span per real model call.

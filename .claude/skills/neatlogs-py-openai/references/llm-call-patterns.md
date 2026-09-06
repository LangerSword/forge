# LLM Call Patterns — How to Recognize Them

Use this reference to identify LLM calls and then assign exactly one capture owner. Supported wrapper/instrumentor calls need no manual LLM trace. Only unsupported/raw calls need `neatlogs.trace(kind="LLM")`.

## OpenAI SDK (`openai`)

```python
# Sync
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...])

# Async
client = AsyncOpenAI()
response = await client.chat.completions.create(model="gpt-4o", messages=[...])

# Streaming
stream = client.chat.completions.create(model="gpt-4o", messages=[...], stream=True)
for chunk in stream: ...

# Async streaming
stream = await client.chat.completions.create(model="gpt-4o", messages=[...], stream=True)
async for chunk in stream: ...

# Responses API
response = client.responses.create(model="gpt-4o", input="...")
```

**Pattern to match:** `*.chat.completions.create(` or `*.responses.create(`

## Anthropic SDK (`anthropic`)

```python
# Sync
client = Anthropic()
message = client.messages.create(model="claude-sonnet-4-20250514", messages=[...], max_tokens=1024)

# Async
client = AsyncAnthropic()
message = await client.messages.create(model="claude-sonnet-4-20250514", messages=[...], max_tokens=1024)

# Streaming
with client.messages.stream(model="claude-sonnet-4-20250514", messages=[...]) as stream:
    for text in stream.text_stream: ...

# Async streaming
async with client.messages.stream(model="claude-sonnet-4-20250514", messages=[...]) as stream:
    async for text in stream.text_stream: ...
```

**Pattern to match:** `*.messages.create(` or `*.messages.stream(`

## Google GenAI (`google-genai`)

```python
from google import genai

client = genai.Client()
response = client.models.generate_content(model="gemini-2.0-flash", contents="...")

# Streaming
for chunk in client.models.generate_content_stream(model="gemini-2.0-flash", contents="..."):
    ...

# Async
response = await client.aio.models.generate_content(model="gemini-2.0-flash", contents="...")
```

**Pattern to match:** `*.models.generate_content(` or `*.models.generate_content_stream(` or `*.aio.models.generate_content(`

## LangChain (`langchain-openai`, `langchain-anthropic`, etc.)

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

llm = ChatOpenAI(model="gpt-4o")
llm = ChatAnthropic(model="claude-sonnet-4-20250514")

# Invoke (sync)
response = llm.invoke(messages)
response = llm.invoke("prompt string")

# Async invoke
response = await llm.ainvoke(messages)

# Streaming
for chunk in llm.stream(messages): ...
async for chunk in llm.astream(messages): ...

# With tool binding
llm_with_tools = llm.bind_tools([...])
response = llm_with_tools.invoke(messages)
```

**Pattern to match:** `llm.invoke(`, `llm.ainvoke(`, `llm.stream(`, `llm.astream(`, `llm_with_tools.invoke(`

## Groq SDK (`groq`)

```python
from groq import Groq, AsyncGroq

client = Groq()
response = client.chat.completions.create(model="llama-3.3-70b", messages=[...])

# Async
client = AsyncGroq()
response = await client.chat.completions.create(model="llama-3.3-70b", messages=[...])
```

**Pattern to match:** same as OpenAI — `*.chat.completions.create(`

## Cohere SDK (`cohere`)

```python
import cohere

client = cohere.Client()
response = client.chat(message="...", model="command-r-plus")

# v2
response = client.v2.chat(model="command-r-plus", messages=[...])
```

**Pattern to match:** `client.chat(` or `client.v2.chat(`

## AWS Bedrock (`boto3`)

```python
import boto3

client = boto3.client("bedrock-runtime")
response = client.converse(modelId="anthropic.claude-3-sonnet", messages=[...])
response = client.invoke_model(modelId="...", body=json.dumps({...}))
```

**Pattern to match:** `*.converse(` or `*.invoke_model(`

## LiteLLM (`litellm`)

```python
import litellm

response = litellm.completion(model="gpt-4o", messages=[...])
response = await litellm.acompletion(model="gpt-4o", messages=[...])
```

**Pattern to match:** `litellm.completion(` or `litellm.acompletion(`

## Together AI (`together`)

```python
from together import Together

client = Together()
response = client.chat.completions.create(model="meta-llama/...", messages=[...])
```

**Pattern to match:** same as OpenAI — `*.chat.completions.create(`

## Mistral AI (`mistralai`)

```python
from mistralai import Mistral

client = Mistral()
response = client.chat.complete(model="mistral-large", messages=[...])
response = await client.chat.complete_async(model="mistral-large", messages=[...])
```

**Pattern to match:** `*.chat.complete(` or `*.chat.complete_async(`

## Ollama (`ollama`)

```python
import ollama

response = ollama.chat(model="llama3", messages=[...])
response = ollama.generate(model="llama3", prompt="...")
```

**Pattern to match:** `ollama.chat(` or `ollama.generate(`

---

## How to Use This Reference

When scanning a file for LLM calls:
1. Identify the capture owner for each call: provider wrapper/instrumentor, framework handler/hook/processor, or none.
2. If a supported capture owner exists, use it exactly once and do not add a manual LLM trace/decorator or rewrite prompts.
3. If no capture owner exists (unsupported SDK/raw HTTP), add one manual LLM span and populate all canonical LLM attributes.
4. Verify the runtime tree contains one LLM span per real model call.

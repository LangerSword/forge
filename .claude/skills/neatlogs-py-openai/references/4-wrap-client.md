# Step 4: Wrap the LLM client(s) with neatlogs.wrap()

## Action

Find where each LLM client is constructed and wrap it with `neatlogs.wrap()`. This is what makes calls on that client traced.

```python
import neatlogs
from openai import OpenAI

client = neatlogs.wrap(OpenAI())          # was: client = OpenAI()
```

`wrap()` returns the SAME instance (patched in place), so the simplest edit is to wrap the constructor expression. Supported clients (auto-routed by type):

| Client | Wrap |
|---|---|
| `OpenAI()` / `AsyncOpenAI()` | `neatlogs.wrap(OpenAI())` |
| `Anthropic()` / `AsyncAnthropic()` | `neatlogs.wrap(Anthropic())` |
| `genai.Client()` (google-genai) | `neatlogs.wrap(genai.Client())` |

## Where the client is built matters

- **Module-level client** (`client = OpenAI()` at top of a file) → wrap it there: `client = neatlogs.wrap(OpenAI())`.
- **Built inside a function/method per call** → wrap at the construction site:
  ```python
  def summarize(text, settings):
      client = neatlogs.wrap(AsyncOpenAI(api_key=settings.api_key))
      ...
  ```
- **Built in a factory / DI provider** → wrap the return value:
  ```python
  def get_client() -> OpenAI:
      return neatlogs.wrap(OpenAI())
  ```
- **A settings/config object stores the client** → wrap when it is assigned.

Wrap EVERY client whose calls you want traced. Wrapping the same client twice is harmless (idempotent), but wrap at least once.

## Path-B providers (Groq / Cohere / Bedrock / Mistral / Together / LiteLLM)

`wrap()` does NOT support these. If the project uses one, do NOT wrap its client — instead it was added to `init(instrumentations=[...])` in Step 2, which patches it globally. Leave those clients untouched here.

## WRONG vs RIGHT

```python
# ❌ WRONG — client constructed but never wrapped (and no instrumentations= for it). No LLM spans.
client = OpenAI()

# ✅ RIGHT
client = neatlogs.wrap(OpenAI())
```

```python
# ❌ WRONG — wrapping AND listing in instrumentations=. Duplicate LLM spans.
neatlogs.init(api_key=..., instrumentations=["openai"])
client = neatlogs.wrap(OpenAI())

# ✅ RIGHT — wrap() only.
neatlogs.init(api_key=...)
client = neatlogs.wrap(OpenAI())
```

## Verify BEFORE moving to step 5

1. Grep for the client constructors (`OpenAI(`, `AsyncOpenAI(`, `Anthropic(`, `genai.Client(`). Each one you intend to trace is wrapped with `neatlogs.wrap(...)`.
2. No client is BOTH wrapped and named in `instrumentations=[]`.
3. `import neatlogs` is present in each file that calls `neatlogs.wrap(...)`.

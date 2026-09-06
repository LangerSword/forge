# Step 3: Set Environment Variables

## Action

1. Use the `set_env_values` tool to write these to `.env`:
   - `NEATLOGS_API_KEY` — use the API key value provided in the wizard session context
2. **Preserve EVERY key the project already declares — not just provider keys.** Writing to `.env` must NOT drop any of the app's config. Before/while writing:
   - Read `.env.example` (and `.env.sample`/`.env.template` if present). Copy **ALL** of its keys into `.env` — provider keys (`OPENAI_API_KEY`), app secrets (`API_SECRET_KEY`), server config (`HOST`, `PORT`, `ENV`), service URLs (`REDIS_URL`, `DATABASE_URL`), feature flags, everything — each with its placeholder/default value. Dropping any of these can break the app (e.g. an auth middleware that reads `API_SECRET_KEY` rejects all requests if it's missing).
   - For each detected LLM provider (from `detect_stack`), ensure its standard key exists in `.env` as a placeholder if missing. See the mapping below.
   - NEVER overwrite a key that already has a real value in `.env`. Only ADD missing keys.
   - The resulting `.env` should be a SUPERSET of `.env.example` plus the `NEATLOGS_*` keys. If `.env.example` has 6 keys, `.env` must have those 6 (+ `NEATLOGS_*`). Count them.
3. Verify `.env` is in `.gitignore`. If not, add it.
4. **Search for `BaseSettings` in the project** (grep all .py files). This check is mandatory.

## Provider → env-var placeholder mapping

| Detected provider | Env var | Placeholder |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | `sk-your-key-here` |
| `anthropic` | `ANTHROPIC_API_KEY` | `sk-ant-your-key-here` |
| `google-genai` | `GOOGLE_API_KEY` | `your-google-api-key` |
| `groq` | `GROQ_API_KEY` | `gsk-your-key-here` |
| `cohere` | `COHERE_API_KEY` | `your-cohere-key` |
| `mistralai` | `MISTRAL_API_KEY` | `your-mistral-key` |

If the project's `.env.example` names a provider key differently, use the name from `.env.example` (it is the source of truth for this project).

## WRONG vs RIGHT — carry over ALL keys

Given a `.env.example` like:
```bash
ANTHROPIC_API_KEY=sk-ant-...
API_SECRET_KEY=your-secret-key-here
HOST=0.0.0.0
PORT=8000
ENV=development
```

```bash
# ❌ WRONG — wizard kept ONLY the provider key and dropped API_SECRET_KEY/HOST/PORT/ENV.
# The auth middleware reads API_SECRET_KEY → every request now 500s. App is broken.
ANTHROPIC_API_KEY=sk-ant-your-key-here
NEATLOGS_API_KEY=nl-...

# ✅ RIGHT — ALL .env.example keys carried over, plus NEATLOGS_*.
ANTHROPIC_API_KEY=sk-ant-your-key-here
API_SECRET_KEY=your-secret-key-here
HOST=0.0.0.0
PORT=8000
ENV=development
NEATLOGS_API_KEY=nl-...
```

## Pydantic-Settings Fix (CRITICAL)

IF the project has a class that inherits from `BaseSettings` and reads from `.env`:

```python
# ❌ WRONG — app will CRASH with "extra fields not permitted" when it sees NEATLOGS_* vars
class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

# ✅ RIGHT — "extra": "ignore" allows unknown env vars like NEATLOGS_API_KEY
class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
```

If `model_config` uses `SettingsConfigDict`, same fix:

```python
# ✅ RIGHT
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
```

## Why this matters

When you add `NEATLOGS_API_KEY` to `.env`, pydantic-settings will try to load ALL env vars from that file. If the Settings class doesn't have fields for them AND doesn't allow extras, the app crashes on import. This is a guaranteed runtime error.

## Verify BEFORE moving to step 4

1. Run `check_env_keys` tool — confirm `NEATLOGS_API_KEY` exists in `.env`.
2. Count the keys in `.env.example` and confirm `.env` contains EVERY one of them (provider keys, app secrets, server config, service URLs — all of it), plus the `NEATLOGS_*` keys. `.env` must be a superset of `.env.example`. If any `.env.example` key is missing from `.env`, add it now — a dropped key can break the app at runtime.
3. `.gitignore` contains `.env`.
4. Grep for `BaseSettings` in all .py files. IF found: confirm `"extra": "ignore"` is present in the model_config of that class. If you skipped this, the app WILL crash.

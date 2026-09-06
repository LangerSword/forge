# Step 2: Add neatlogs.init()

## Action

1. Find the application entry point (`main.py`, `app.py`, `run.py`, or `if __name__ == "__main__":`).
   **For web servers (FastAPI/Flask/Starlette/Litestar) read the CRITICAL section below FIRST — the entry point is NOT the file you think.**
2. Read the entry point file.
3. Add `import os` and `import neatlogs` near the top.
4. Add the init call. For the wrap() path (OpenAI/Anthropic/Google GenAI), `init()` takes NO `instrumentations=` argument — instrumentation happens in Step 4 by wrapping the client. Only add `instrumentations=[...]` for a Path-B provider (Groq/Cohere/Bedrock/Mistral/Together/LiteLLM) the app uses.

## CRITICAL: Web servers (FastAPI / Flask / ASGI / WSGI)

For a web app, the server (uvicorn/gunicorn/hypercorn) imports the **app module** (e.g. `src.app:app`) in its own worker process. A `main.py` that calls `uvicorn.run("src.app:app", ...)` does NOT run in that worker — so putting `init()` in `main.py` means **the process that actually serves requests never initializes Neatlogs, and no traces are produced.**

`init()` MUST go in the **module that defines the app object** (the one the server imports), and it MUST run BEFORE that module imports the LLM SDK / constructs the client.

```python
# ❌ WRONG — init() in main.py / the uvicorn launcher.
# uvicorn imports src.app:app in a separate worker that never runs this. No traces.
# main.py
neatlogs.init(...)
uvicorn.run("src.app:app", reload=True)

# app.py  ← what the worker actually loads
from openai import OpenAI
client = OpenAI()        # constructed with NO init/wrap having run → never traced
app = FastAPI(lifespan=lifespan)
```

```python
# ✅ RIGHT — init() at the top of app.py (the imported app module), BEFORE the LLM import + wrap.
# app.py
import os
import neatlogs
from dotenv import load_dotenv

load_dotenv()
neatlogs.init(
    api_key=os.getenv("NEATLOGS_API_KEY"),
    workflow_name="my-api",
)

from openai import OpenAI
client = neatlogs.wrap(OpenAI())        # wrapped in the served process
from fastapi import FastAPI
app = FastAPI(lifespan=lifespan)
```

Rules for web apps:
- Put `init()` in the app module (where `app = FastAPI(...)` / `Flask(__name__)` lives), at the very top, after `load_dotenv()`, before the LLM SDK import and client construction.
- Do NOT put `init()` only in a `main.py` whose job is to call `uvicorn.run(...)`. If such a `main.py` also matters (e.g. someone runs it directly), it's harmless to leave its own init too, but the app-module init is the one that counts.
- `neatlogs.flush()`/`shutdown()` go in the lifespan shutdown / `atexit` (Step 8) — but they only work if `init()` ran in the SAME process, which the above guarantees.

## Pattern (non-web: CLI / script / worker)

```python
import os
import neatlogs
from dotenv import load_dotenv  # if project uses dotenv

load_dotenv()  # MUST be before init()

neatlogs.init(
    api_key=os.getenv("NEATLOGS_API_KEY"),
    workflow_name="{project_name}",
)

# ALL LLM library imports MUST come AFTER this point; wrap the client in Step 4.
from openai import OpenAI  # etc.
```

## WRONG vs RIGHT

```python
# ❌ WRONG — missing api_key. SDK may not find it from env depending on load order.
neatlogs.init(
    workflow_name="myapp",
)

# ✅ RIGHT — explicit api_key from env var guarantees it works.
neatlogs.init(
    api_key=os.getenv("NEATLOGS_API_KEY"),
    workflow_name="myapp",
)
```

```python
# ❌ WRONG — listing the provider in instrumentations= AND wrapping the client.
# Double-fires → duplicate LLM spans.
neatlogs.init(api_key=..., workflow_name="myapp", instrumentations=["openai"])
client = neatlogs.wrap(OpenAI())   # pick ONE: wrap() OR instrumentations, not both

# ✅ RIGHT — wrap() only, no instrumentations= for that provider.
neatlogs.init(api_key=..., workflow_name="myapp")
client = neatlogs.wrap(OpenAI())
```

```python
# ❌ WRONG — no import os
import neatlogs
neatlogs.init(api_key=os.getenv("NEATLOGS_API_KEY"), ...)  # NameError!

# ✅ RIGHT — import os before using os.getenv
import os
import neatlogs
neatlogs.init(api_key=os.getenv("NEATLOGS_API_KEY"), ...)
```

## Why api_key is required

The SDK CAN read NEATLOGS_API_KEY from env internally, but only if `load_dotenv()` ran first AND the env var is available in the process. Passing it explicitly guarantees it works in all cases: Docker, CI, systemd, cron, and projects that don't use dotenv.


## Verify BEFORE moving to step 3

1. Grep for `api_key=os.getenv("NEATLOGS_API_KEY")`. If this string does not appear inside `neatlogs.init(...)`, you did this step wrong. Fix it now.
2. Confirm `init()` has NO `instrumentations=` for an OpenAI/Anthropic/Google-GenAI client you intend to `wrap()`. Only Path-B providers belong in `instrumentations=[]`.
3. **Web apps:** confirm `init()` is in the module that defines the app object (the one the server imports), BEFORE the LLM SDK import + `wrap()` — NOT only in a `uvicorn.run(...)` launcher. Grep the app module for `neatlogs.init`; if it's missing there, the served process won't trace.

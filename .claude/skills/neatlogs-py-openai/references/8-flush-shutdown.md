# Step 8: Add flush() and shutdown()

## Action — Scripts (CLI apps, one-shot jobs)

Add `neatlogs.flush()` then `neatlogs.shutdown()` at the program's exit point.

### Pattern: try/finally in main

```python
if __name__ == "__main__":
    try:
        main()
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
```

### Pattern: Click CLI

```python
if __name__ == "__main__":
    try:
        cli()
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
```

## Action — Servers (FastAPI, Flask, Django)

Do NOT flush per-request. Add flush/shutdown to the server's lifespan/shutdown hook:

### FastAPI

```python
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await asyncio.to_thread(neatlogs.flush)
    await asyncio.to_thread(neatlogs.shutdown)

app = FastAPI(lifespan=lifespan)
```

### Flask

```python
import atexit
atexit.register(neatlogs.flush)
atexit.register(neatlogs.shutdown)
```

## Important

- `flush()` sends any buffered spans. `shutdown()` tears down the telemetry provider.
- Always call `flush()` BEFORE `shutdown()`.
- For scripts: ONE flush/shutdown pair in a try/finally at the outermost level. NOT inside each command/function.
- For servers: flush/shutdown in the shutdown lifecycle hook only.

## Verification

- Script: `neatlogs.flush()` and `neatlogs.shutdown()` in a `try/finally` wrapping the main entry point.
- Server: flush/shutdown in lifespan or shutdown hook, NOT per-request.
- No duplicate flush/shutdown calls scattered across multiple functions.

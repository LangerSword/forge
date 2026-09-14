# Forge — Native Execution Plane (daemon + fleet runner)

> **Date:** 2026-09-15
> **Status:** Planning document — no build.
> **Purpose:** Replace the AO dependency with a Forge-owned execution plane: a
> single-operator loopback **daemon** that owns worker session lifecycle, and a
> **fleet runner** that drives it. AO stays installable as an alternative
> backend, not a requirement.

---

## 1. Why

- Forge's goal needs live specialist workers whose experience is distilled into
  portable skills. Today the only spawn path is AO, whose daemon is not running
  and whose worker produced a no-op in the last live attempt — so the
  "autonomous completion" proof point has never landed.
- The runner seam already exists: `FleetController` consumes
  `runner_factory(request) → TaskRunner.run(AORunRequest) → AORunResult`. A
  Forge-owned runner is one more implementation — no controller, scheduler,
  watchdog, or verifier-authority changes.
- AO is retained as a *backend option* (`harness: "opencode"` via the AO
  daemon). Forge stops depending on it to prove anything.

## 2. The key design decision: AO-API-compatible surface

`.forge/ao-surface.json` already records the surface Forge speaks
(all routes `known_exercised` or `known_unexercised`):

```text
GET  /healthz   GET  /readyz     GET  /agents      GET  /projects
GET  /sessions  GET  /session    POST /spawn       POST /send
POST /kill
```

**The Forge daemon implements exactly these routes on loopback.** Consequence:
`forge.ao.AOClient` and `forge.ao_runner.AORunner` run against it unchanged —
only `base_url` (from `.forge/ao-surface.json`) and the harness label change.
The watchdog keeps consuming a `SessionSnapshot`, never a daemon type.

Non-goals (explicitly): no multi-tenant auth, no remote access, no second
state model. The daemon is single-operator, loopback-only
(`127.0.0.1`), and its registry is SQLite — the README's "not a second Kanban"
rule applies to the daemon too.

## 3. Architecture

```text
forge.cli fleet / experiment
    │
    ├─ FleetController (unchanged)
    │
    └─ runner_factory → AORunner (unchanged code, new base_url)
          │
          └─ forge daemon (127.0.0.1:7777, default)
                ├─ session registry (SQLite: sessions, events)
                ├─ process supervisor (spawn / heartbeat / kill)
                │     └─ worker = `opencode run --format json "<prompt>"`
                │        cwd = git worktree, log = session log file
                ├─ git worktree create/prune (branch forge/<run>/<task>)
                └─ route handlers = the ao-surface routes above
```

Worker command is configurable (`FORGE_WORKER_CMD`), so the same daemon can
spawn different agent CLIs → the cross-harness transfer proof point becomes
runnable without AO.

## 4. Components

### 4.1 `src/forge/daemon.py` (create)

- `DaemonState`: SQLite at `.forge/daemon/daemon.db` — `sessions(session_id,
  run_id, task_id, harness, status, pid, worktree, log_path, started_at,
  heartbeat_at, exit_code)` and `daemon_events(ts, kind, session_id, payload)`.
- `spawn(req) -> {session_id}`:
  1. `git worktree add .worktrees/<run_id>-<task_id> -b forge/<run_id>/<task_id>`
  2. build worker command from `FORGE_WORKER_CMD` (default opencode), prompt
     from the scoped `ContextPackage`
  3. `subprocess.Popen(cmd, cwd=worktree, stdout=log, stderr=log)`, store pid
  4. status `running`; background thread updates `heartbeat_at` from log mtime
     + liveness every N s (bounded, daemon-side)
- `session(session_id) -> SessionSnapshot-shaped dict`: status mapped to the
  watchdog vocabulary (`working/passed/blocked_visible/no_op/terminated`),
  `artifact_exists` from the request's `artifact_path`, exit code, heartbeat.
- `send(session_id, message)`: append nudge to the worker's stdin (or re-invoke
  with `-s <session>` for CLIs without stdin); bounded to one nudge per poll
  window (reuse AORunner's nudge policy).
- `kill(session_id)`: SIGTERM → grace → SIGKILL; status `terminated`; prune
  worktree only on explicit `forget` (evidence survives for review).
- `health()`, `ready()`: process + registry checks; `agents()`,
  `projects()`: static single-operator responses (route compatibility only).

### 4.2 `src/forge/daemon_cli.py` (create)

`forge daemon --port 7777` → serve until SIGINT; `--foreground` for tests.
Readiness printed as JSON `{"ok": true, "base_url": ...}` once the socket
accepts (matches the repo's JSON-CLI convention).

### 4.3 `src/forge/ao_cli.py` (patch, small)

`AOCLI.resolve_binary()` already prefers `binary`/env — add
`FORGE_DAEMON_URL` env + `.forge/ao-surface.json` `base_url` as the resolved
transport target. No route changes.

### 4.4 `src/forge/cli.py` (patch)

- `fleet` dispatch: runner_factory picks backend by `goal.harness` —
  `opencode` → AO path (unchanged), `forge-native` → same `AORunner` against
  the Forge daemon.
- new `forge daemon` subcommand (4.2).

### 4.5 `src/forge/testing/fake_worker.py` (create)

Deterministic no-LLM worker for tests: sleeps `FORGE_FAKE_SLEEP` (default 2s),
writes `artifact_path` JSON `{"ok": true}`, exits 0. `--fail` variant exits 1
without artifact. `--hang` variant sleeps forever (tests kill/nudge/timeout).

## 5. Build order (each step lands green before the next)

1. **Daemon core + health routes.** `daemon.py` state + `healthz/readyz`;
   `test_daemon.py`: boot on an ephemeral port, assert JSON readiness, restart
   re-opens the registry (persistence).
2. **Spawn/supervise with the fake worker.** `spawn` → `session` shows
   `running` → worker exits → `passed` with `artifact_exists=true`;
   `--fail` → `failed`; `--hang` + kill → `terminated`. No LLM anywhere.
3. **Worktree isolation.** spawn creates branch `forge/<run>/<task>`; artifact
   written inside the worktree is invisible to the main checkout; prune on
   `forget`.
4. **Wire AORunner against the daemon.** Point `AOClient` at the daemon
   (`FORGE_DAEMON_URL`); `test_ao_runner.py` gains a daemon-backend variant
   running the same truth table (worker status × artifact × verifier) — the
   verifier-authority rule must hold identically on both backends.
5. **Fleet end-to-end.** `forge fleet <goal> --dry-run` unchanged; live
   `harness: "forge-native"` run with the fake worker → FleetReport `passed`;
   ledger carries the same event kinds as the AO path.
6. **Live smoke (one bounded attempt).** Real `opencode run` in a worktree on a
   scoped no-op-ish task (e.g. "write docs/SMOKE.md with today's date");
   record payload + completion signal in `.forge/ao-surface.json` under
   `forge_daemon`. Accept only an independently verified artifact. If the
   worker no-ops again: record as blocked, do not retry-loop.

## 6. Paste-ready test skeleton (step 2)

```python
def test_spawn_fake_worker_passes(daemon):
    r = daemon.spawn({"run_id": "d1", "task_id": "t1", "harness": "forge-native",
                      "prompt": "ok", "cmd": [FAKE_WORKER, "--ok"],
                      "artifact_path": str(ART)})
    sid = r["session_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        snap = daemon.session(sid)
        if snap["status"] != "working":
            break
        time.sleep(0.2)
    assert snap["status"] == "passed"
    assert snap["artifact_exists"] is True
    assert Path(ART).exists()
```

## 7. Failure modes to design for

| Mode | Guard |
|---|---|
| Port already bound | ephemeral-port fallback in tests; explicit error in CLI |
| Worker hang | heartbeat stale + `max_runtime_s` → kill → `terminated` (never blocks the fleet) |
| Daemon crash mid-run | registry on disk; restart marks pid-dead sessions `terminated`; resume is runner-level |
| Zombie worktrees | `forget` prunes; `git worktree prune` on daemon start |
| Concurrent spawn flood | `max_parallel` from the graph budget (controller already owns it) |
| Log growth | log per session, capped tail read for heartbeat |

## 8. Evidence boundary (state honestly in README after build)

- The daemon + fake-worker path is deterministic and fully testable — that
  proves the *execution plane*, not autonomy.
- Autonomous completion is claimed only after step 6 produces a fresh,
  independently verified artifact from a real agent CLI.
- Cross-harness transfer is claimed only with the same task/context contract
  through two different harnesses (forge-native vs AO/opencode), reported
  separately.

## 9. What stays true regardless

`FleetController`, scheduler, watchdog classification, verifier authority, the
promotion gate, and `forge review` are daemon-agnostic and unchanged. If the
daemon never ships, Forge's local proof points (0.2.3) still stand.

# Forge quickstart

Three steps, in order, from a terminal in the Forge checkout (`~/forge`).

## 1. Install the CLI as an editable uv tool

```bash
cd ~/forge
uv tool install --editable .
```

This registers the `forge` console script at `~/.local/bin/forge` and points
it at this checkout, so source edits take effect without a reinstall. Re-run
the same command after dependency changes in `pyproject.toml`. Check with
`forge --version`.

## 2. Bring up the AO daemon

```bash
forge ao install-cli   # once: extracts the ao binary from the Agent
                      # Orchestrator AppImage (searched in ~/Applications,
                      # ~/.local/bin, ~/Downloads) to ~/.local/bin/ao
forge ao start         # headless `ao daemon` on :3001, waits for /readyz
```

`forge ao start` is idempotent — a ready daemon is reported as
`already_running`. Companions: `forge ao status` (works while the daemon is
down) and `forge ao stop`. Re-running `install-cli` is safe: it reports
`up_to_date` unless the AppImage changed or you pass `--force`. Every live
command preflights the daemon and fails with the fix if it is not ready.

## 3. Open the operator cockpit

```bash
cd tui && go build -o ~/.local/bin/forge-tui .   # once
forge                                          # then every time
```

Bare `forge`, with no arguments, execs into `forge-tui` — the Go cockpit
reading the same JSON surface as the CLI, with pages for status, runs, AO,
and review. It needs a TTY; piped or scripted, it returns `not_a_tty` and you
should pass a subcommand such as `forge status`. `forge tui` is equivalent,
and `forge-tui --dump` prints a non-interactive snapshot.

---

*Drafted by an Agent Orchestrator worker (session `forge-19`) during Forge's
first live `forge run-graph` (`graph-7fd57cd4`, 2026-09-28), independently
re-produced by a second worker (`forge-20`) in its own worktree, and promoted
after review.*
# forge-tui

The Forge cockpit — a bubbletea TUI over the same JSON surface the `forge`
CLI exposes. No second state model: every panel is a `forge` command.

## Build & run

```bash
cd tui
go build -o ~/.local/bin/forge-tui .
forge                    # bare `forge` (or `forge tui`) execs into the cockpit
forge-tui                # the same binary, invoked directly
forge-tui --dump         # non-interactive snapshot (CI / verification)
forge-tui --root=/path   # override repo root (default: $FORGE_ROOT or ~/forge)
```

`forge` must be on `PATH` (install it with
`uv tool install --editable /path/to/forge`).

## Pages

| key | page    | source commands |
|-----|---------|-----------------|
| 1   | status  | `forge status` |
| 2   | runs    | `forge runs`, `forge run <id>` |
| 3   | ao      | `forge ao status`, `forge harnesses` |
| 4   | review  | `forge review` |
| 5   | help    | — |

Keys: `j`/`k` move or scroll · `enter` open run · `esc` back · `r` refresh ·
`q` quit.

## Frameworks

bubbletea (runtime) · lipgloss (styling) · bubbles (spinner, viewport).
Next increments: bubbles list/table, glamour-rendered plan viewer, and an
in-TUI goal compiler once `forge plan` learns streaming.
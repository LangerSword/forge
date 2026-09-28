# Quickstart doc for Forge

Repo: /home/lakshaya/forge
Harness: opencode
Artifact: docs/QUICKSTART.md
Max minutes: 6

## Goal

Write `docs/QUICKSTART.md`: a short, accurate quickstart for running Forge on this machine. Cover, in order: (1) the CLI is installed as an editable uv tool (`uv tool install --editable .` from the repo); (2) the AO daemon lifecycle (`forge ao install-cli` once, then `forge ao start`); (3) launching the operator cockpit by running bare `forge`. Under 300 words. No badges, no marketing prose — just the three steps.

## Acceptance

- docs/QUICKSTART.md exists in the worktree.
- It mentions `uv tool install`.
- It mentions `forge ao start`.
- It mentions that bare `forge` opens the cockpit.
- It is shorter than 300 words.

## Verification

- `test -s docs/QUICKSTART.md`
- `grep -q "uv tool install" docs/QUICKSTART.md`
- `grep -q "forge ao start" docs/QUICKSTART.md`
- `grep -qi "cockpit" docs/QUICKSTART.md`
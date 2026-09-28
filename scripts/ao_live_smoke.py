"""Bounded live AO smoke: one worker through Forge's real runner.

The repeatable form of the 2026-09-15 proof (``ao-live-smoke-20260915-v2``):
same runner, same verifier authority, same recording discipline. Spawn one
bounded opencode worker that writes ``docs/SMOKE.md``; a fresh artifact plus
an independent content check are required before the run passes.

Usage:
  uv run python scripts/ao_live_smoke.py [run_id]

Preconditions (all enforced):
  - ready AO daemon (`uv run forge ao start`)
  - stable CLI installed (`uv run forge ao install-cli`)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from forge.ao import AOClient  # noqa: E402
from forge.ao_cli import AOCLI  # noqa: E402
from forge.ao_daemon import require_ao_ready  # noqa: E402
from forge.ao_runner import AORunRequest, AORunner  # noqa: E402
from forge.ledger import Ledger  # noqa: E402


def main() -> int:
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_id = sys.argv[1] if len(sys.argv) > 1 else f"ao-live-smoke-{date_str.replace('-', '')}"
    prompt = (
        "Create the file docs/SMOKE.md in the current repository with exactly one line: "
        f"SMOKE {date_str}. Then stop."
    )

    # Wiring contract: the daemon must actually be ready before we spawn.
    require_ao_ready()

    def verifier(root: Path, artifact: Path) -> bool:
        try:
            text = artifact.read_text()
        except OSError:
            return False
        return "SMOKE" in text and date_str in text and 0 < len(text) <= 4000

    runner = AORunner(ao_cli=AOCLI(), ao_client=AOClient(), ledger=Ledger(ROOT))
    request = AORunRequest(
        run_id=run_id,
        goal="live AO smoke: one bounded worker writes docs/SMOKE.md",
        project="forge",
        worker_name="smoke-verify",
        prompt=prompt,
        harness="opencode",
        mode="chat",
        artifact_path=Path("docs/SMOKE.md"),
        independent_verifier=verifier,
        max_polls=40,
        poll_interval_s=2.0,
        max_runtime_s=300.0,
        max_idle_s=90.0,
    )
    result = runner.run(request)
    payload_text = json.dumps(result.to_dict(), indent=2, default=str).replace(prompt, "<redacted>")

    out_path = ROOT / "evals" / "results" / f"live-smoke-{date_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload_text + "\n")
    print(payload_text)
    print(
        f"\nresult: {result.status} | artifact={result.artifact_exists} | "
        f"verified={result.verification_passed} | session={result.session_id}"
    )
    print(f"saved: {out_path}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
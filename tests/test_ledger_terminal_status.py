from pathlib import Path

from forge.ledger import Ledger
from forge.verifier import verify_local_smoke


def test_verifier_persists_terminal_status():
    root = Path.cwd()
    run_id = "terminal-status-test"
    result = verify_local_smoke(root, run_id=run_id)
    stored = Ledger(root).get_run(run_id)
    assert result.status == "passed"
    assert stored is not None
    assert stored["status"] == "passed"
    assert stored["events"][-1]["kind"] == "verdict"

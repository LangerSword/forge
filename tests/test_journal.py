from pathlib import Path

import pytest

from forge.journal import ProjectJournal


def test_journal_requires_evidence_and_redacts_secrets(tmp_path: Path):
    journal = ProjectJournal(tmp_path)
    with pytest.raises(ValueError):
        journal.append(entry_type="setback", status="observed", title="x", summary="y", evidence=[])
    entry = journal.append(
        entry_type="discovery", status="observed", title="AO healthy",
        summary="AO returned ready", evidence=["/readyz"],
        impact={"runtime": "ok", "api_key": "must not persist"},
    )
    assert entry["impact"]["api_key"] == "<redacted>"
    assert journal.read()[0]["title"] == "AO healthy"

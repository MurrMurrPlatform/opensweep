"""Filesystem side of the terminal handoff — tmp_path stands in for a sandbox."""

from pathlib import Path

from domains.investigations.services.handoff import HANDOFF_FILENAME, write_handoff_file


def _fake_sandbox(tmp_path: Path) -> Path:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    return tmp_path


def test_write_handoff_file_creates_brief_and_git_exclude(tmp_path):
    sandbox = _fake_sandbox(tmp_path)
    path = write_handoff_file(str(sandbox), "# brief")
    assert Path(path).read_text() == "# brief"
    assert Path(path).name == HANDOFF_FILENAME
    exclude = (sandbox / ".git" / "info" / "exclude").read_text()
    assert HANDOFF_FILENAME in exclude


def test_write_handoff_file_is_idempotent_on_exclude(tmp_path):
    sandbox = _fake_sandbox(tmp_path)
    write_handoff_file(str(sandbox), "one")
    write_handoff_file(str(sandbox), "two")
    exclude = (sandbox / ".git" / "info" / "exclude").read_text()
    assert exclude.count(HANDOFF_FILENAME) == 1
    assert (sandbox / HANDOFF_FILENAME).read_text() == "two"


def test_write_handoff_file_survives_missing_git_dir(tmp_path):
    # A half-destroyed sandbox must not break the handoff response.
    path = write_handoff_file(str(tmp_path), "# brief")
    assert Path(path).read_text() == "# brief"

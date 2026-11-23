"""Guard against carrying completed expedited-incident markers into normal work."""

from __future__ import annotations

from os import walk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_MARKER = "EXPEDITED_INCIDENT_RESPONSE flag: " + "overseer-5v2ajq"
GENERATED_DIRECTORIES = {".codex", ".git", ".tmux", ".venv", "__pycache__"}


def test_overseer_5v2ajq_expedited_incident_marker_is_absent_from_source_tree():
    marked_files = []
    for directory, directories, filenames in walk(ROOT):
        directories[:] = [name for name in directories if name not in GENERATED_DIRECTORIES]
        marked_files.extend(
            path.relative_to(ROOT)
            for filename in filenames
            if INCIDENT_MARKER
            in (path := Path(directory, filename)).read_text(encoding="utf-8", errors="ignore")
        )

    assert marked_files == []

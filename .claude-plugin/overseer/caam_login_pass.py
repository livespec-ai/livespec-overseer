"""The rotation pass's login step: first-seen records, then the login report.

Observation only. It reads and writes the login record store and prints lines;
its result is never an input to the account decision.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from caam_anthropic_finish import LineWriter
from caam_login_records import (
    load_records,
    locked,
    note_first_seen,
    prune_records,
    records_path,
    save_records,
)
from caam_login_report import lifetime_settings, login_report_lines

__all__: list[str] = ["observe_pass_logins"]

_FAIL: str = "FAIL login records unavailable"


def observe_pass_logins(
    *,
    home: Path,
    names: tuple[str, ...],
    now: float,
    dry_run: bool,
    stdout: LineWriter,
    environ: Mapping[str, str] | None = None,
) -> None:
    path = records_path(home=home)
    try:
        with locked(path=path):
            loaded = load_records(path=path)
            if loaded.problem is not None:
                stdout(f"{_FAIL}: {loaded.problem}")
                return
            records = loaded.records
            fresh = [name for name in names if note_first_seen(records=records, name=name, now=now)]
            prune_records(records=records, now=now)
            if not dry_run:
                save_records(path=path, records=records)
    except OSError as exc:
        stdout(f"{_FAIL}: {exc}")
        return
    settings = lifetime_settings(environ=os.environ if environ is None else environ)
    for line in login_report_lines(records=records, names=names, now=now, settings=settings):
        stdout(line)
    if fresh and not dry_run:
        stdout(f"LOGIN first-seen records created for {', '.join(fresh)}")

"""Shared fixtures for the integration tier."""

from __future__ import annotations

import herdr_replacement_process
import pytest


def _fixture_predecessor_absent(*, pid: int) -> None:
    """A fixture pid names no host process, whatever the host's own process table holds."""
    _ = pid


@pytest.fixture
def fixture_predecessors_are_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the recorded-predecessor exit check from fixture state, never the host /proc.

    The herdr replacement tests record fake predecessor pids (100, 200, 201, 300, 301). On a
    host where those pids are live kernel threads the real reader reports a different start
    time and a completed replacement reads as a reused predecessor (overseer-aw6gv5).
    """
    monkeypatch.setattr(herdr_replacement_process, "proc_starttime", _fixture_predecessor_absent)

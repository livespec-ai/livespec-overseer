"""Fixture pids of the herdr replacement tests never reach the host's own process table."""

from __future__ import annotations

import herdr_replacement_process
import pytest

_FIXTURE_PIDS = (100, 200, 201, 300, 301)


def test_fixture_predecessors_are_gone_whatever_the_host_runs(
    *, request: pytest.FixtureRequest
) -> None:
    """Pids 100/200/201/300/301 are kernel threads on some hosts; the exit check must not see them.

    On such a host the real reader reports a different start time and a completed replacement
    reads as a reused predecessor (overseer-aw6gv5).
    """
    request.getfixturevalue("fixture_predecessors_are_gone")

    assert all(herdr_replacement_process.proc_starttime(pid=pid) is None for pid in _FIXTURE_PIDS)

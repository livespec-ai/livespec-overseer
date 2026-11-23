"""Regression coverage for status-snapshot rows discovered from Herdr agents.

``overseer-3xc62h``: the daemon's plan mapping can omit live Herdr agents, notably
idle and completed agents and sessions launched without a resumed session.  The
snapshot is an operator inventory, so every agent the backend reports needs a row;
an unreadable context is a fact to publish, not a reason to drop that agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from overseer.test_supervisor_builders import idle_capture, make_supervisor
from overseer.test_supervisor_fakes import FakeTmux


def test_tick_snapshots_every_listed_herdr_agent_even_when_its_context_is_unreadable(*, tmp_path):
    """The listed population, rather than a resumed-session join, owns snapshot coverage."""
    repo = tmp_path / "watched-repo"
    repo.mkdir()
    status_path = tmp_path / "status.json"
    fake = FakeTmux()
    readable = {
        "working-agent": 81,
        "idle-agent": 62,
        "done-agent": 43,
        # This agent was launched fresh, so no earlier resumed-session identity exists.
        "fresh-agent": 24,
    }
    for name, ctx in readable.items():
        fake.serve(session=name, repo=repo, capture=idle_capture(ctx=ctx))
    fake.serve(session="unreadable-agent", repo=repo, capture="agent output without a statusline")

    def herdr_agent_list():
        return [
            {"name": "working-agent", "status": "working", "pane": "working-agent"},
            {"name": "idle-agent", "status": "idle", "pane": "idle-agent"},
            {"name": "done-agent", "status": "done", "pane": "done-agent"},
            {
                "name": "fresh-agent",
                "status": "working",
                "pane": "fresh-agent",
                "resumed_session_id": None,
            },
            {
                "name": "unreadable-agent",
                "status": "idle",
                "pane": "unreadable-agent",
            },
        ]

    fake.herdr_agent_list = herdr_agent_list
    sup = make_supervisor(
        tmp_path=tmp_path,
        fake=fake,
        status_path=status_path,
        watch_repos=[str(repo)],
    )

    _ = sup.tick(act=True)

    document = json.loads(Path(status_path).read_text(encoding="utf-8"))
    rows = {row["topic"]: row for row in document["rows"]}
    assert set(readable) | {"unreadable-agent"} <= set(rows)
    for name, ctx in readable.items():
        assert rows[name]["ctx"] == ctx
        assert rows[name]["ctx_source"] == "live"
    assert rows["unreadable-agent"]["ctx"] is None
    assert rows["unreadable-agent"]["ctx_source"] == "unreadable"

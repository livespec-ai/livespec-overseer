"""Coverage for Herdr-agent inventory rows that already have a mapped track."""

from __future__ import annotations

import json

from overseer import registry
from overseer.test_supervisor_builders import idle_capture, make_plan, make_supervisor, mapped_track
from overseer.test_supervisor_fakes import FakeTmux


def test_tick_does_not_duplicate_a_mapped_herdr_agent(*, tmp_path):
    repo, topic = make_plan(tmp_path=tmp_path, topic="mapped-agent")
    status_path = tmp_path / "status.json"
    fake = FakeTmux()
    fake.serve(session=topic, repo=repo, capture=idle_capture(ctx=77))
    fake.herdr_agent_list = lambda: [{"name": topic, "status": "idle", "pane": topic}]
    sup = make_supervisor(
        tmp_path=tmp_path,
        fake=fake,
        status_path=status_path,
        watch_repos=[str(repo)],
    )
    registry.append_mapping(
        track=mapped_track(repo=repo, topic=topic, session=topic),
        store_path=sup.store_path,
        added_at="2026-11-23T00:00:00Z",
    )

    _ = sup.tick(act=True)

    rows = json.loads(status_path.read_text(encoding="utf-8"))["rows"]
    assert [row["topic"] for row in rows].count(topic) == 1

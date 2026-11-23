"""Boundary coverage for durable rotation push-alert state."""

from __future__ import annotations

import json
from pathlib import Path

from caam_push_alerts import _load, observe_alerts


def _channel(*, home: Path) -> None:
    path = home / ".claude/settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"env": {"CLAUDE_NTFY_TOPIC": "test"}}), encoding="utf-8")


def test_a_failed_recovery_stays_remembered_for_the_next_pass(*, tmp_path: Path) -> None:
    _channel(home=tmp_path)
    sent: list[str] = []

    def post(*, url: str, message: str) -> str:
        del url
        sent.append(message)
        return "sent 200" if len(sent) == 1 else "failed OSError"

    observe_alerts(
        home=tmp_path,
        now=10.0,
        conditions=(("dark/a", "dark login", "account a", 1.0),),
        post=post,
        stdout=lambda _line: None,
    )
    observe_alerts(home=tmp_path, now=20.0, conditions=(), post=post, stdout=lambda _line: None)

    assert set(_load(home=tmp_path)) == {"dark/a"}


def test_malformed_alert_memory_is_ignored_without_a_crash(*, tmp_path: Path) -> None:
    path = tmp_path / ".local/state/caam-usage-rotate/push-alerts.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "conditions": {
                    "not-an-object": 1,
                    "bad-fields": {"description": 1, "subject": "x", "started_at": "now"},
                }
            }
        ),
        encoding="utf-8",
    )

    assert _load(home=tmp_path) == {}
    path.write_text("{}", encoding="utf-8")
    assert _load(home=tmp_path) == {}

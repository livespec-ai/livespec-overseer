"""A forwarded refusal is authenticated by the verified delivery-push ssh session.

The role holder runs the host-side refusal program over the same host-key-pinned
ssh runner the delivery push uses, and stamps the answer with the listed host
whose session carried it.  Nothing a reply or loop state says about its own origin
is believed.  Fixtures stand in for the hosts; no host and no provider is contacted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from caam_decide_context import DecisionContext
from caam_decision import ProfileUsage, UsageRecord
from caam_delivery_push_state import HOSTS_FILE, STATE_DIR
from caam_forwarded_refusal_intake import (
    FORWARD_SCRIPT,
    forward_if_due,
    forward_refusals,
    verified_forwarded,
)
from caam_forwarded_refusals import forwarded_refusals
from caam_pass_refusals import observe_pass_refusals
from caam_profiles import ActiveIdentity
from caam_refusal_store import remembered_refusals
from caam_refusals import TrackedSession

__all__: list[str] = []

pytestmark = pytest.mark.integration

NOW = 1_800_000_000.0
STAMP = "2027-01-15T08:00:00Z"
MESSAGE = f"Claude AI usage limit reached|{int(NOW + 3_600.0)}"
STORE = f"{STATE_DIR}/delivery-forwarded-refusals.json"


def _list_host(*, home: Path, label: str = "build-agent-a", target: str = "ops@build-a") -> None:
    path = home / HOSTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"{label} {target} linux\n", encoding="utf-8")


def _reply(**changes: object) -> str:
    body: dict[str, object] = {
        "account": "uuid-anthropic-1",
        "recorded_at": NOW - 60.0,
        "provider_message": MESSAGE,
    }
    body.update(changes)
    return "forwarded-refusal " + json.dumps(body)


def _runner(*, line: str, calls: list[dict[str, object]] | None = None):
    def run(**kwargs: object) -> tuple[int, str]:
        if calls is not None:
            calls.append(kwargs)
        return 0, line

    return run


def _store(*, home: Path) -> dict[str, dict[str, object]]:
    return json.loads((home / STORE).read_text(encoding="utf-8"))


def _host_with_transcript(
    *, home: Path, lines: list[str], account: str | None = "host-uuid"
) -> None:
    if account is not None:
        _ = (home / ".claude.json").write_text(
            json.dumps({"oauthAccount": {"accountUuid": account}}), encoding="utf-8"
        )
    project = home / ".claude" / "projects" / "-work"
    project.mkdir(parents=True)
    _ = (project / "session.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_host_script(
    *, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> str:
    """Run the exact program the push sends, as the host's python3 would."""
    monkeypatch.setenv("HOME", str(home))
    exec(compile(FORWARD_SCRIPT, "<forward>", "exec"), {"__name__": "__main__"})  # noqa: S102
    return capsys.readouterr().out.strip().splitlines()[-1]


def _api_error(*, text: str, stamp: str = STAMP, account: str | None = "line-uuid") -> str:
    body: dict[str, object] = {
        "isApiErrorMessage": True,
        "timestamp": stamp,
        "message": {"content": text},
    }
    if account is not None:
        body["accountUuid"] = account
    return json.dumps(body)


def test_the_listed_hosts_verified_session_stamps_the_forwarded_refusal(*, tmp_path: Path) -> None:
    _list_host(home=tmp_path)
    calls: list[dict[str, object]] = []

    outcomes = forward_refusals(
        home=tmp_path, now=NOW, run=_runner(line=_reply(host="build-agent-b"), calls=calls)
    )

    assert outcomes == {"build-agent-a": "forwarded"}
    assert [call["target"] for call in calls] == ["ops@build-a"]
    assert calls[0]["program"] == FORWARD_SCRIPT
    assert str(calls[0]["known_hosts"]).endswith("delivery-known_hosts")
    stored = _store(home=tmp_path)
    assert set(stored) == {"build-agent-a"}
    assert stored["build-agent-a"]["target"] == "ops@build-a"
    assert stored["build-agent-a"]["account"] == "uuid-anthropic-1"


def test_a_verified_forwarded_refusal_reaches_the_reader_as_authenticated(
    *, tmp_path: Path
) -> None:
    _list_host(home=tmp_path)
    _ = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=_reply()))

    hosts, records = verified_forwarded(home=tmp_path)
    outcomes = forwarded_refusals(state={"delivery_hosts": hosts, "forwarded_refusals": records})

    assert len(outcomes) == 1
    assert outcomes[0].host == "build-agent-a"
    assert outcomes[0].ignored_reason is None
    assert outcomes[0].refusal is not None
    assert outcomes[0].refusal.account == "uuid-anthropic-1"


def test_a_record_stored_for_another_ssh_target_is_not_authenticated(*, tmp_path: Path) -> None:
    _list_host(home=tmp_path)
    _ = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=_reply()))
    _list_host(home=tmp_path, target="ops@somewhere-else")

    hosts, records = verified_forwarded(home=tmp_path)
    outcomes = forwarded_refusals(state={"delivery_hosts": hosts, "forwarded_refusals": records})

    assert [outcome.ignored_reason for outcome in outcomes] == [
        "not authenticated as that host's own observation"
    ]


def test_a_record_for_a_host_no_longer_listed_is_ignored(*, tmp_path: Path) -> None:
    _list_host(home=tmp_path)
    _ = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=_reply()))
    _list_host(home=tmp_path, label="build-agent-c", target="ops@build-c")

    hosts, records = verified_forwarded(home=tmp_path)
    outcomes = forwarded_refusals(state={"delivery_hosts": hosts, "forwarded_refusals": records})

    assert [outcome.ignored_reason for outcome in outcomes] == ["host is not listed"]


@pytest.mark.parametrize(
    "line",
    [
        "failed host-key-verification",
        "failed timeout",
        "forwarded-refusal not-json",
        "forwarded-refusal []",
        _reply(account=None),
        _reply(recorded_at="yesterday"),
        _reply(provider_message=["usage limit reached"]),
        _reply(provider_message="x" * 500),
    ],
)
def test_an_unusable_reply_forwards_nothing(*, tmp_path: Path, line: str) -> None:
    _list_host(home=tmp_path)

    outcomes = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=line))

    assert outcomes["build-agent-a"] != "forwarded"
    assert verified_forwarded(home=tmp_path) == (["build-agent-a"], [])


def test_a_failed_session_keeps_the_earlier_record_and_a_clear_reply_withdraws_it(
    *, tmp_path: Path
) -> None:
    _list_host(home=tmp_path)
    _ = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=_reply()))

    _ = forward_refusals(home=tmp_path, now=NOW + 60.0, run=_runner(line="failed timeout"))
    assert len(verified_forwarded(home=tmp_path)[1]) == 1

    outcomes = forward_refusals(home=tmp_path, now=NOW + 120.0, run=_runner(line="no-refusal"))
    assert outcomes == {"build-agent-a": "none"}
    assert verified_forwarded(home=tmp_path)[1] == []


def test_forwarding_runs_once_per_interval_and_never_without_listed_hosts(
    *, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []
    run = _runner(line="no-refusal", calls=calls)

    assert forward_if_due(home=tmp_path, now=NOW, due_at=0.0, run=run) > NOW
    assert calls == []

    _list_host(home=tmp_path)
    due_at = forward_if_due(home=tmp_path, now=NOW, due_at=0.0, run=run)
    assert len(calls) == 1
    assert forward_if_due(home=tmp_path, now=NOW + 1.0, due_at=due_at, run=run) == due_at
    assert len(calls) == 1
    assert forward_if_due(home=tmp_path, now=due_at, due_at=due_at, run=run) > due_at
    assert len(calls) == 2


@dataclass(frozen=True, kw_only=True)
class _Context:
    home: Path
    state: dict[str, object]
    now: float
    reports: list[str]

    def stdout(self, line: str) -> None:
        self.reports.append(line)


def _pass(*, home: Path, state: dict[str, object]) -> list[str]:
    reading = UsageRecord(
        five_hour_remaining=45.0,
        seven_day_remaining=60.0,
        five_hour_resets_at=None,
        seven_day_resets_at=None,
        fable_remaining=None,
        fable_resets_at=None,
    )
    context = _Context(home=home, state=state, now=NOW, reports=[])
    observe_pass_refusals(
        context=cast(DecisionContext, context),
        active=ActiveIdentity(profile="anthropic-1", account_uuid="uuid-anthropic-1"),
        current=reading,
        profiles=(ProfileUsage(name="anthropic-1", source="live", usage=reading),),
        source=lambda *, home: (TrackedSession(session_id="s1", config_dir=home / ".claude"),),
    )
    return context.reports


def test_a_pass_holds_the_active_account_only_from_the_verified_store(*, tmp_path: Path) -> None:
    _list_host(home=tmp_path)
    _ = forward_refusals(home=tmp_path, now=NOW, run=_runner(line=_reply()))
    state: dict[str, object] = {"active_since": {"account": "anthropic-1", "at": NOW - 3_600.0}}

    reports = _pass(home=tmp_path, state=state)

    assert len(remembered_refusals(state=state)) == 1
    assert reports == ["forwarded usage-limit refusal from build-agent-a holds the active account"]
    assert "forwarded_refusals" not in state
    assert "delivery_hosts" not in state


def test_a_self_asserted_record_in_loop_state_holds_nothing(*, tmp_path: Path) -> None:
    _list_host(home=tmp_path)
    state: dict[str, object] = {
        "active_since": {"account": "anthropic-1", "at": NOW - 3_600.0},
        "delivery_hosts": ["build-agent-a"],
        "forwarded_refusals": [
            {
                "host": "build-agent-a",
                "authenticated_host": "build-agent-a",
                "account": "uuid-anthropic-1",
                "recorded_at": NOW - 60.0,
                "provider_message": MESSAGE,
            }
        ],
    }

    reports = _pass(home=tmp_path, state=state)

    assert remembered_refusals(state=state) == ()
    assert reports == []
    assert "forwarded_refusals" not in state


def test_the_host_program_reports_the_newest_usage_limit_refusal_it_holds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _host_with_transcript(
        home=tmp_path,
        lines=[
            _api_error(text="usage limit reached|1799990000", stamp="2027-01-15T07:00:00Z"),
            _api_error(text=f"Claude AI usage limit reached|{int(NOW + 3_600.0)}"),
            json.dumps({"timestamp": "2027-01-15T09:00:00Z", "text": "usage limit reached"}),
        ],
    )

    reply = _run_host_script(home=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert reply.startswith("forwarded-refusal ")
    body = json.loads(reply.removeprefix("forwarded-refusal "))
    assert body == {
        "account": "line-uuid",
        "recorded_at": NOW,
        "provider_message": f"usage limit reached|{int(NOW + 3_600.0)}",
    }


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [json.dumps({"timestamp": STAMP, "text": "usage limit reached"})],
        [_api_error(text="authentication error: usage limit reached")],
        [_api_error(text="provider overloaded")],
    ],
)
def test_the_host_program_reports_none_without_a_structural_usage_limit_refusal(
    *,
    tmp_path: Path,
    lines: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host_with_transcript(home=tmp_path, lines=lines or ["{}"])

    assert _run_host_script(home=tmp_path, monkeypatch=monkeypatch, capsys=capsys) == "no-refusal"


def test_the_host_program_reports_none_when_no_refusal_line_names_its_account(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _host_with_transcript(
        home=tmp_path, lines=[_api_error(text="usage limit reached", account=None)]
    )

    assert _run_host_script(home=tmp_path, monkeypatch=monkeypatch, capsys=capsys) == "no-refusal"


def test_the_host_program_attributes_a_refusal_to_the_account_its_own_line_names(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal from before an account switch keeps the old account, not the host's current one."""
    _host_with_transcript(
        home=tmp_path,
        lines=[_api_error(text="usage limit reached", account="before-the-switch-uuid")],
        account="host-uuid-after-the-switch",
    )

    reply = _run_host_script(home=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    body = json.loads(reply.removeprefix("forwarded-refusal "))
    assert body["account"] == "before-the-switch-uuid"


def test_the_host_program_skips_a_newer_refusal_that_names_no_account(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _host_with_transcript(
        home=tmp_path,
        lines=[
            _api_error(text="usage limit reached", stamp="2027-01-15T07:00:00Z", account="named"),
            _api_error(text="usage limit reached", account=None),
        ],
        account=None,
    )

    reply = _run_host_script(home=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    body = json.loads(reply.removeprefix("forwarded-refusal "))
    assert body["account"] == "named"

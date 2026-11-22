"""Fixture-only coverage for forwarded refusal admission and attribution."""

from __future__ import annotations

from pathlib import Path

import pytest
from caam_decision import ProfileUsage, UsageRecord
from caam_forwarded_refusals import forwarded_refusals
from caam_profiles import ActiveIdentity
from caam_refusal_attribution import RefusalObservation, observe_refusals
from caam_refusal_store import remembered_refusals
from caam_refusals import TrackedSession

__all__: list[str] = []

pytestmark = pytest.mark.integration

NOW = 1_800_000_000.0
ACTIVATION = NOW - 3_600.0


def _reading() -> UsageRecord:
    return UsageRecord(
        five_hour_remaining=45.0,
        seven_day_remaining=60.0,
        five_hour_resets_at=None,
        seven_day_resets_at=None,
        fable_remaining=None,
        fable_resets_at=None,
    )


def _state(*, record: dict[str, object]) -> dict[str, object]:
    return {
        "active_since": {"account": "anthropic-1", "at": ACTIVATION},
        "delivery_hosts": ["build-agent-a"],
        "forwarded_refusals": [record],
    }


def _record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "host": "build-agent-a",
        "authenticated_host": "build-agent-a",
        "account": "uuid-anthropic-1",
        "recorded_at": NOW - 60.0,
        "provider_message": f"Claude AI usage limit reached|{int(NOW + 3_600.0)}",
    }
    record.update(changes)
    return record


def _observe(*, state: dict[str, object], should_report: bool = True) -> list[str]:
    reading = _reading()
    report: list[str] = []
    observe_refusals(
        observation=RefusalObservation(
            home=Path("/home/op"),
            state=state,
            active=ActiveIdentity(profile="anthropic-1", account_uuid="uuid-anthropic-1"),
            current=reading,
            profiles=(ProfileUsage(name="anthropic-1", source="live", usage=reading),),
            sessions=(TrackedSession(session_id="s1", config_dir=Path("/home/op/.claude")),),
            now=NOW,
            reader=lambda *, session: (),
            report=report.append if should_report else None,
        )
    )
    return report


def test_a_legitimate_forwarded_refusal_holds_the_active_account_fleet_wide() -> None:
    state = _state(record=_record())

    report = _observe(state=state)

    assert len(remembered_refusals(state=state)) == 1
    assert report == ["forwarded usage-limit refusal from build-agent-a holds the active account"]


def test_a_forwarded_refusal_holds_without_an_operator_reporter() -> None:
    state = _state(record=_record())

    report = _observe(state=state, should_report=False)

    assert len(remembered_refusals(state=state)) == 1
    assert report == []


def test_a_forwarded_refusal_for_a_non_active_account_is_ignored() -> None:
    state = _state(record=_record(account="uuid-anthropic-2"))

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == [
        "forwarded refusal from build-agent-a ignored: does not name the active account"
    ]


def test_a_stale_forwarded_refusal_is_ignored() -> None:
    state = _state(record=_record(recorded_at=NOW - 120.0))
    state["lapsed_refusals"] = [
        {"account": "anthropic-1", "window": "five_hour", "recorded_at": NOW - 60.0}
    ]

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == ["forwarded refusal from build-agent-a ignored: stale"]


def test_an_unauthenticated_forwarded_refusal_is_ignored() -> None:
    state = _state(record=_record(authenticated_host="build-agent-b"))

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == [
        "forwarded refusal from build-agent-a ignored: "
        "not authenticated as that host's own observation"
    ]


def test_an_ignored_forwarded_refusal_needs_no_operator_reporter() -> None:
    state = _state(record=_record(authenticated_host="build-agent-b"))

    report = _observe(state=state, should_report=False)

    assert remembered_refusals(state=state) == ()
    assert report == []


def test_a_forwarded_authentication_error_is_not_a_usage_limit_refusal() -> None:
    state = _state(record=_record(provider_message="authentication error: usage limit reached"))

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == ["forwarded refusal from build-agent-a ignored: not a usage-limit refusal"]


def test_malformed_or_unlisted_forwarded_records_are_reported_as_ignored() -> None:
    state = {
        "delivery_hosts": ["build-agent-a"],
        "forwarded_refusals": [
            _record(host="build-agent-b"),
            {"host": "build-agent-a", "authenticated_host": "build-agent-a"},
            {"authenticated_host": "build-agent-a"},
            _record(provider_message="provider overloaded"),
        ],
    }

    outcomes = forwarded_refusals(state=state)

    assert tuple(outcome.ignored_reason for outcome in outcomes) == (
        "host is not listed",
        "record is incomplete",
        "host is not listed",
        "not a usage-limit refusal",
    )


def test_an_expired_forwarded_refusal_is_reported_as_stale() -> None:
    state = _state(record=_record(provider_message=f"usage limit reached|{int(NOW - 1.0)}"))

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == ["forwarded refusal from build-agent-a ignored: stale"]


def test_a_forwarded_refusal_matching_a_departed_reset_is_not_attributed() -> None:
    state = _state(record=_record())
    state["departed_accounts"] = {"anthropic-2": {"five_hour_resets_at": "2027-01-15T09:00:00Z"}}

    report = _observe(state=state)

    assert remembered_refusals(state=state) == ()
    assert report == ["forwarded refusal from build-agent-a ignored: not attributable"]


def test_forwarded_provider_messages_use_the_local_refusal_windows_and_resets() -> None:
    state = {
        "delivery_hosts": ["build-agent-a"],
        "forwarded_refusals": [
            _record(provider_message="weekly limit reached"),
            _record(provider_message="rate_limit_error retry-after: 120"),
            _record(provider_message="rate limit exceeded retry-after: unavailable"),
            _record(provider_message="authentication error"),
        ],
    }

    refusals = forwarded_refusals(state=state)

    parsed = tuple(outcome.refusal for outcome in refusals if outcome.refusal is not None)

    assert tuple((refusal.window, refusal.resets_at) for refusal in parsed) == (
        ("seven_day", None),
        ("five_hour", NOW + 60.0),
        ("five_hour", None),
    )
    assert refusals[-1].ignored_reason == "not a usage-limit refusal"

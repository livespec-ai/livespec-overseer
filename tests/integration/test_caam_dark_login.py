"""A dark active login is left at once (overseer-iusknl).

Covers spec.md "Account rotation and quota supervision" **A dark active login
MUST be left at once.** and its login-hold paragraph, driven through the SHIPPED
rotation pass. The tracked sessions and the provider's readings are injected, as
the refusal trigger's scenarios do; the transcript, the live credential file and
the login record store are real files under a tmp home.

Every credential here is an obviously fake placeholder; no test reads, prints or
compares a real credential.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from caam_anthropic_loop import Flags
from caam_anthropic_pass import run_pass
from caam_dark_login import DarkObservation, observe_dark_logins
from caam_decision import UsageRecord
from caam_login_records import (
    current_login,
    load_records,
    locked,
    record_login,
    records_path,
    save_records,
)
from caam_profile_state import STATE_REL
from caam_profiles import ActiveIdentity
from caam_switch import REASON_SWITCHED, SwitchRequest, SwitchResult

from tests.test_caam_anthropic_loop import no_plan_read

__all__: list[str] = []

pytestmark = pytest.mark.integration

NOW = 1_800_000_000.0
HOUR = 3_600.0
ACTIVE = "anthropic-3"
OTHER = "anthropic-1"
FAKE = "FAKE-PLACEHOLDER-NOT-A-REAL-TOKEN"
LIFETIME_CAP_TEXT = "Your login reached its time limit and cannot be renewed"


def stamp(*, at: float) -> str:
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def usage(*, weekly: float = 80.0, five_hour: float = 80.0) -> UsageRecord:
    reset = datetime.fromtimestamp(NOW + 604_800.0, tz=timezone.utc).isoformat()
    return UsageRecord(
        five_hour_remaining=five_hour,
        seven_day_remaining=weekly,
        five_hour_resets_at=datetime.fromtimestamp(NOW + HOUR, tz=timezone.utc).isoformat(),
        seven_day_resets_at=reset,
        fable_remaining=80.0,
        fable_resets_at=reset,
    )


@dataclass(frozen=True, kw_only=True)
class StandIn:
    session_id: str
    config_dir: Path
    provider: str = "anthropic"


@dataclass(kw_only=True)
class Harness:
    home: Path
    usages: dict[str, UsageRecord]
    active: str = ACTIVE
    refused: dict[str, str] = field(default_factory=dict)
    plans: dict[str, str] = field(default_factory=dict)
    sessions: tuple[StandIn, ...] = ()
    switches: list[str] = field(default_factory=list)
    requests: list[Path] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)
    push_outcome: str = "sent 200"

    def __post_init__(self) -> None:
        for name in self.usages:
            profile = self.home / ".local/share/caam/vault/claude" / name
            profile.mkdir(parents=True, exist_ok=True)
            (profile / ".credentials.json").write_text("{}\n", encoding="utf-8")
            self._account(path=profile / ".claude.json", name=name)
        self._account(path=self.home / ".claude.json", name=self.active)
        self.write_live_credential(expires_at=NOW + 4 * HOUR)
        state = self.home / STATE_REL
        state.parent.mkdir(parents=True, exist_ok=True)
        if not state.exists():
            state.write_text(
                json.dumps({"active_since": {"account": self.active, "at": NOW - 5 * HOUR}}),
                encoding="utf-8",
            )

    def write_live_credential(self, *, expires_at: float, token: str = FAKE) -> None:
        live = self.home / ".claude/.credentials.json"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": token, "expiresAt": expires_at * 1000}}),
            encoding="utf-8",
        )

    def record_login_refusal(self, *, at: float, text: str = LIFETIME_CAP_TEXT) -> None:
        path = self.home / ".claude/projects/-data-projects/live.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": stamp(at=at),
                        "isApiErrorMessage": True,
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": text}],
                        },
                    }
                )
                + "\n"
            )
        self.sessions = (StandIn(session_id="live", config_dir=self.home / ".claude"),)

    def configure_push(self) -> None:
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"env": {"CLAUDE_NTFY_TOPIC": "rotation-test"}}), "utf-8")

    def store(self) -> dict[str, object]:
        return load_records(path=records_path(home=self.home)).records

    def run(self, *, at: float = NOW) -> tuple[int, tuple[str, ...]]:
        lines: list[str] = []
        code = run_pass(
            flags=Flags(
                scheduled=True,
                force=False,
                dry_run=False,
                no_models=True,
                no_warm=True,
                session_models=(),
                protected_accounts=(),
            ),
            home=self.home,
            now=at,
            stdout=lines.append,
            caam_runner=self._caam,
            capacity_source=self._plan if self.plans else no_plan_read,
            fetcher=self._fetch,
            switch_account=self._switch,
            enforce_models=lambda **kwargs: [],
            tracked_sessions=lambda *, home: self.sessions,
            push_post=self._push,
        )
        return code, tuple(lines)

    def _push(self, *, url: str, message: str) -> str:
        del url
        self.pushed.append(message)
        return self.push_outcome

    def _caam(self, *, args: tuple[str, ...]) -> object:
        del args
        body = json.dumps({"tools": [{"tool": "claude", "active_profile": self.active}]})
        return type("Process", (), {"returncode": 0, "stdout": body, "stderr": ""})()

    def _fetch(
        self, *, creds_path: Path, now: float | None = None
    ) -> tuple[UsageRecord | None, str | None]:
        del now
        self.requests.append(creds_path)
        name = (
            self.active
            if creds_path == self.home / ".claude/.credentials.json"
            else creds_path.parent.name
        )
        if name in self.refused:
            return None, self.refused[name]
        return self.usages[name], None

    def _plan(self, *, creds_path: Path, now: float | None = None) -> tuple[str | None, str | None]:
        del now
        name = (
            self.active
            if creds_path == self.home / ".claude/.credentials.json"
            else creds_path.parent.name
        )
        return self.plans.get(name), None

    def _switch(self, *, request: SwitchRequest) -> SwitchResult:
        self.switches.append(request.target.name)
        self.active = request.target.name
        self._account(path=self.home / ".claude.json", name=self.active)
        request.state["active_since"] = {"account": self.active, "at": request.now}
        request.save(state=request.state)
        return SwitchResult(
            exit_code=0, reason=REASON_SWITCHED, switched=True, lines=("SWITCHED generic",)
        )

    @staticmethod
    def _account(*, path: Path, name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"oauthAccount": {"accountUuid": f"uuid-{name}"}}), "utf-8")


def two_accounts(*, tmp_path: Path, other: UsageRecord | None = None) -> Harness:
    return Harness(home=tmp_path, usages={ACTIVE: usage(), OTHER: other or usage(weekly=70.0)})


def test_scenario_a_dark_active_login_is_left_on_the_next_pass_and_ends_dark_with_a_hold(
    *, tmp_path: Path
) -> None:
    """Condition (a), whatever the usage figures report, through the real pass path."""
    harness = two_accounts(tmp_path=tmp_path)
    harness.record_login_refusal(at=NOW - HOUR)

    code, lines = harness.run()

    assert code == 0
    assert harness.switches == [OTHER]
    switched = next(line for line in lines if line.startswith("SWITCHED") and "dark login" in line)
    assert f"{ACTIVE}'s login was judged dark by condition (a)" in switched
    assert stamp(at=NOW) in switched
    store = harness.store()
    assert current_login(records=store, name=ACTIVE) is None
    past = store["accounts"][ACTIVE]["past"]  # type: ignore[index]
    assert [(item["end_cause"], item["condition"]) for item in past] == [("dark", "a")]
    assert store["holds"][ACTIVE]["since"] == NOW  # type: ignore[index]
    assert store["holds"][ACTIVE]["condition"] == "a"  # type: ignore[index]
    # Detecting under (a) sent no request of its own: only the ordinary readings.
    assert all(path.name == ".credentials.json" for path in harness.requests)


def test_scenario_a_dark_login_pushes_one_onset_alert_without_credential_material(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.configure_push()
    harness.record_login_refusal(at=NOW - HOUR)

    code, _lines = harness.run()

    assert code == 0
    assert len(harness.pushed) == 1
    assert "dark login" in harness.pushed[0]
    assert ACTIVE in harness.pushed[0]
    assert FAKE not in harness.pushed[0]


def test_a_failed_dark_login_alert_is_reported_without_blocking_its_rotation(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.configure_push()
    harness.push_outcome = "failed OSError"
    harness.record_login_refusal(at=NOW - HOUR)

    code, lines = harness.run()

    assert code == 0
    assert harness.switches == [OTHER]
    assert any("alert delivery failed" in line for line in lines)


def test_a_dark_login_alert_repeats_after_six_hours_and_recovers_when_its_hold_ends(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.configure_push()
    harness.record_login_refusal(at=NOW - HOUR)

    assert harness.run()[0] == 0
    assert harness.run(at=NOW + HOUR)[0] == 0
    assert len(harness.pushed) == 1
    assert harness.run(at=NOW + 7 * HOUR)[0] == 0
    assert len(harness.pushed) == 2
    path = records_path(home=harness.home)
    with locked(path=path):
        records = load_records(path=path).records
        record_login(
            records=records,
            name=ACTIVE,
            minted_at=NOW + 7 * HOUR,
            source="test recovery",
            now=NOW + 7 * HOUR,
        )
        save_records(path=path, records=records)

    assert harness.run(at=NOW + 8 * HOUR)[0] == 0
    assert len(harness.pushed) == 3
    assert "recovery" in harness.pushed[-1]


def test_scenario_a_refusal_before_the_activation_or_the_recorded_mint_is_not_this_login(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.record_login_refusal(at=NOW - 6 * HOUR)  # before the account became active

    code, _lines = harness.run()

    assert code == 0
    assert harness.switches == []
    assert not harness.store()["holds"]


def test_scenario_an_expired_access_token_alone_does_not_trigger_a_dark_login_rotation(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.write_live_credential(expires_at=NOW - HOUR)
    harness.refused[ACTIVE] = "token expired 1.0h ago"

    for index in range(3):
        _ = harness.run(at=NOW + index * 1_800.0)

    assert harness.switches == []
    store = harness.store()
    assert not store["holds"]
    assert not store.get("suspects")


def test_scenario_one_refused_reading_does_not_judge_a_login_dark(*, tmp_path: Path) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth token has been revoked"

    _code, _lines = harness.run()

    assert harness.switches == []
    assert not harness.store()["holds"]

    # The next reading is healthy: the first refusal is forgotten, not carried.
    del harness.refused[ACTIVE]
    _ = harness.run(at=NOW + 1_800.0)
    harness.refused[ACTIVE] = "OAuth token has been revoked"
    _ = harness.run(at=NOW + 3_600.0)
    assert harness.switches == []
    assert not harness.store()["holds"]


def test_scenario_a_refused_reading_with_a_changed_credential_does_not_judge_dark(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth token has been revoked"
    _ = harness.run()
    harness.write_live_credential(expires_at=NOW + 4 * HOUR, token=FAKE + "-REFRESHED")

    _ = harness.run(at=NOW + 1_800.0)

    assert harness.switches == []
    assert not harness.store()["holds"]


def test_scenario_two_consecutive_refused_readings_with_an_unchanged_credential_judge_dark(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth token has been revoked"

    _ = harness.run()
    assert harness.switches == []
    first_store = (harness.home / ".local/state/caam-usage-rotate/login-records.json").read_text()
    assert FAKE not in first_store  # only a hash of the credential is kept
    _code, lines = harness.run(at=NOW + 1_800.0)

    assert harness.switches == [OTHER]
    switched = next(line for line in lines if "dark login" in line and "SWITCHED" in line)
    assert "condition (b)" in switched
    assert stamp(at=NOW + 1_800.0) in switched
    store = harness.store()
    assert store["holds"][ACTIVE]["condition"] == "b"  # type: ignore[index]
    assert ACTIVE not in store["suspects"]  # type: ignore[operator]


def test_scenario_a_rate_limited_reading_between_refusals_preserves_the_dark_login_suspect(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."

    _ = harness.run()
    harness.refused[ACTIVE] = "HTTP 429 rate_limit_error: retry later"
    _ = harness.run(at=NOW + 1_800.0)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."
    _code, lines = harness.run(at=NOW + 3_600.0)

    assert harness.switches == [OTHER]
    switched = next(line for line in lines if "dark login" in line and "SWITCHED" in line)
    assert "condition (b)" in switched
    assert harness.store()["holds"][ACTIVE]["condition"] == "b"  # type: ignore[index]


def test_scenario_two_revoked_token_refusals_with_the_provider_wording_judge_dark(
    *, tmp_path: Path
) -> None:
    """Condition (b) keys the provider's revoked-token refusal as unauthenticated."""
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."

    _ = harness.run()
    _code, lines = harness.run(at=NOW + 1_800.0)

    assert harness.switches == [OTHER]
    switched = next(line for line in lines if "dark login" in line and "SWITCHED" in line)
    assert "condition (b)" in switched
    assert harness.store()["holds"][ACTIVE]["condition"] == "b"  # type: ignore[index]


def test_scenario_a_dark_active_login_with_no_surviving_candidate_holds_and_reports(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path, other=usage(weekly=0.0, five_hour=0.0))
    harness.record_login_refusal(at=NOW - HOUR)

    code, lines = harness.run()

    assert code == 0
    assert harness.switches == []
    report = next(line for line in lines if line.startswith("hold:"))
    assert f"{ACTIVE}'s login is dark" in report
    assert "no account could be selected" in report
    assert "reset" not in report
    assert harness.store()["holds"][ACTIVE]  # type: ignore[index]


def test_scenario_a_login_hold_survives_a_restart_and_is_never_selected(*, tmp_path: Path) -> None:
    first = two_accounts(tmp_path=tmp_path, other=usage(weekly=0.0, five_hour=0.0))
    first.record_login_refusal(at=NOW - HOUR)
    _ = first.run()
    assert first.switches == []

    # A restart: a new process, with no memory but the files, and no transcript.
    # The held account still reads healthy; the other has recovered.
    second = Harness(home=tmp_path, usages={ACTIVE: usage(weekly=95.0), OTHER: usage()})
    second.sessions = ()
    _code, lines = second.run(at=NOW + 3 * HOUR)

    assert second.switches == [OTHER]
    assert any(f"{ACTIVE}'s login was judged dark by condition (a)" in line for line in lines)
    # The fleet is not returned to it: the new active account is nearly spent and
    # the held account reads healthiest of all, yet it is no candidate.
    second.usages[OTHER] = usage(weekly=3.0, five_hour=3.0)
    _code, lines = second.run(at=NOW + 4 * HOUR)

    assert second.switches == [OTHER]
    assert any(line.startswith("hold:") for line in lines)
    assert second.active == OTHER


def test_a_revoked_login_is_judged_dark_and_a_refresh_failure_alone_is_not(
    *, tmp_path: Path
) -> None:
    """The two wordings are separate kinds, and a refresh that merely failed is neither."""
    harness = two_accounts(tmp_path=tmp_path)
    harness.record_login_refusal(
        at=NOW - HOUR, text="OAuth session expired and could not be refreshed"
    )

    _ = harness.run()

    assert harness.switches == []
    assert not harness.store()["holds"]

    harness.record_login_refusal(at=NOW - HOUR / 2, text="Your login has been revoked")
    _ = harness.run(at=NOW + 600.0)

    assert harness.switches == [OTHER]
    hold = harness.store()["holds"][ACTIVE]  # type: ignore[index]
    assert "revoked" in hold["evidence"]


def test_a_refusal_that_is_not_an_authentication_refusal_never_becomes_a_suspicion(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "HTTP 429"
    _ = harness.run()
    harness.refused[ACTIVE] = "HTTP 429"
    _ = harness.run(at=NOW + 1_800.0)

    assert harness.switches == []
    assert not harness.store().get("suspects")


def test_a_suspicion_of_an_account_that_is_no_longer_active_is_forgotten(*, tmp_path: Path) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    path = records_path(home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"accounts": {}, "holds": {}, "suspects": {OTHER: {"fingerprint": "x"}}}),
        encoding="utf-8",
    )

    _ = harness.run()

    assert not harness.store()["suspects"]


def test_an_unreadable_or_unwritable_store_yields_no_hold_and_stops_no_pass(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    path = records_path(home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1]", encoding="utf-8")
    harness.record_login_refusal(at=NOW - HOUR)

    code, _lines = harness.run()

    assert code == 0
    assert harness.switches == []
    assert path.read_text(encoding="utf-8") == "[1]"
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / ".local").write_text("a file where a directory must be", encoding="utf-8")
    observation = DarkObservation(
        home=blocked,
        state={},
        active=ActiveIdentity(profile=ACTIVE, account_uuid=None),
        profiles=(),
        live_before=None,
        sessions=lambda: (),
        now=NOW,
        dry_run=False,
    )
    assert observe_dark_logins(observation=observation) == {}


def test_scenario_a_dark_login_holds_where_the_capacity_test_excludes_every_candidate(
    *, tmp_path: Path
) -> None:
    """The capacity test's release is NOT extended to a dark login."""
    harness = Harness(
        home=tmp_path,
        usages={ACTIVE: usage(five_hour=60.0), OTHER: usage(five_hour=50.0)},
        plans={ACTIVE: "default_claude_max_20x", OTHER: "default_claude_ai"},
    )
    _ = harness.run(at=NOW)
    harness.record_login_refusal(at=NOW + 600.0)

    code, lines = harness.run(at=NOW + 1_800.0)

    assert code == 0
    assert harness.switches == []
    report = next(line for line in lines if line.startswith("hold:"))
    assert f"{ACTIVE}'s login is dark" in report
    assert "capacity test" in report


def test_a_refusal_with_an_already_expired_access_token_is_not_a_dark_login(
    *, tmp_path: Path
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.write_live_credential(expires_at=NOW - HOUR)
    harness.refused[ACTIVE] = "OAuth token has been revoked"

    _ = harness.run()
    _ = harness.run(at=NOW + 1_800.0)

    assert harness.switches == []
    assert not harness.store()["holds"]

"""Login records, login age and the lifetime cap (overseer-oomnmk).

Covers spec.md "Account rotation and quota supervision" **Login records.** and
**Login age and the lifetime cap.**: the durable per-account login record, the
`record-login` operator command, and the loop's report of each login's age.

Every credential here is an obviously fake placeholder written into a tmp home;
no test reads, prints or compares a real credential.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from caam_anthropic_loop import Flags
from caam_anthropic_pass import run_pass
from caam_decision import UsageRecord
from caam_login_pass import observe_pass_logins
from caam_login_records import (
    RETENTION_DAYS,
    current_login,
    end_login,
    load_records,
    note_first_seen,
    prune_records,
    record_login,
    records_path,
    save_records,
)
from caam_login_report import lifetime_settings, login_report_lines
from caam_record_login import credential_write_time, main

from tests.test_caam_anthropic_loop import no_plan_read

__all__: list[str] = []

ACTIVE = "active"
OTHER = "other"
DAY = 86400.0
NOW = 1789000000.0
FAKE = "FAKE-PLACEHOLDER-NOT-A-REAL-TOKEN"
CAP_ENV = "CAAM_ROTATE_LOGIN_LIFETIME_CAP_HOURS"
LEAD_ENV = "CAAM_ROTATE_LOGIN_WARNING_LEAD_HOURS"


class _Caam:
    returncode = 0
    stderr = ""
    stdout = json.dumps({"tools": [{"tool": "claude", "active_profile": ACTIVE}]})


def _home(*, tmp_path: Path) -> Path:
    vault = tmp_path / ".local/share/caam/vault/claude"
    for name in (ACTIVE, OTHER):
        (vault / name).mkdir(parents=True, exist_ok=True)
        _ = (vault / name / ".claude.json").write_text(
            json.dumps({"oauthAccount": {"accountUuid": f"uuid-{name}"}}), encoding="utf-8"
        )
        _ = (vault / name / ".credentials.json").write_text(_credential(tag=name), encoding="utf-8")
    _ = (tmp_path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"accountUuid": f"uuid-{ACTIVE}"}}), encoding="utf-8"
    )
    live = tmp_path / ".claude"
    live.mkdir(parents=True, exist_ok=True)
    _ = (live / ".credentials.json").write_text(_credential(tag="live"), encoding="utf-8")
    return tmp_path


def _credential(*, tag: str) -> str:
    return json.dumps(
        {"claudeAiOauth": {"accessToken": f"{FAKE}-{tag}-access", "refreshToken": f"{FAKE}-{tag}"}}
    )


def _login_dir(*, tmp_path: Path, written_at: float | None = NOW, tag: str = "new") -> Path:
    config = tmp_path / f"config-{tag}"
    config.mkdir(parents=True, exist_ok=True)
    cred = config / ".credentials.json"
    _ = cred.write_text(_credential(tag=tag), encoding="utf-8")
    if written_at is not None:
        os.utime(cred, (written_at, written_at))
    return config


def _usage(*, five: float) -> UsageRecord:
    return UsageRecord(
        five_hour_remaining=five,
        seven_day_remaining=70.0,
        five_hour_resets_at="2026-09-09T12:00:00Z",
        seven_day_resets_at="2026-09-11T00:00:00Z",
        fable_remaining=90.0,
        fable_resets_at="2026-09-11T00:00:00Z",
    )


def _pass(*, home: Path, now: float, dry: bool = False, active_five: float = 80.0) -> list[str]:
    lines: list[str] = []
    by_account = {ACTIVE: active_five, OTHER: 90.0}

    def fetch(*, creds_path: Path, now: float | None = None) -> tuple[UsageRecord, None]:
        owner = OTHER if f"/{OTHER}/" in str(creds_path) else ACTIVE
        return (_usage(five=by_account[owner]), None)

    _ = run_pass(
        flags=Flags(
            scheduled=True,
            force=False,
            dry_run=dry,
            no_models=True,
            no_warm=True,
            session_models=(),
            protected_accounts=(),
        ),
        home=home,
        now=now,
        stdout=lines.append,
        caam_runner=lambda *, args: _Caam(),
        capacity_source=no_plan_read,
        fetcher=fetch,
        save_state=lambda *, state, state_path: None,
    )
    return lines


def _record(*, home: Path, tmp_path: Path, account: str, now: float, written_at: float | None):
    out: list[str] = []
    config = _login_dir(
        tmp_path=tmp_path,
        written_at=now if written_at is None else written_at,
        tag=f"{account}{int(now)}",
    )
    code = main(argv=[account, "--config-dir", str(config)], home=home, now=now, stdout=out.append)
    return code, out


def _store(*, home: Path) -> dict[str, object]:
    loaded = load_records(path=records_path(home=home))
    assert loaded.problem is None
    return loaded.records


def _account(*, home: Path, name: str) -> dict[str, object]:
    accounts = _store(home=home)["accounts"]
    assert isinstance(accounts, dict)
    entry = accounts[name]
    assert isinstance(entry, dict)
    return entry


def _login_lines(*, lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith(("LOGIN", "WARN login"))]


# --- A recorded login shows its age in the report -----------------------------


def test_a_recorded_login_shows_its_age_and_recorded_mint_time(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CAP_ENV, raising=False)
    home = _home(tmp_path=tmp_path)
    code, out = _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    assert code == 0
    assert any("file write time" in line for line in out)
    lines = _pass(home=home, now=NOW + DAY)
    mine = [line for line in lines if line.startswith(f"LOGIN {OTHER}:")]
    assert len(mine) == 1
    assert "age 1d 0h" in mine[0]
    assert "(recorded)" in mine[0]
    assert "lower bound" not in mine[0]
    # the account that never had a record is first-seen, its age a lower bound
    active_line = next(line for line in lines if line.startswith(f"LOGIN {ACTIVE}:"))
    assert "(first-seen)" in active_line
    assert "lower bound" in active_line


def test_the_command_says_it_used_the_command_time_when_no_write_time_is_readable(
    *, tmp_path: Path
) -> None:
    home = _home(tmp_path=tmp_path)
    assert credential_write_time(path=tmp_path / "missing") is None
    assert credential_write_time(path=tmp_path) is not None
    config = _login_dir(tmp_path=tmp_path)
    cred = config / ".credentials.json"
    out: list[str] = []
    code = main(
        argv=[OTHER, "--config-dir", str(config)],
        home=home,
        now=NOW + 5,
        stdout=out.append,
        write_time=lambda *, path: None,
    )
    assert code == 0
    assert cred.exists()
    assert any("command time" in line for line in out)
    login = current_login(records=_store(home=home), name=OTHER)
    assert login is not None
    assert login["minted_at"] == NOW + 5
    assert login["basis"] == "recorded"


# --- The command stores the credential and never touches the live one ---------


def test_record_login_stores_the_credential_and_never_writes_the_live_one(
    *, tmp_path: Path
) -> None:
    home = _home(tmp_path=tmp_path)
    live = home / ".claude/.credentials.json"
    live_before = live.read_bytes()
    config = _login_dir(tmp_path=tmp_path, tag="stored")
    code, out = _record(home=home, tmp_path=tmp_path, account=ACTIVE, now=NOW, written_at=NOW)
    assert code == 0
    stored = home / ".local/share/caam/vault/claude" / ACTIVE / ".credentials.json"
    assert FAKE in stored.read_text(encoding="utf-8")
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert live.read_bytes() == live_before
    assert not any(FAKE in line for line in out)
    assert config.exists()


def test_record_login_refuses_what_it_cannot_store_and_changes_nothing(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    out: list[str] = []
    assert main(argv=[], home=home, now=NOW, stdout=out.append) == 2
    assert main(argv=[OTHER], home=home, now=NOW, stdout=out.append) == 2
    config = _login_dir(tmp_path=tmp_path)
    assert (
        main(argv=["ghost", "--config-dir", str(config)], home=home, now=NOW, stdout=out.append)
        == 2
    )
    empty = tmp_path / "empty"
    empty.mkdir()
    assert (
        main(argv=[OTHER, "--config-dir", str(empty)], home=home, now=NOW, stdout=out.append) == 2
    )
    junk = tmp_path / "junk"
    junk.mkdir()
    _ = (junk / ".credentials.json").write_text("not json", encoding="utf-8")
    assert main(argv=[OTHER, "--config-dir", str(junk)], home=home, now=NOW, stdout=out.append) == 2
    plain = tmp_path / "plain"
    plain.mkdir()
    _ = (plain / ".credentials.json").write_text('{"other": 1}', encoding="utf-8")
    assert (
        main(argv=[OTHER, "--config-dir", str(plain)], home=home, now=NOW, stdout=out.append) == 2
    )
    assert all(line.startswith("FAIL") for line in out)
    assert not records_path(home=home).exists()
    stored = home / ".local/share/caam/vault/claude" / OTHER / ".credentials.json"
    assert FAKE in stored.read_text(encoding="utf-8")
    assert "-other-" in stored.read_text(encoding="utf-8")


def test_record_login_reports_a_corrupt_store_and_leaves_it_alone(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    path = records_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("not json", encoding="utf-8")
    code, out = _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    assert code == 2
    assert out[-1].startswith("FAIL")
    assert path.read_text(encoding="utf-8") == "not json"


def test_record_login_leaves_the_vault_unchanged_when_saving_the_record_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path=tmp_path)
    stored = home / ".local/share/caam/vault/claude" / OTHER / ".credentials.json"
    before = stored.read_bytes()
    config = _login_dir(tmp_path=tmp_path, tag="save-failure")
    out: list[str] = []

    def fail_save(*, path: Path, records: object) -> None:
        raise OSError("injected save failure")

    monkeypatch.setattr("caam_record_login.save_records", fail_save)

    assert (
        main(argv=[OTHER, "--config-dir", str(config)], home=home, now=NOW, stdout=out.append) == 2
    )
    assert stored.read_bytes() == before
    assert not records_path(home=home).exists()
    assert out[-1].startswith("FAIL could not record the login")


# --- Recording a new login replaces the old one and releases a login hold -----


def test_recording_a_new_login_ends_the_old_one_as_replaced(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    code, out = _record(
        home=home, tmp_path=tmp_path, account=OTHER, now=NOW + DAY, written_at=NOW + DAY
    )
    assert code == 0
    assert any("replaced" in line for line in out)
    entry = _account(home=home, name=OTHER)
    past = entry["past"]
    assert isinstance(past, list)
    assert len(past) == 1
    assert past[0]["end_cause"] == "replaced"
    assert past[0]["ended_at"] == NOW + DAY
    login = current_login(records=_store(home=home), name=OTHER)
    assert login is not None
    assert login["minted_at"] == NOW + DAY


def test_recording_a_new_login_releases_a_login_hold_and_keeps_the_dark_end(
    *, tmp_path: Path
) -> None:
    home = _home(tmp_path=tmp_path)
    _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    records = _store(home=home)
    assert end_login(records=records, name=OTHER, now=NOW + DAY, cause="dark", evidence="refused")
    save_records(path=records_path(home=home), records=records)
    holds = _store(home=home)["holds"]
    assert isinstance(holds, dict)
    assert OTHER in holds
    assert current_login(records=_store(home=home), name=OTHER) is None
    code, out = _record(
        home=home, tmp_path=tmp_path, account=OTHER, now=NOW + 2 * DAY, written_at=NOW + 2 * DAY
    )
    assert code == 0
    assert any("released" in line for line in out)
    assert OTHER not in _store(home=home)["holds"]  # type: ignore[operator]
    past = _account(home=home, name=OTHER)["past"]
    assert isinstance(past, list)
    assert [item["end_cause"] for item in past] == ["dark"]
    assert past[0]["evidence"] == "refused"
    assert current_login(records=_store(home=home), name=OTHER) is not None


def test_ending_a_login_that_is_already_ended_changes_nothing() -> None:
    records: dict[str, object] = {"accounts": {}, "holds": {}}
    assert not end_login(records=records, name=OTHER, now=NOW, cause="dark", evidence="x")
    assert records == {"accounts": {}, "holds": {}}


# --- A refresh does not start a new login record ------------------------------


def test_a_refresh_leaves_the_login_record_and_its_mint_time_unchanged(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    before = _account(home=home, name=OTHER)
    stored = home / ".local/share/caam/vault/claude" / OTHER / ".credentials.json"
    _ = stored.write_text(_credential(tag="refreshed"), encoding="utf-8")
    _ = _pass(home=home, now=NOW + DAY)
    _ = _pass(home=home, now=NOW + 2 * DAY)
    assert _account(home=home, name=OTHER) == before
    assert before["past"] == []


# --- First-seen records --------------------------------------------------------


def test_first_seen_is_given_only_to_an_account_that_never_had_a_record(*, tmp_path: Path) -> None:
    records: dict[str, object] = {"accounts": {}, "holds": {}}
    assert note_first_seen(records=records, name=ACTIVE, now=NOW)
    assert not note_first_seen(records=records, name=ACTIVE, now=NOW + DAY)
    login = current_login(records=records, name=ACTIVE)
    assert login is not None
    assert login["basis"] == "first-seen"
    assert login["minted_at"] == NOW
    assert end_login(records=records, name=ACTIVE, now=NOW + DAY, cause="dark", evidence="x")
    assert not note_first_seen(records=records, name=ACTIVE, now=NOW + 2 * DAY)
    assert current_login(records=records, name=ACTIVE) is None


def test_a_pass_gives_first_seen_records_once_and_not_to_an_ended_login(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    _ = _pass(home=home, now=NOW)
    records = _store(home=home)
    assert end_login(records=records, name=OTHER, now=NOW + DAY, cause="dark", evidence="x")
    save_records(path=records_path(home=home), records=records)
    lines = _pass(home=home, now=NOW + 2 * DAY)
    assert current_login(records=_store(home=home), name=OTHER) is None
    ended = next(line for line in lines if line.startswith(f"LOGIN {OTHER}:"))
    assert "no current login" in ended
    assert "dark" in ended
    assert "login-held" in ended
    still = current_login(records=_store(home=home), name=ACTIVE)
    assert still is not None
    assert still["minted_at"] == NOW


def test_a_dry_run_pass_writes_no_records(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    lines = _pass(home=home, now=NOW, dry=True)
    assert not records_path(home=home).exists()
    assert any(line.startswith(f"LOGIN {ACTIVE}:") for line in lines)


def test_a_corrupt_store_is_reported_not_replaced(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    path = records_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("[1]", encoding="utf-8")
    lines = _pass(home=home, now=NOW)
    assert any(line.startswith("FAIL login records") for line in lines)
    assert path.read_text(encoding="utf-8") == "[1]"
    unwritable = tmp_path / "blocked"
    unwritable.mkdir()
    _ = (unwritable / ".local").write_text("a file where a directory must be", encoding="utf-8")
    out: list[str] = []
    observe_pass_logins(home=unwritable, names=(ACTIVE,), now=NOW, dry_run=False, stdout=out.append)
    assert any(line.startswith("FAIL login records") for line in out)


# --- The lifetime cap ----------------------------------------------------------


def test_no_lifetime_cap_warning_before_the_cap_is_measured(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CAP_ENV, raising=False)
    home = _home(tmp_path=tmp_path)
    _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW - 400 * DAY, written_at=None)
    lines = _pass(home=home, now=NOW)
    assert "LOGIN lifetime cap: not yet measured" in lines
    assert not [line for line in lines if line.startswith("WARN login")]


def test_a_login_approaching_the_measured_cap_is_warned_and_a_younger_one_is_not(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAP_ENV, str(28 * 24))
    monkeypatch.delenv(LEAD_ENV, raising=False)
    home = _home(tmp_path=tmp_path)
    _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW - 26 * DAY - 3600, written_at=None)
    _record(home=home, tmp_path=tmp_path, account=ACTIVE, now=NOW - 25 * DAY, written_at=None)
    lines = _pass(home=home, now=NOW)
    warned = [line for line in lines if line.startswith("WARN login")]
    assert len(warned) == 1
    assert OTHER in warned[0]
    assert "approaching its lifetime cap" in warned[0]
    assert "LOGIN lifetime cap: 28d 0h, warning lead 2d 0h" in lines


def test_a_first_seen_age_is_a_lower_bound_and_still_warns(*, tmp_path: Path) -> None:
    records: dict[str, object] = {"accounts": {}, "holds": {}}
    _ = note_first_seen(records=records, name=ACTIVE, now=NOW - 27 * DAY)
    settings = lifetime_settings(environ={CAP_ENV: "672", LEAD_ENV: "48"})
    lines = login_report_lines(records=records, names=(ACTIVE,), now=NOW, settings=settings)
    assert any("lower bound" in line and "(first-seen)" in line for line in lines)
    assert any(line.startswith("WARN login") and ACTIVE in line for line in lines)
    assert "age at least 27d 0h" in lines[1]


def test_the_cap_settings_default_unset_and_reject_nonsense() -> None:
    unset = lifetime_settings(environ={})
    assert unset.cap_s is None
    assert unset.lead_s == 48 * 3600.0
    assert unset.problem is None
    for bad in ("soon", "0", "-5", "nan"):
        settings = lifetime_settings(environ={CAP_ENV: bad})
        assert settings.cap_s is None
        assert settings.problem is not None
    odd_lead = lifetime_settings(environ={CAP_ENV: "100", LEAD_ENV: "x"})
    assert odd_lead.cap_s == 100 * 3600.0
    assert odd_lead.lead_s == 48 * 3600.0
    assert odd_lead.problem is not None
    lines = login_report_lines(
        records={"accounts": {}, "holds": {}}, names=(), now=NOW, settings=odd_lead
    )
    assert any("invalid" in line for line in lines)


def test_an_account_with_no_record_yet_is_named_in_the_report() -> None:
    lines = login_report_lines(
        records={"accounts": {}, "holds": {}},
        names=(ACTIVE,),
        now=NOW,
        settings=lifetime_settings(environ={}),
    )
    assert f"LOGIN {ACTIVE}: no login record yet" in lines


# --- Retention -----------------------------------------------------------------


def test_past_logins_are_kept_for_at_least_a_year_and_pruned_after_the_retention() -> None:
    assert RETENTION_DAYS >= 365
    records: dict[str, object] = {"accounts": {}, "holds": {}}
    record_login(records=records, name=OTHER, minted_at=NOW, source="file write time", now=NOW)
    for index in range(3):
        age_days = (RETENTION_DAYS + 10, 366, 5)[index]
        record_login(
            records=records,
            name=OTHER,
            minted_at=NOW,
            source="file write time",
            now=NOW - age_days * DAY,
        )
    record_login(records=records, name=OTHER, minted_at=NOW, source="command time", now=NOW)
    prune_records(records=records, now=NOW)
    past = records["accounts"][OTHER]["past"]  # type: ignore[index]
    ends = sorted(item["ended_at"] for item in past)
    assert len(ends) == 3
    assert all(NOW - end <= RETENTION_DAYS * DAY for end in ends)
    assert any(NOW - end >= 366 * DAY for end in ends)


# --- Login records never influence eligibility or ranking ---------------------


def test_login_records_do_not_change_the_rotation_decision(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAP_ENV, "100")
    plain = _home(tmp_path=tmp_path / "plain")
    aged = _home(tmp_path=tmp_path / "aged")
    _record(
        home=aged, tmp_path=tmp_path / "aged", account=OTHER, now=NOW - 90 * DAY, written_at=None
    )
    _record(
        home=aged, tmp_path=tmp_path / "aged", account=ACTIVE, now=NOW - 1 * DAY, written_at=None
    )
    base = _pass(home=plain, now=NOW, active_five=10.0)
    with_records = _pass(home=aged, now=NOW, active_five=10.0)
    assert [line for line in base if not line.startswith(("LOGIN", "WARN login"))] == [
        line for line in with_records if not line.startswith(("LOGIN", "WARN login"))
    ]
    assert [line for line in with_records if line.startswith("WARN login")]
    assert not [line for line in base if line.startswith("WARN login")]
    assert _login_lines(lines=base)


# --- Failure paths and the default output sink --------------------------------


def test_a_store_that_cannot_be_read_is_a_problem_not_an_empty_store(*, tmp_path: Path) -> None:
    path = tmp_path / "store"
    path.mkdir()
    loaded = load_records(path=path)
    assert loaded.problem is not None
    assert loaded.records == {"accounts": {}, "holds": {}}


def test_record_login_reports_a_state_directory_it_cannot_create(*, tmp_path: Path) -> None:
    home = _home(tmp_path=tmp_path)
    _ = (home / ".local/state").write_text("a file where a directory must be", encoding="utf-8")
    code, out = _record(home=home, tmp_path=tmp_path, account=OTHER, now=NOW, written_at=NOW)
    assert code == 2
    assert out[-1].startswith("FAIL could not record the login")


def test_record_login_writes_to_standard_output_by_default(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = _home(tmp_path=tmp_path)
    config = _login_dir(tmp_path=tmp_path)
    assert main(argv=[OTHER, "--config-dir", str(config)], home=home, now=NOW) == 0
    assert capsys.readouterr().out.startswith(f"OK record-login {OTHER}:")

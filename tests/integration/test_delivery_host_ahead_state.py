"""Integration coverage for the host-ahead delivery state and malformed host counters."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _sequence_sent(*, program: str) -> int:
    push = importlib.import_module("caam_delivery_push")
    call = program.removeprefix(push.APPLY_SCRIPT).strip()
    return int(
        json.loads(ast.literal_eval(call.removeprefix("main(").removesuffix(")")))["sequence"]
    )


def test_host_ahead_is_shown_without_failure_and_retried(*, tmp_path: Path) -> None:
    """Scenarios: a host ahead is shown as ahead, not failed; it is never exempted from retry."""
    push = importlib.import_module("caam_delivery_push")
    service = importlib.import_module("caam_delivery_service")
    status = importlib.import_module("caam_delivery_push_status")
    delivery = service.Delivery(sequence=31, account_id="account", identity={}, oauth={})
    hosts = tmp_path / push.HOSTS_FILE
    hosts.parent.mkdir(parents=True)
    _ = hosts.write_text("ahead user@ahead linux\n", encoding="utf-8")
    counter = tmp_path / push.STATE_DIR / "delivery-sequence.json"
    _ = counter.write_text(json.dumps({"sequence": 31}), encoding="utf-8")

    outcomes = push.push_due(
        home=tmp_path,
        delivery=delivery,
        now=100.0,
        run=lambda **_: (0, "stale-sequence 31 host-applied 40"),
    )

    assert outcomes == {"ahead": "stale-sequence 31 host-applied 40"}
    entry = push.load_state(home=tmp_path)["ahead"]
    assert entry["state"] == "ahead"
    assert entry["host_applied_sequence"] == 40
    assert "last_error" not in entry and "last_success" not in entry
    row = next(
        line
        for line in status.status_lines(home=tmp_path, now=101.0, reissue_available=True)
        if line.startswith("ahead  ")
    )
    assert " ahead " in row and "host-applied 40" in row
    settings = push.load_config(home=tmp_path)
    retry = float(settings["retry_s"])
    assert not push._due(entry=entry, sequence=31, now=100.0 + retry - 1, settings=settings)
    assert push._due(entry=entry, sequence=31, now=100.0 + retry, settings=settings)


def test_host_ahead_advances_the_counter_and_reissues_to_every_host(*, tmp_path: Path) -> None:
    """Scenario: A host ahead moves the sequence forward, never the host back."""
    entry = importlib.import_module("caam_delivery_push_entry")
    push = importlib.import_module("caam_delivery_push")
    service = importlib.import_module("caam_delivery_service")
    credentials = tmp_path / ".claude/.credentials.json"
    credentials.parent.mkdir(parents=True)
    _ = credentials.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "token", "expiresAt": 9_999_999_999_000}}),
        encoding="utf-8",
    )
    _ = (tmp_path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"accountUuid": "account"}, "userID": "user"}),
        encoding="utf-8",
    )
    counter = tmp_path / push.STATE_DIR / "delivery-sequence.json"
    counter.parent.mkdir(parents=True)
    _ = counter.write_text(json.dumps({"sequence": 31}), encoding="utf-8")
    _ = (tmp_path / push.HOSTS_FILE).write_text(
        "first user@first linux\nsecond user@second linux\n", encoding="utf-8"
    )
    applied = {"user@first": 40, "user@second": 40}
    sent: list[tuple[str, int]] = []

    def run(*, target: str, program: str, **_: object) -> tuple[int, str]:
        sequence = _sequence_sent(program=program)
        sent.append((target, sequence))
        if sequence <= applied[target]:
            return 0, f"stale-sequence {sequence} host-applied {applied[target]}"
        applied[target] = sequence
        return 0, f"applied {sequence}"

    loop = entry.PushLoop(
        last=service.Delivery(
            sequence=31,
            account_id="account",
            identity={"oauthAccount": {"accountUuid": "account"}, "userID": "user"},
            oauth={"accessToken": "token", "expiresAt": 9_999_999_999_000},
        )
    )
    entry.run_once(
        home=tmp_path,
        now=100.0,
        loop=loop,
        confirm=lambda **_: "account",
        run=run,
        start=lambda **_: None,
    )

    assert sent == [
        ("user@first", 31),
        ("user@second", 31),
        ("user@first", 41),
        ("user@second", 41),
    ]
    assert json.loads(counter.read_text(encoding="utf-8")) == {"sequence": 41}
    assert applied == {"user@first": 41, "user@second": 41}


@pytest.mark.parametrize("saved", [None, "", "not-a-number"])
def test_apply_treats_missing_empty_or_malformed_sequence_as_zero(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    saved: str | None,
) -> None:
    """Scenario: A corrupt applied-sequence file reads as zero."""
    apply = importlib.import_module("caam_delivery_apply_script")
    home = tmp_path / ("missing" if saved is None else saved or "empty")
    sequence = home / ".claude/.caam-delivery-sequence"
    sequence.parent.mkdir(parents=True)
    if saved is not None:
        _ = sequence.write_text(saved, encoding="utf-8")
    payload = json.dumps(
        {
            "sequence": 5,
            "account_id": "account",
            "identity": {"oauthAccount": {"accountUuid": "account"}, "userID": "user"},
            "oauth": {"accessToken": "token"},
        }
    )
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(SystemExit) as stopped:
        exec(  # noqa: S102
            compile(apply.apply_program(payload=payload), "<apply>", "exec"),
            {"__name__": "__main__"},
        )

    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == "applied 5"
    assert sequence.read_text(encoding="utf-8") == "5"

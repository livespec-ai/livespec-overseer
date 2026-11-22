"""Integration coverage for advancing a delivery counter past hosts already ahead."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path


def _write(*, path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(body), encoding="utf-8")


def _sequence_sent(*, program: str) -> int:
    push = importlib.import_module("caam_delivery_push")
    assert program.startswith(push.APPLY_SCRIPT)
    call = program[len(push.APPLY_SCRIPT) :].strip()
    assert call.startswith("main(") and call.endswith(")")
    payload = ast.literal_eval(call[len("main(") : -1])
    return int(json.loads(payload)["sequence"])


def test_a_new_role_holder_moves_its_counter_past_hosts_already_ahead(*, tmp_path: Path) -> None:
    """Scenario: A host ahead moves the sequence forward, never the host back."""
    entry = importlib.import_module("caam_delivery_push_entry")
    push = importlib.import_module("caam_delivery_push")
    service = importlib.import_module("caam_delivery_service")
    _write(
        path=tmp_path / ".claude/.credentials.json",
        body={
            "claudeAiOauth": {
                "accessToken": "access-token",
                "expiresAt": 9_999_999_999_000,
                "refreshToken": "role-holder-only",
            }
        },
    )
    _write(
        path=tmp_path / ".claude.json",
        body={"oauthAccount": {"accountUuid": "account-a"}, "userID": "user-a"},
    )
    counter = tmp_path / push.STATE_DIR / "delivery-sequence.json"
    _write(path=counter, body={"sequence": 83})
    hosts = tmp_path / push.HOSTS_FILE
    hosts.parent.mkdir(parents=True, exist_ok=True)
    _ = hosts.write_text("first user@first linux\nsecond user@second linux\n", encoding="utf-8")

    applied = {"user@first": 84, "user@second": 84}
    sent: list[tuple[str, int]] = []

    def run(*, target: str, program: str, **_: object) -> tuple[int, str]:
        sequence = _sequence_sent(program=program)
        sent.append((target, sequence))
        if sequence <= applied[target]:
            return 0, f"stale-sequence {sequence} host-applied {applied[target]}"
        applied[target] = sequence
        return 0, f"applied {sequence}"

    current = service.Delivery(
        sequence=83,
        account_id="account-a",
        identity={"oauthAccount": {"accountUuid": "account-a"}, "userID": "user-a"},
        oauth={"accessToken": "access-token", "expiresAt": 9_999_999_999_000},
    )
    loop = entry.PushLoop(last=current)
    entry.run_once(
        home=tmp_path,
        now=100.0,
        loop=loop,
        confirm=lambda **_: "account-a",
        run=run,
        start=lambda **_: None,
    )

    assert sent == [
        ("user@first", 83),
        ("user@second", 83),
        ("user@first", 85),
        ("user@second", 85),
    ]
    assert json.loads(counter.read_text(encoding="utf-8")) == {"sequence": 85}
    assert applied == {"user@first": 85, "user@second": 85}

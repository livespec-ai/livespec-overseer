"""`record-login`: store a freshly completed login and record it (spec.md **Login records.**).

    record-login <account> --config-dir <dir>

Takes the credential from `<dir>/.credentials.json`, the configuration directory
in which the operator has just completed a login for `<account>`, and stores it as
that account's stored credential in the vault the rotation operation already uses.
It records the login with mint time `recorded` (the credential file's write time
where readable, otherwise the time the command ran, and it says which), ends the
account's previous login as `replaced` unless it already ended, and releases any
login hold on the account. It NEVER writes the live credential. Output names
accounts, paths and times only; no credential value is ever printed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Protocol, cast

import streams
from caam_anthropic_finish import LineWriter
from caam_login_records import (
    END_DARK,
    current_login,
    load_records,
    locked,
    record_login,
    records_path,
    save_records,
)
from caam_login_report import stamp
from caam_profile_state import caam_vault, profile_names

__all__: list[str] = ["credential_write_time", "main"]

_CREDENTIAL = ".credentials.json"
_ARGC = 3
_USAGE = "FAIL usage: record-login <account> --config-dir <dir>"


class WriteTime(Protocol):
    def __call__(self, *, path: Path) -> float | None: ...


def credential_write_time(*, path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _looks_like_credential(*, body: bytes) -> bool:
    try:
        parsed = cast(object, json.loads(body))
    except ValueError:
        return False
    return isinstance(parsed, dict) and isinstance(
        cast(dict[str, object], parsed).get("claudeAiOauth"), dict
    )


def _store_credential(*, body: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp")
    _ = tmp_path.write_bytes(body)
    tmp_path.chmod(0o600)
    _ = tmp_path.replace(target)


def _parse(*, argv: list[str]) -> tuple[str, Path] | None:
    if len(argv) != _ARGC or argv[1] != "--config-dir" or argv[0].startswith(("-", "_")):
        return None
    return argv[0], Path(argv[2])


def main(
    *,
    argv: list[str] | None = None,
    home: Path | None = None,
    now: float | None = None,
    stdout: LineWriter | None = None,
    write_time: WriteTime = credential_write_time,
) -> int:
    say = _stdout_line if stdout is None else stdout
    parsed = _parse(argv=list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        say(_USAGE)
        return 2
    account, config_dir = parsed
    run_home = Path.home() if home is None else home
    vault = caam_vault(home=run_home)
    if account not in profile_names(vault=vault, active_name=None):
        say(f"FAIL {account} is not a managed account in {vault}")
        return 2
    source = config_dir / _CREDENTIAL
    try:
        body = source.read_bytes()
    except OSError as exc:
        say(f"FAIL cannot read the credential in {config_dir}: {type(exc).__name__}")
        return 2
    if not _looks_like_credential(body=body):
        say(f"FAIL {source} does not hold a Claude credential; nothing changed")
        return 2
    return _record(
        account=account,
        body=body,
        written=write_time(path=source),
        home=run_home,
        now=time.time() if now is None else now,
        say=say,
    )


def _record(
    *, account: str, body: bytes, written: float | None, home: Path, now: float, say: LineWriter
) -> int:
    path = records_path(home=home)
    minted = now if written is None else written
    basis = "command time" if written is None else "file write time"
    try:
        with locked(path=path):
            loaded = load_records(path=path)
            if loaded.problem is not None:
                say(f"FAIL login records unavailable: {loaded.problem}; nothing changed")
                return 2
            records = loaded.records
            held = account in cast(dict[str, object], records["holds"])
            replaced = current_login(records=records, name=account) is not None
            _store_credential(body=body, target=caam_vault(home=home) / account / _CREDENTIAL)
            record_login(records=records, name=account, minted_at=minted, source=basis, now=now)
            save_records(path=path, records=records)
    except OSError as exc:
        say(f"FAIL could not record the login: {type(exc).__name__}: {exc}")
        return 2
    say(
        f"OK record-login {account}: stored credential recorded, mint time "
        f"{stamp(at=minted)} (recorded, taken from the {basis})"
    )
    if replaced:
        say(f"previous login for {account} ended as replaced")
    if held:
        say(f"login hold released for {account} ({END_DARK} login replaced)")
    return 0


class _StdoutLine:
    def __call__(self, line: str) -> None:
        streams.write_stdout(text=line + "\n")


_stdout_line = _StdoutLine()

"""The durable login record store: one file, per managed account.

A LOGIN is one provider sign-in for an account (spec.md "Account rotation and
quota supervision", **Login records.**). The store keeps each account's current
login and its past logins. A login carries its mint time and how that time is
known (`recorded` at the login, or `first-seen` for an account that never had a
record, a lower bound only); once ended it carries an end time and an end cause,
`dark` or `replaced`. A login judged dark also leaves a LOGIN HOLD, which only
the `record-login` command releases.

The file holds times, account names and short evidence strings. It never holds
credential material. Login records are read by the report only: they play no part
in eligibility or ranking.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

__all__: list[str] = [
    "BASIS_FIRST_SEEN",
    "BASIS_RECORDED",
    "END_DARK",
    "END_REPLACED",
    "RECORDS_REL",
    "RETENTION_DAYS",
    "RecordsLoad",
    "current_login",
    "end_login",
    "load_records",
    "locked",
    "note_first_seen",
    "prune_records",
    "record_login",
    "records_path",
    "save_records",
]

RECORDS_REL: Final = Path(".local/state/caam-usage-rotate/login-records.json")
BASIS_RECORDED: Final = "recorded"
BASIS_FIRST_SEEN: Final = "first-seen"
END_DARK: Final = "dark"
END_REPLACED: Final = "replaced"
# Past logins must be kept at least 365 days; twice that leaves room for a cap
# derived from a year of logins.
RETENTION_DAYS: Final = 730
_DAY_S: Final = 86400.0

Records = dict[str, object]


@dataclass(frozen=True, kw_only=True)
class RecordsLoad:
    """The store as read, or why it could not be read."""

    records: Records
    problem: str | None


def records_path(*, home: Path) -> Path:
    return home / RECORDS_REL


def _empty() -> Records:
    return {"accounts": {}, "holds": {}}


def load_records(*, path: Path) -> RecordsLoad:
    """An absent file is an empty store; an unreadable or malformed one is a problem.

    A malformed store must never read as empty, or every account would be given
    a fresh first-seen record and the history would be overwritten.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RecordsLoad(records=_empty(), problem=None)
    except OSError as exc:
        return RecordsLoad(records=_empty(), problem=f"{path} is unreadable: {exc}")
    try:
        parsed = cast(object, json.loads(text))
    except ValueError:
        return RecordsLoad(records=_empty(), problem=f"{path} is not valid JSON")
    if not (
        isinstance(parsed, dict)
        and isinstance(cast(dict[str, object], parsed).get("accounts"), dict)
        and isinstance(cast(dict[str, object], parsed).get("holds"), dict)
    ):
        return RecordsLoad(records=_empty(), problem=f"{path} is not a login record store")
    return RecordsLoad(records=cast(Records, parsed), problem=None)


def save_records(*, path: Path, records: Records) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    _ = tmp_path.write_text(json.dumps(records, indent=1, sort_keys=True), encoding="utf-8")
    tmp_path.chmod(0o600)
    _ = tmp_path.replace(path)


@contextmanager
def locked(*, path: Path) -> Iterator[None]:
    """Serialize read-modify-write of the store between a pass and the command."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path.with_name(path.name + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _accounts(*, records: Records) -> dict[str, dict[str, object]]:
    return cast(dict[str, dict[str, object]], records["accounts"])


def _holds(*, records: Records) -> dict[str, object]:
    return cast(dict[str, object], records["holds"])


def _entry(*, records: Records, name: str) -> dict[str, object]:
    return _accounts(records=records).setdefault(name, {"current": None, "past": []})


def current_login(*, records: Records, name: str) -> dict[str, object] | None:
    entry = _accounts(records=records).get(name)
    return None if entry is None else cast("dict[str, object] | None", entry["current"])


def note_first_seen(*, records: Records, name: str, now: float) -> bool:
    """Give an account that NEVER had a record a first-seen one; never to an ended login."""
    if name in _accounts(records=records):
        return False
    _entry(records=records, name=name)["current"] = {
        "minted_at": now,
        "basis": BASIS_FIRST_SEEN,
        "source": "pass time",
    }
    return True


def record_login(*, records: Records, name: str, minted_at: float, source: str, now: float) -> None:
    """Record a login the operator completed: end the previous one, release the hold."""
    _ = end_login(records=records, name=name, now=now, cause=END_REPLACED, evidence="", hold=False)
    _entry(records=records, name=name)["current"] = {
        "minted_at": minted_at,
        "basis": BASIS_RECORDED,
        "source": source,
    }
    _ = _holds(records=records).pop(name, None)


def end_login(
    *, records: Records, name: str, now: float, cause: str, evidence: str, hold: bool = True
) -> bool:
    """End the current login. Returns False where there was none to end."""
    login = current_login(records=records, name=name)
    if login is None:
        return False
    ended: dict[str, object] = {**login, "ended_at": now, "end_cause": cause}
    if evidence:
        ended["evidence"] = evidence
    entry = _entry(records=records, name=name)
    cast(list[object], entry["past"]).append(ended)
    entry["current"] = None
    if hold and cause == END_DARK:
        _holds(records=records)[name] = {"since": now, "evidence": evidence}
    return True


def prune_records(*, records: Records, now: float) -> None:
    horizon = now - RETENTION_DAYS * _DAY_S
    for entry in _accounts(records=records).values():
        past = cast(list[dict[str, object]], entry["past"])
        entry["past"] = [item for item in past if cast(float, item["ended_at"]) >= horizon]

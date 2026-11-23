"""Judging the active account's login dark, and remembering it.

A login is DARK when the provider will no longer accept it and no refresh can
restore it. Two conditions judge it, and a pass judges only the ACTIVE account:

  (a) a tracked session's transcript records the provider refusing the login as
      unrenewable or revoked, attributed to the account by the usage-limit
      refusal clause's own conditions and recorded after the login's recorded
      mint time (`caam_login_refusals`). Sends no request.
  (b) the operation's own read-only reading of the active account is refused as
      unauthenticated while the live credential's access token has not reached
      its expiry; the live credential, re-read, is byte-identical to the one
      that was refused; and the NEXT pass is refused the same way with that
      same credential still unchanged. ONE refused reading never judges a login
      dark, because a refresh on the role holder revokes the previous access
      token at once and can race the reading. It uses only the reading
      Observation already makes.

An access token that has merely reached its expiry is NOT dark, because the
agent's own refresh may restore it: a locally expired token is never a refusal
here, since the reading it blocked was never sent.

The credential is compared by a SHA-256 of the file's bytes, which is all that
is stored between passes; no credential value is ever kept, printed or logged.
A judgement ends the account's current login as `dark` and leaves the login
hold, both in the durable store, under the store's lock.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, cast

from caam_decision import ProfileUsage
from caam_login_hold import CONDITION_A, CONDITION_B, LoginHold, read_holds
from caam_login_records import (
    BASIS_RECORDED,
    END_DARK,
    Records,
    current_login,
    end_login,
    load_records,
    locked,
    note_condition,
    note_first_seen,
    records_path,
    save_records,
    suspects,
)
from caam_login_refusals import attributed_login_refusal
from caam_profile_state import live_creds_path
from caam_profiles import ActiveIdentity
from caam_refusal_store import activation_of
from caam_refusals import TrackedSession
from caam_usage import read_creds

__all__: list[str] = ["DarkObservation", "credential_fingerprint", "observe_dark_logins"]

_UNAUTHENTICATED_RE: Final = re.compile(
    r"HTTP 401\b.*\bauthentication_error\b|authenticat|unauthori[sz]ed|"
    r"invalid (bearer|access|oauth)|oauth (access )?token",
    re.IGNORECASE,
)
_SUSPECT_MAX_AGE_S: Final = 240 * 60


@dataclass(frozen=True, kw_only=True)
class DarkObservation:
    """Everything one pass hands the judgement, carried as one value."""

    home: Path
    state: dict[str, object]
    active: ActiveIdentity
    profiles: tuple[ProfileUsage, ...]
    live_before: str | None
    sessions: Callable[[], tuple[TrackedSession, ...]]
    now: float
    dry_run: bool


def credential_fingerprint(*, path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _stamp(*, at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def observe_dark_logins(*, observation: DarkObservation) -> dict[str, LoginHold]:
    """Judge the active login, persist what that changes, and return every hold.

    The holds come back from the DURABLE store on every pass, which is what keeps
    a restart from returning the fleet to a dark login. An unreadable store yields
    none: the report already says so, and the pass must not be stopped by it.
    """
    path = records_path(home=observation.home)
    try:
        with locked(path=path):
            loaded = load_records(path=path)
            if loaded.problem is not None:
                return {}
            records = loaded.records
            before = json.dumps(records, sort_keys=True)
            if observation.active.profile not in read_holds(records=records):
                _judge(observation=observation, records=records)
            if not observation.dry_run and json.dumps(records, sort_keys=True) != before:
                save_records(path=path, records=records)
            return read_holds(records=records)
    except OSError:
        return {}


def _judge(*, observation: DarkObservation, records: Records) -> None:
    name = observation.active.profile
    evidence = _condition_a(observation=observation, records=records)
    if evidence is not None:
        _dark(observation=observation, records=records, condition=CONDITION_A, evidence=evidence)
        return
    evidence = _condition_b(observation=observation, records=records)
    if evidence is not None:
        _dark(observation=observation, records=records, condition=CONDITION_B, evidence=evidence)
        return
    pending = suspects(records=records)
    for other in [key for key in pending if key != name]:
        del pending[other]


def _dark(*, observation: DarkObservation, records: Records, condition: str, evidence: str) -> None:
    name = observation.active.profile
    _ = note_first_seen(records=records, name=name, now=observation.now)
    _ = end_login(
        records=records,
        name=name,
        now=observation.now,
        cause=END_DARK,
        evidence=evidence,
    )
    note_condition(records=records, name=name, condition=condition)
    _ = suspects(records=records).pop(name, None)


def _condition_a(*, observation: DarkObservation, records: Records) -> str | None:
    name = observation.active.profile
    activated = activation_of(state=observation.state, account=name)
    if activated is None:
        return None
    login = current_login(records=records, name=name)
    minted = (
        cast(float, login["minted_at"])
        if login is not None and login.get("basis") == BASIS_RECORDED
        else activated
    )
    refusal = attributed_login_refusal(
        sessions=observation.sessions(),
        home=observation.home,
        account_uuid=observation.active.account_uuid,
        after=max(activated, minted),
    )
    if refusal is None:
        return None
    return (
        f"a tracked session recorded the provider refusing the login ({refusal.kind}) "
        f"at {_stamp(at=refusal.recorded_at)}"
    )


def _refused_unauthenticated(*, observation: DarkObservation) -> bool:
    row = next((p for p in observation.profiles if p.name == observation.active.profile), None)
    failure = None if row is None else row.read_failure
    if failure is None or failure.startswith(("token expired", "no token")):
        return False
    _, expires_at = read_creds(path=live_creds_path(home=observation.home))
    if expires_at is None or expires_at <= observation.now:
        return False
    return _UNAUTHENTICATED_RE.search(failure) is not None


def _condition_b(*, observation: DarkObservation, records: Records) -> str | None:
    name = observation.active.profile
    pending = suspects(records=records)
    fingerprint = credential_fingerprint(path=live_creds_path(home=observation.home))
    unchanged = fingerprint is not None and fingerprint == observation.live_before
    first = cast("dict[str, object] | None", pending.get(name))
    if first is not None and _suspect_expired(first=first, now=observation.now):
        _ = pending.pop(name, None)
        first = None
    if not (unchanged and _refused_unauthenticated(observation=observation)):
        if _reading_is_informative(observation=observation):
            _ = pending.pop(name, None)
        return None
    if first is None or first.get("fingerprint") != fingerprint:
        pending[name] = {"fingerprint": fingerprint, "first_refused_at": observation.now}
        return None
    return (
        "the reading was refused as unauthenticated at "
        f"{_stamp(at=cast(float, first['first_refused_at']))} and again at "
        f"{_stamp(at=observation.now)} with the live credential unchanged and unexpired"
    )


def _reading_is_informative(*, observation: DarkObservation) -> bool:
    row = next((p for p in observation.profiles if p.name == observation.active.profile), None)
    return row is not None and row.read_failure is None


def _suspect_expired(*, first: dict[str, object], now: float) -> bool:
    return now - cast(float, first["first_refused_at"]) > _SUSPECT_MAX_AGE_S

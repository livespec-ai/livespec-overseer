"""Condition (a) of the dark-login judgement: a refusal of the LOGIN itself.

A tracked session's transcript can record the provider refusing an account's
login as unrenewable or revoked -- the refusal that states the login reached its
time limit and cannot be renewed, for one. This reads those records and sends NO
request: every fact is on disk already, written by a session that had made its
own.

TWO REFUSAL KINDS ARE KEPT APART rather than folded into one cap signal, because
what is measured about them differs: the time-limit wording names a lifetime,
while a revocation names no age at all. A refusal that says a refresh merely
FAILED is deliberately NOT matched: a refresh can fail for a transient reason,
and judging a login dark on it would hold a healthy account until an operator
re-recorded a login.

Attribution to the active account is the usage-limit refusal clause's own
conditions, every one failing closed: the session authenticates with the
host-wide live credential, a named identity is the active account's, the record
post-dates the moment the account was last observed to become active, and -- for
an account whose current login's mint time is `recorded` -- post-dates that mint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from caam_refusals import (
    TrackedSession,
    api_error_line,
    line_account,
    line_recorded_at,
    session_transcript_lines,
)

__all__: list[str] = [
    "KIND_LIFETIME_CAP",
    "KIND_REVOKED",
    "LoginRefusal",
    "attributed_login_refusal",
]

KIND_LIFETIME_CAP: Final = "lifetime-cap"
KIND_REVOKED: Final = "revoked"
_LIVE_CONFIG_REL: Final = ".claude"
_TIME_LIMIT_RE: Final = re.compile(
    r"login reached its time limit|reached its time limit and cannot be renewed|"
    r"login cannot be renewed",
    re.IGNORECASE,
)
_REVOKED_RE: Final = re.compile(
    r"(login|session|oauth token|refresh token) (has been |was )?revoked", re.IGNORECASE
)


@dataclass(frozen=True, kw_only=True)
class LoginRefusal:
    """One provider refusal of the login, with the kind of refusal it was."""

    recorded_at: float
    kind: str
    account: str | None = None


def _kind(*, line: str) -> str | None:
    if _TIME_LIMIT_RE.search(line) is not None:
        return KIND_LIFETIME_CAP
    if _REVOKED_RE.search(line) is not None:
        return KIND_REVOKED
    return None


def session_login_refusals(*, session: TrackedSession) -> tuple[LoginRefusal, ...]:
    refusals: list[LoginRefusal] = []
    for line in session_transcript_lines(session=session):
        kind = _kind(line=line) if api_error_line(line=line) else None
        at = None if kind is None else line_recorded_at(line=line)
        if kind is not None and at is not None:
            refusals.append(
                LoginRefusal(recorded_at=at, kind=kind, account=line_account(line=line))
            )
    return tuple(refusals)


def attributed_login_refusal(
    *,
    sessions: tuple[TrackedSession, ...],
    home: Path,
    account_uuid: str | None,
    after: float,
) -> LoginRefusal | None:
    """The most recent refusal attributable to the active account, or None.

    `after` is the latest of the moment the account was observed to become active
    and its recorded mint time; a refusal recorded at or before it is not the
    active login's.
    """
    found = [
        refusal
        for session in sessions
        if session.config_dir == home / _LIVE_CONFIG_REL
        for refusal in session_login_refusals(session=session)
        if refusal.recorded_at > after and refusal.account in (None, account_uuid)
    ]
    return max(found, key=lambda refusal: refusal.recorded_at, default=None)

"""A LOGIN HOLD as the rest of the operation sees it, and how it enters the rows.

The hold lives in the durable login record store (`caam_login_records`), so it
survives a restart. This module reads it back as values, and applies it to the
polled rows in the one place every later rule already looks.

An account that is login-held MUST NOT count as live-verified. "Live-verified"
is read off a row's source, so the held row's source is rewritten and its usage
withdrawn: every rule after it -- candidacy, the weekly reserve's count of
accounts above it, the capacity test, the report's unverified note -- then
excludes it without being told about login holds at all. The held ACTIVE
account's headroom is taken as zero on every dimension rather than withdrawn,
because the decision needs a reading to leave.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final, cast

from caam_decision import ProfileUsage, UsageRecord
from caam_login_records import Records

__all__: list[str] = [
    "CONDITION_A",
    "CONDITION_B",
    "LOGIN_HELD_SOURCE",
    "LoginHold",
    "apply_login_holds",
    "read_holds",
    "zero_usage",
]

CONDITION_A: Final = "a"
CONDITION_B: Final = "b"
LOGIN_HELD_SOURCE: Final = "login-held"


@dataclass(frozen=True, kw_only=True)
class LoginHold:
    """Why and since when an account's login is judged dark."""

    account: str
    since: float
    condition: str | None
    evidence: str


def read_holds(*, records: Records) -> dict[str, LoginHold]:
    held = cast(dict[str, dict[str, object]], records["holds"])
    return {
        name: LoginHold(
            account=name,
            since=cast(float, entry["since"]),
            condition=cast("str | None", entry.get("condition")),
            evidence=cast(str, entry.get("evidence", "")),
        )
        for name, entry in held.items()
    }


def zero_usage() -> UsageRecord:
    """Headroom of nothing on every dimension, which is what a dark login has."""
    return UsageRecord(
        five_hour_remaining=0.0,
        seven_day_remaining=0.0,
        five_hour_resets_at=None,
        seven_day_resets_at=None,
        fable_remaining=0.0,
        fable_resets_at=None,
    )


def _no_headroom(*, usage: UsageRecord | None) -> UsageRecord:
    """The reading with nothing left on any dimension, keeping its reset instants."""
    if usage is None:
        return zero_usage()
    return replace(
        usage,
        five_hour_remaining=0.0,
        seven_day_remaining=0.0,
        fable_remaining=None if usage.fable_remaining is None else 0.0,
    )


def apply_login_holds(
    *,
    profiles: tuple[ProfileUsage, ...],
    holds: Mapping[str, LoginHold],
    active_name: str,
) -> tuple[ProfileUsage, ...]:
    return tuple(
        replace(
            profile,
            source=LOGIN_HELD_SOURCE,
            usage=_no_headroom(usage=profile.usage) if profile.name == active_name else None,
        )
        if profile.name in holds
        else profile
        for profile in profiles
    )

"""The loop's report of each account's login age, and the lifetime-cap warning.

spec.md **Login age and the lifetime cap.**: the report shows every managed
account's current login age and mint time, a lower bound when the mint time is
`first-seen`. The lifetime cap is unset by default, because no cap length has been
measured, and while it is unset the report says so and never warns. Once set, it
warns for every account whose current login age has reached the cap minus the
warning lead, a lower-bound age included. Nothing here reads or changes
eligibility or ranking.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, cast

from caam_login_records import BASIS_FIRST_SEEN, Records, current_login

__all__: list[str] = ["LifetimeSettings", "lifetime_settings", "login_report_lines", "stamp"]

CAP_ENV: Final = "CAAM_ROTATE_LOGIN_LIFETIME_CAP_HOURS"
LEAD_ENV: Final = "CAAM_ROTATE_LOGIN_WARNING_LEAD_HOURS"
_DEFAULT_LEAD_H: Final = 48.0
_HOUR_S: Final = 3600.0


@dataclass(frozen=True, kw_only=True)
class LifetimeSettings:
    cap_s: float | None
    lead_s: float
    problem: str | None


def _hours(*, raw: str) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def lifetime_settings(*, environ: Mapping[str, str]) -> LifetimeSettings:
    problems: list[str] = []
    cap_s: float | None = None
    lead_h = _DEFAULT_LEAD_H
    raw_cap = environ.get(CAP_ENV)
    if raw_cap is not None:
        cap_h = _hours(raw=raw_cap)
        cap_s = None if cap_h is None else cap_h * _HOUR_S
        if cap_h is None:
            problems.append(f"{CAP_ENV}={raw_cap!r}")
    raw_lead = environ.get(LEAD_ENV)
    if raw_lead is not None:
        parsed = _hours(raw=raw_lead)
        lead_h = _DEFAULT_LEAD_H if parsed is None else parsed
        if parsed is None:
            problems.append(f"{LEAD_ENV}={raw_lead!r}")
    return LifetimeSettings(
        cap_s=cap_s,
        lead_s=lead_h * _HOUR_S,
        problem=", ".join(problems) if problems else None,
    )


def _span(*, seconds: float) -> str:
    hours = int(max(seconds, 0.0) // _HOUR_S)
    return f"{hours // 24}d {hours % 24}h"


def stamp(*, at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cap_line(*, settings: LifetimeSettings) -> tuple[str, ...]:
    invalid = (
        ()
        if settings.problem is None
        else (f"LOGIN lifetime cap setting invalid ({settings.problem}); using the default",)
    )
    if settings.cap_s is None:
        return (*invalid, "LOGIN lifetime cap: not yet measured")
    return (
        *invalid,
        f"LOGIN lifetime cap: {_span(seconds=settings.cap_s)}, "
        f"warning lead {_span(seconds=settings.lead_s)}",
    )


def login_report_lines(
    *, records: Records, names: tuple[str, ...], now: float, settings: LifetimeSettings
) -> tuple[str, ...]:
    lines = list(_cap_line(settings=settings))
    accounts = cast(dict[str, dict[str, object]], records["accounts"])
    holds = cast(dict[str, object], records["holds"])
    for name in names:
        login = current_login(records=records, name=name)
        if login is None:
            lines.append(_ended_line(name=name, entry=accounts.get(name), held=name in holds))
            continue
        minted = cast(float, login["minted_at"])
        first_seen = login["basis"] == BASIS_FIRST_SEEN
        age = max(now - minted, 0.0)
        shown = (
            f"age at least {_span(seconds=age)} (lower bound)"
            if first_seen
            else (f"age {_span(seconds=age)}")
        )
        label = "first seen" if first_seen else "minted"
        lines.append(f"LOGIN {name}: {shown}, {label} {stamp(at=minted)} ({login['basis']})")
        if settings.cap_s is not None and age >= settings.cap_s - settings.lead_s:
            lines.append(
                f"WARN login lifetime cap: {name} login is approaching its lifetime cap "
                f"({shown}, cap {_span(seconds=settings.cap_s)})"
            )
    return tuple(lines)


def _ended_line(*, name: str, entry: dict[str, object] | None, held: bool) -> str:
    past = [] if entry is None else cast(list[dict[str, object]], entry["past"])
    if not past:
        return f"LOGIN {name}: no login record yet"
    last = past[-1]
    held_note = ", login-held" if held else ""
    return (
        f"LOGIN {name}: no current login (ended {last['end_cause']} at "
        f"{stamp(at=cast(float, last['ended_at']))}{held_note})"
    )

"""What a pass SAYS when a dark login governs it, in the operator's words.

The switch line names the dark login as the reason, states which of the two
conditions judged it, and states when. The condition reads from the durable
hold, so the line is the same on a pass that finds the hold on disk after a
restart as on the pass that judged it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final, cast

from caam_decision import ProfileUsage, UsageRecord
from caam_login_hold import CONDITION_A, CONDITION_B, LoginHold
from caam_rendering import until, with_reasons

__all__: list[str] = [
    "DARK_LOGIN_TRIGGER",
    "dark_login_hold_line",
    "dark_login_switch_line",
    "dark_login_trigger_line",
]

DARK_LOGIN_TRIGGER: Final = "dark-login"
_CONDITIONS: Final = {
    CONDITION_A: "condition (a), a refusal of the login recorded in a session transcript",
    CONDITION_B: "condition (b), two refused readings with the live credential unchanged",
}


def _stamp(*, at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _judged(*, hold: LoginHold) -> str:
    which = _CONDITIONS.get(hold.condition or "", "an earlier pass")
    return f"{hold.account}'s login was judged dark by {which} at {_stamp(at=hold.since)}"


def dark_login_trigger_line(*, hold: LoginHold) -> str:
    return f"trigger: dark login -- {_judged(hold=hold)} -- comparing candidates on seven_day"


def dark_login_switch_line(
    *, active_name: str, target: ProfileUsage, hold: LoginHold, now: float
) -> str:
    usage = cast(UsageRecord, target.usage)
    now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
    return (
        f"SWITCHED {active_name} -> {target.name} "
        f"(dark login: {_judged(hold=hold)}; target has "
        f"{usage.seven_day_remaining:.0f}% week left, resets in "
        f"{until(timestamp=usage.seven_day_resets_at, now=now_dt)})"
    )


def dark_login_hold_line(*, hold: LoginHold, cause: str, reasons: tuple[str, ...] = ()) -> str:
    return with_reasons(
        line=(
            f"hold: {hold.account}'s login is dark ({_judged(hold=hold)}) and no account "
            f"could be selected -- {cause}"
        ),
        reasons=reasons,
    )

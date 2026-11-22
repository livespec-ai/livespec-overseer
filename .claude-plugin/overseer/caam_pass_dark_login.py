"""Where a pass judges the active login dark and applies every login hold to its rows.

Judged AFTER the readings are settled and BEFORE the decision, because a dark
login is evidence about the account those readings describe and a hold changes
which rows the decision may trust. Returns the rows with every login hold applied
and the ACTIVE account's hold, which is what makes the dark-login trigger fire.
"""

from __future__ import annotations

from pathlib import Path

from caam_dark_login import DarkObservation, credential_fingerprint, observe_dark_logins
from caam_decide_context import DecisionContext
from caam_decision import ProfileUsage
from caam_login_hold import LoginHold, apply_login_holds
from caam_profile_state import live_creds_path
from caam_profiles import ActiveIdentity
from caam_refusals import TrackedSessionSource

__all__: list[str] = ["live_credential_fingerprint", "observe_pass_dark_logins"]


def live_credential_fingerprint(*, home: Path) -> str | None:
    """The live credential as it stands BEFORE the active account is read with it.

    The judgement needs the bytes that were refused, and compares them with a
    re-read taken after. A hash only; the credential itself is never kept.
    """
    return credential_fingerprint(path=live_creds_path(home=home))


def observe_pass_dark_logins(
    *,
    context: DecisionContext,
    active: ActiveIdentity,
    profiles: tuple[ProfileUsage, ...],
    live_before: str | None,
    source: TrackedSessionSource,
) -> tuple[tuple[ProfileUsage, ...], LoginHold | None]:
    holds = observe_dark_logins(
        observation=DarkObservation(
            home=context.home,
            state=context.state,
            active=active,
            profiles=profiles,
            live_before=live_before,
            sessions=lambda: source(home=context.home),
            now=context.now,
            dry_run=context.flags.dry_run,
        )
    )
    held = apply_login_holds(profiles=profiles, holds=holds, active_name=active.profile)
    return held, holds.get(active.profile)

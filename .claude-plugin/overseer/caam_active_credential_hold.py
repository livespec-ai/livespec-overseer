"""Terminal outcome for an active account whose live credential is unavailable."""

from __future__ import annotations

from caam_decision import ProfileUsage

__all__: list[str] = ["active_usage_read_outcome"]


def active_usage_read_outcome(
    *, active_name: str, profiles: tuple[ProfileUsage, ...]
) -> tuple[int, str]:
    """Return the successful credential hold or the ordinary unreadable-usage failure."""
    active = next(profile for profile in profiles if profile.name == active_name)
    if active.credential_expired:
        return (
            0,
            f"hold: live credential unavailable for active profile {active_name}: "
            f"{active.source.removeprefix('dark: ')}",
        )
    return 2, f"FAIL cannot read usage for active profile {active_name}"

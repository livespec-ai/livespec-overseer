"""Parse refusal observations the delivery channel forwarded from listed hosts.

The delivery channel's authentication names the host that delivered a record
(`caam_forwarded_refusal_intake` stamps it from the verified ssh session); the
record itself must name its account and carry only provider refusal text.  This
module admits no host state and makes no request.  Attribution applies the
active-account, activation, settling, and departed-account rules afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import jsonio
from caam_refusals import WINDOW_FIVE_HOUR, WINDOW_SEVEN_DAY, Refusal

__all__: list[str] = [
    "DELIVERY_HOSTS_KEY",
    "FORWARDED_REFUSALS_KEY",
    "ForwardedRefusal",
    "forwarded_refusals",
]

FORWARDED_REFUSALS_KEY: Final = "forwarded_refusals"
DELIVERY_HOSTS_KEY: Final = "delivery_hosts"
_WEEKLY_LIMIT_PHRASES: Final = (
    "weekly limit reached",
    "hit your weekly limit",
    "weekly usage limit",
)
_SHORT_LIMIT_PHRASES: Final = (
    "usage limit reached",
    "hit your session limit",
    "hit your usage limit",
    "rate_limit_error",
    "rate limit exceeded",
)
_AUTHENTICATION_ERROR_PHRASES: Final = (
    "authentication error",
    "unauthorized",
    "invalid api key",
    "expired credential",
    "revoked credential",
)
_EPOCH_MIN_DIGITS: Final = 9
_EPOCH_MAX_DIGITS: Final = 11
_RETRY_AFTER_MAX_DIGITS: Final = 6


@dataclass(frozen=True, kw_only=True)
class ForwardedRefusal:
    """One forwarding outcome, retaining its host for the operator report."""

    host: str
    refusal: Refusal | None
    ignored_reason: str | None = None


def forwarded_refusals(*, state: dict[str, object]) -> tuple[ForwardedRefusal, ...]:
    """The listed hosts' self-authenticated usage-limit refusals, failing closed."""
    listed = frozenset(
        value
        for value in jsonio.as_list(value=state.get(DELIVERY_HOSTS_KEY)) or []
        if isinstance(value, str)
    )
    return tuple(
        outcome
        for value in jsonio.as_list(value=state.get(FORWARDED_REFUSALS_KEY)) or []
        for record in (jsonio.as_object(value=value) or {},)
        for outcome in (_forwarded_refusal(record=record, listed=listed),)
    )


def _forwarded_refusal(*, record: dict[str, object], listed: frozenset[str]) -> ForwardedRefusal:
    host = record.get("host")
    authenticated_host = record.get("authenticated_host")
    account = record.get("account")
    recorded_at = jsonio.as_float(value=record.get("recorded_at"))
    message = record.get("provider_message")
    label = host if isinstance(host, str) else "unknown host"
    if not isinstance(host, str) or host not in listed:
        return ForwardedRefusal(host=label, refusal=None, ignored_reason="host is not listed")
    if authenticated_host != host:
        return ForwardedRefusal(
            host=host,
            refusal=None,
            ignored_reason="not authenticated as that host's own observation",
        )
    if not isinstance(account, str) or recorded_at is None or not isinstance(message, str):
        return ForwardedRefusal(host=host, refusal=None, ignored_reason="record is incomplete")
    window = _forwarded_window(message=message)
    if window is None:
        return ForwardedRefusal(
            host=host,
            refusal=None,
            ignored_reason="not a usage-limit refusal",
        )
    return ForwardedRefusal(
        host=host,
        refusal=Refusal(
            recorded_at=recorded_at,
            window=window,
            resets_at=_forwarded_reset(message=message, recorded_at=recorded_at),
            account=account,
        ),
    )


def _forwarded_window(*, message: str) -> str | None:
    normalized = message.lower()
    if any(phrase in normalized for phrase in _AUTHENTICATION_ERROR_PHRASES):
        return None
    if any(phrase in normalized for phrase in _WEEKLY_LIMIT_PHRASES):
        return WINDOW_SEVEN_DAY
    if any(phrase in normalized for phrase in _SHORT_LIMIT_PHRASES):
        return WINDOW_FIVE_HOUR
    return None


def _forwarded_reset(*, message: str, recorded_at: float) -> float | None:
    """The same concrete reset forms a locally read provider message supports."""
    _, separator, value = message.rpartition("limit reached|")
    if separator and value.isdigit() and _EPOCH_MIN_DIGITS <= len(value) <= _EPOCH_MAX_DIGITS:
        return float(value)
    marker = "retry-after"
    lowered = message.lower()
    if marker not in lowered:
        return None
    suffix = lowered.split(marker, 1)[1].lstrip("-_ :")
    digits = "".join(character for character in suffix if character.isdigit())
    return (
        recorded_at + float(digits) if digits and len(digits) <= _RETRY_AFTER_MAX_DIGITS else None
    )

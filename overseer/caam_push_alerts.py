"""Durable, best-effort push alerts for rotation-pass conditions.

Alerts are deliberately outside the provider and selection paths.  The caller
hands this module facts already established by the pass; it only remembers the
condition's onset and tries the operator's configured ntfy channel.  A delivery
failure is data for the report, never a reason to hold or revisit a decision.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, cast

from caam_delivery_push_sweep import Post, ntfy_push, ntfy_url

__all__: list[str] = ["observe_alerts"]

_STATE_REL: Final = Path(".local/state/caam-usage-rotate/push-alerts.json")
_REPEAT_S: Final = 6 * 60 * 60


@dataclass(frozen=True, kw_only=True)
class _Condition:
    key: str
    description: str
    subject: str
    started_at: float


@dataclass(frozen=True, kw_only=True)
class _Remembered:
    description: str
    subject: str
    started_at: float
    alerted_at: float | None


def observe_alerts(
    *,
    home: Path,
    now: float,
    conditions: Iterable[tuple[str, str, str, float]],
    post: Post | None,
    stdout: Callable[[str], None],
) -> None:
    """Reconcile present conditions with the durable alert state.

    Each tuple is ``(key, description, subject, started_at)``.  Keys and state
    contain identities and timestamps only, never credential values.
    """
    current = {
        key: _Condition(key=key, description=description, subject=subject, started_at=started_at)
        for key, description, subject, started_at in conditions
    }
    remembered = _load(home=home)
    configured = ntfy_url(home=home) is not None
    next_state: dict[str, _Remembered] = {}

    for key, condition in current.items():
        prior = remembered.pop(key, None)
        started = condition.started_at if prior is None else prior.started_at
        alerted_at = None if prior is None else prior.alerted_at
        due = alerted_at is None or now - alerted_at >= _REPEAT_S
        if due:
            verb = "started" if alerted_at is None else "persists"
            sent = _deliver(
                home=home,
                message=(
                    f"rotation alert: {condition.description} {verb} at {_stamp(at=started)}; "
                    f"{condition.subject}"
                ),
                post=post,
                configured=configured,
                stdout=stdout,
            )
            if sent:
                alerted_at = now
        next_state[key] = _Remembered(
            description=condition.description,
            subject=condition.subject,
            started_at=started,
            alerted_at=alerted_at,
        )

    for key, prior in remembered.items():
        sent = _deliver(
            home=home,
            message=(
                f"rotation recovery: {prior.description} ended; {prior.subject}; "
                f"started {_stamp(at=prior.started_at)}"
            ),
            post=post,
            configured=configured,
            stdout=stdout,
        )
        if not sent:
            next_state[key] = prior
    _save(home=home, conditions=next_state)


def _deliver(
    *, home: Path, message: str, post: Post | None, configured: bool, stdout: Callable[[str], None]
) -> bool:
    if not configured:
        stdout("alerts cannot be delivered: no push channel configured")
        return False
    outcome = ntfy_push(home=home, message=message, post=post)
    if not outcome.startswith("sent"):
        stdout(f"alert delivery failed ({outcome}); retrying next pass")
        return False
    return True


def _load(*, home: Path) -> dict[str, _Remembered]:
    try:
        raw: object = json.loads((home / _STATE_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    body = cast(dict[str, object], raw) if isinstance(raw, dict) else None
    entries = None if body is None else body.get("conditions")
    if not isinstance(entries, dict):
        return {}
    result: dict[str, _Remembered] = {}
    for key, value in cast(Mapping[object, object], entries).items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        entry = cast(dict[str, object], value)
        description, subject, started_at, alerted_at = (
            entry.get("description"),
            entry.get("subject"),
            entry.get("started_at"),
            entry.get("alerted_at"),
        )
        if (
            isinstance(description, str)
            and isinstance(subject, str)
            and isinstance(started_at, float | int)
            and (alerted_at is None or isinstance(alerted_at, float | int))
        ):
            result[key] = _Remembered(
                description=description,
                subject=subject,
                started_at=float(started_at),
                alerted_at=None if alerted_at is None else float(alerted_at),
            )
    return result


def _save(*, home: Path, conditions: dict[str, _Remembered]) -> None:
    path = home / _STATE_REL
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = {
        "conditions": {
            key: {
                "description": value.description,
                "subject": value.subject,
                "started_at": value.started_at,
                "alerted_at": value.alerted_at,
            }
            for key, value in sorted(conditions.items())
        }
    }
    temporary = path.with_name(path.name + ".tmp")
    _ = temporary.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    _ = temporary.replace(path)


def _stamp(*, at: float) -> str:
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

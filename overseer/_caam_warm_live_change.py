"""Classify whether a concurrent live-token change came from keep-warm."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from caam_usage import read_creds

__all__: list[str] = ["finish_warm"]

_LIVE_CHANGED = (
    "FAIL keep-warm altered the LIVE credential -- this must never happen; "
    "investigate before trusting the next rotation"
)
_LIVE_REFRESHED = (
    "keep-warm: the active account's own session refreshed its token during maintenance"
)


def finish_warm(
    *,
    live_before: str | None,
    live_path: Path,
    sandbox: Path,
    logger: Callable[[str], None],
) -> None:
    """Classify any live change before deleting the evidence-bearing sandbox."""

    live_after, _ = read_creds(path=live_path)
    message = _live_change_message(
        live_before=live_before,
        live_after=live_after,
        sandbox=sandbox,
    )
    if message is not None:
        logger(message)
    shutil.rmtree(sandbox, ignore_errors=True)


def _live_change_message(
    *, live_before: str | None, live_after: str | None, sandbox: Path
) -> str | None:
    """Attribute a live change while the warm sandbox credential remains readable."""

    if live_after == live_before:
        return None
    sandbox_token, _ = read_creds(path=sandbox / ".credentials.json")
    if live_after is not None and live_after == sandbox_token:
        return _LIVE_CHANGED
    return _LIVE_REFRESHED

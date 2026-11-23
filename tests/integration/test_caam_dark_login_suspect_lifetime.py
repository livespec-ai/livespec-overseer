"""Transient and stale readings do not misjudge a dark login."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_caam_dark_login import ACTIVE, HOUR, NOW, two_accounts


@pytest.mark.integration
@pytest.mark.parametrize(
    "transient_failure",
    [
        "HTTP 429 rate_limit_error: retry later",
        "HTTP 500 internal_server_error",
        "network failure: connection reset",
    ],
)
def test_transient_reading_preserves_a_dark_login_suspect(
    *, tmp_path: Path, transient_failure: str
) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."

    _ = harness.run()
    harness.refused[ACTIVE] = transient_failure
    _ = harness.run(at=NOW + HOUR / 2)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."
    _ = harness.run(at=NOW + HOUR)

    assert harness.switches == ["anthropic-1"]
    assert harness.store()["holds"][ACTIVE]["condition"] == "b"  # type: ignore[index]


def test_healthy_reading_clears_a_dark_login_suspect(*, tmp_path: Path) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."

    _ = harness.run()
    del harness.refused[ACTIVE]
    _ = harness.run(at=NOW + HOUR / 2)

    assert ACTIVE not in harness.store()["suspects"]  # type: ignore[operator]


def test_suspect_older_than_four_hours_does_not_confirm_a_dark_login(*, tmp_path: Path) -> None:
    harness = two_accounts(tmp_path=tmp_path)
    harness.write_live_credential(expires_at=NOW + 10 * HOUR)
    harness.refused[ACTIVE] = "OAuth access token has been revoked."

    _ = harness.run()
    _ = harness.run(at=NOW + 4 * HOUR + 1)

    assert harness.switches == []
    suspect = harness.store()["suspects"][ACTIVE]  # type: ignore[index]
    assert suspect["first_refused_at"] == NOW + 4 * HOUR + 1

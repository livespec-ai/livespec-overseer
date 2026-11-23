"""Regression coverage for dark-login refusal classification."""

from __future__ import annotations

import json
from pathlib import Path

from caam_dark_login import DarkObservation, _refused_unauthenticated
from caam_decision import ProfileUsage
from caam_login_refusals import KIND_REVOKED, session_login_refusals
from caam_profiles import ActiveIdentity
from caam_refusals import TrackedSession

__all__: list[str] = []


def test_revoked_typed_api_error_is_a_login_refusal(*, tmp_path: Path) -> None:
    config_dir = tmp_path / ".claude"
    transcript = config_dir / "projects" / "-repo" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-11-22T21:00:00Z",
                "isApiErrorMessage": True,
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "API Error 401 authentication_error: "
                                "OAuth access token has been revoked."
                            ),
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    refusals = session_login_refusals(
        session=TrackedSession(session_id="session", config_dir=config_dir)
    )

    assert [(refusal.kind, refusal.account) for refusal in refusals] == [(KIND_REVOKED, None)]


def test_rate_limit_and_network_failures_are_not_unauthenticated(*, tmp_path: Path) -> None:
    credential = tmp_path / ".claude/.credentials.json"
    credential.parent.mkdir(parents=True)
    credential.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "fake", "expiresAt": 2_000_000_000_000}}),
        encoding="utf-8",
    )
    for failure in ("HTTP 429 rate_limit_error: retry later", "OSError: network unreachable"):
        observation = DarkObservation(
            home=tmp_path,
            state={},
            active=ActiveIdentity(profile="active", account_uuid=None),
            profiles=(
                ProfileUsage(
                    name="active", source=f"dark: {failure}", usage=None, read_failure=failure
                ),
            ),
            live_before=None,
            sessions=lambda: (),
            now=1_800_000_000.0,
            dry_run=False,
        )

        assert not _refused_unauthenticated(observation=observation)

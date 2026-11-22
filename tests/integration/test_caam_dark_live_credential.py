"""Integration coverage for a rotation pass with no usable live login."""

from __future__ import annotations

import json
from pathlib import Path

import caam_anthropic_loop as module
import pytest

__all__: list[str] = []


class _ActiveProfileProcess:
    returncode = 0
    stdout = '{"tools": [{"tool": "claude", "active_profile": "active"}]}'
    stderr = ""


def _write_active_snapshot(*, home: Path) -> None:
    profile = home / ".local" / "share" / "caam" / "vault" / "claude" / "active"
    profile.mkdir(parents=True)
    _ = (profile / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "stored", "expiresAt": 30_000_000}}),
        encoding="utf-8",
    )
    _ = (profile / ".claude.json").write_text('{"oauthAccount": {}}', encoding="utf-8")
    _ = (profile / "settings.json").write_text("{}", encoding="utf-8")


def _no_plan_read(*, creds_path: Path, now: float | None = None) -> tuple[None, str]:
    del creds_path, now
    return None, "no live plan read in this test"


@pytest.mark.parametrize("credential_text", [None, "{"])
def test_dark_live_credential_holds_with_the_unavailable_token_reason(
    *, tmp_path: Path, credential_text: str | None
) -> None:
    _write_active_snapshot(home=tmp_path)
    if credential_text is not None:
        live_credentials = tmp_path / ".claude" / ".credentials.json"
        live_credentials.parent.mkdir()
        _ = live_credentials.write_text(credential_text, encoding="utf-8")
    lines: list[str] = []

    result = module.run_pass(
        flags=module.parse_flags(argv=["--scheduled", "--no-warm"]),
        home=tmp_path,
        now=2_000.0,
        stdout=lines.append,
        caam_runner=lambda *, args: _ActiveProfileProcess(),
        capacity_source=_no_plan_read,
        save_state=lambda *, state, state_path: None,
        enforce_models=lambda **kwargs: [],
    )

    assert result == 0
    assert any(line.startswith("hold:") and "no token in snapshot" in line for line in lines)
    assert not any(line.startswith("FAIL") for line in lines)

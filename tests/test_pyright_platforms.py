"""Platform-specific acceptance coverage for the type-check configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_darwin_pyright_accepts_linux_only_stdlib_guards() -> None:
    """Darwin analysis must accept guarded ``pipe2`` and ``SO_PEERCRED`` use."""
    result = subprocess.run(  # noqa: S603
        ["uv", "run", "pyright", "--pythonplatform", "Darwin"],  # noqa: S607
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

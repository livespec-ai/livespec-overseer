"""Platform-specific primitives shared by local-provider performers."""

from __future__ import annotations

import os
import sys

__all__: list[str] = ["close_on_exec_pipe"]


def close_on_exec_pipe() -> tuple[int, int]:
    return os.pipe2(os.O_CLOEXEC) if sys.platform == "linux" else os.pipe()  # pragma: no cover

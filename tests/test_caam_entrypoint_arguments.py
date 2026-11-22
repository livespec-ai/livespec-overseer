"""Argument safety at the three CAAM console-entrypoint action boundaries."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_help_exits_before_every_caam_action(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--help` is informational and must not start any CAAM operation."""
    rotation = importlib.import_module("caam_anthropic_loop")
    rotation_output: list[str] = []
    rotations: list[object] = []

    assert (
        rotation.main(
            argv=["--help"],
            stdout=rotation_output.append,
            pass_runner=lambda **kwargs: rotations.append(kwargs) or 99,
        )
        == 0
    )
    assert rotations == []
    assert any("usage" in line.lower() for line in rotation_output)

    delivery = importlib.import_module("caam_delivery_push_entry")
    delivery_output: list[str] = []
    deliveries: list[object] = []
    monkeypatch.setattr(
        delivery,
        "run_once",
        lambda **kwargs: deliveries.append(kwargs),
    )
    monkeypatch.setattr(
        delivery.streams,
        "write_stdout",
        lambda *, text: delivery_output.append(text),
    )

    assert delivery.main(argv=["--help"], sleep=lambda _: None, passes=1) == 0
    assert deliveries == []
    assert any("usage" in line.lower() for line in delivery_output)

    strip = importlib.import_module("caam_refresh_strip")
    strip_output: list[str] = []
    strips: list[object] = []
    monkeypatch.setattr(strip, "credential_files", lambda *, home: (tmp_path / "credentials",))
    monkeypatch.setattr(
        strip,
        "strip_file",
        lambda **kwargs: strips.append(kwargs) or "clean placeholder",
    )
    monkeypatch.setattr(strip.streams, "write_stdout", lambda *, text: strip_output.append(text))

    assert strip.main(argv=["--help"], proc_root=tmp_path) == 0
    assert strips == []
    assert any("usage" in line.lower() for line in strip_output)

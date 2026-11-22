"""Console entry point for the caam Anthropic account-rotation pass."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streams
from caam_anthropic_pass import run_pass
from caam_switch import SwitchResult

__all__: list[str] = [
    "UNSCHEDULED_LINE",
    "Flags",
    "LineWriter",
    "SwitchResult",
    "main",
    "parse_flags",
    "run_pass",
]

_EXPECTED_ERRORS = (
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    KeyError,
    IndexError,
    subprocess.SubprocessError,
)


UNSCHEDULED_LINE = (
    "unscheduled: no --scheduled marker, so this pass rotates now;"
    " the projected short-window drain and the expiring-weekly drain do not apply"
)
_USAGE = (
    "usage: caam-anthropic-loop [--scheduled] [--force] [--dry-run] [--no-models] "
    "[--no-warm] [--session-model SESSION=MODEL] "
    "[--protected-account ACCOUNT=FLOOR]"
)


class LineWriter(Protocol):
    def __call__(self, line: str) -> None: ...


_ARGUMENT_ERROR_PREFIX = "argument error: "


class PassRunner(Protocol):
    def __call__(self, *, flags: Flags) -> int: ...


@dataclass(frozen=True, kw_only=True)
class Flags:
    scheduled: bool
    force: bool
    dry_run: bool
    no_models: bool
    no_warm: bool
    session_models: tuple[tuple[str, str], ...]
    protected_accounts: tuple[tuple[str, str], ...] = ()


def parse_flags(*, argv: list[str], environ: Mapping[str, str] | None = None) -> Flags:
    del environ
    # Idle-profile keep-warm is ON BY DESIGN: expiry-scheduled maintenance is the
    # mechanism that keeps idle accounts selectable (overseer-54k2za.52), so it is
    # not an opt-in. `--no-warm` remains as an explicit escape for a pass that must
    # not touch idle snapshots.
    values = {name: False for name in ("scheduled", "force", "dry_run", "no_models", "no_warm")}
    session_models: list[tuple[str, str]] = []
    protected_accounts: list[tuple[str, str]] = []
    index = 0
    while index < len(argv):
        lowered = argv[index].strip().lower()
        if _is_valued_flag(lowered=lowered, name="--session-model"):
            index = _append_session_model(argv=argv, index=index, session_models=session_models)
        elif _is_valued_flag(lowered=lowered, name="--protected-account"):
            index = _append_protected_account(
                argv=argv,
                index=index,
                protected_accounts=protected_accounts,
            )
        elif not _apply_bool_flag(lowered=lowered, values=values):
            raise _argument_error(issue="unrecognised argument", argument=argv[index])
        index += 1
    return Flags(
        session_models=tuple(session_models),
        protected_accounts=tuple(protected_accounts),
        **values,
    )


def _is_valued_flag(*, lowered: str, name: str) -> bool:
    """A valued flag is its exact name, or the name followed by `=`; never a longer name."""
    return lowered == name or lowered.startswith(f"{name}=")


def _append_session_model(
    *, argv: list[str], index: int, session_models: list[tuple[str, str]]
) -> int:
    value = argv[index].partition("=")[2]
    if not value and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        index += 1
        value = argv[index]
    if not value:
        raise _argument_error(issue="missing value for", argument=argv[index])
    session, _separator, model = value.partition("=")
    session_models.append((session.strip(), model.strip().lower()))
    return index


def _append_protected_account(
    *, argv: list[str], index: int, protected_accounts: list[tuple[str, str]]
) -> int:
    value = argv[index].partition("=")[2]
    if not value and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        index += 1
        value = argv[index]
    if not value:
        raise _argument_error(issue="missing value for", argument=argv[index])
    account, _separator, floor = value.partition("=")
    protected_accounts.append((account.strip(), floor.strip().lower()))
    return index


def _apply_bool_flag(*, lowered: str, values: dict[str, bool]) -> bool:
    if lowered == "--scheduled":
        values["scheduled"] = True
    elif lowered == "--force":
        values["force"] = True
    elif lowered == "--dry-run":
        values["dry_run"] = True
    elif lowered == "--no-models":
        values["no_models"] = True
    elif lowered == "--no-warm":
        values["no_warm"] = True
    elif lowered == "--warm":
        # The retired opt-in remains a recognised no-op for compatibility.
        pass
    else:
        return False
    return True


def _argument_error(*, issue: str, argument: str) -> ValueError:
    return ValueError(f"{_ARGUMENT_ERROR_PREFIX}{issue}: {argument}")


def main(
    *,
    argv: list[str] | None = None,
    stdout: LineWriter | None = None,
    pass_runner: PassRunner | None = None,
) -> int:
    writer = _stdout_line if stdout is None else stdout
    runner = _main_pass_runner(writer=writer) if pass_runner is None else pass_runner
    args = list(sys.argv[1:] if argv is None else argv)
    if any(argument.strip().lower() == "--help" for argument in args):
        writer(_USAGE)
        return 0
    try:
        flags = parse_flags(argv=args)
        return runner(flags=_resolve_mode(flags=flags, writer=writer))
    except ValueError as exc:
        if str(exc).startswith(_ARGUMENT_ERROR_PREFIX):
            writer(_USAGE)
            writer(f"error: {str(exc).removeprefix(_ARGUMENT_ERROR_PREFIX)}")
            return 2
        writer(f"FAIL {type(exc).__name__}: {exc}")
        return 2
    except _EXPECTED_ERRORS as exc:
        writer(f"FAIL {type(exc).__name__}: {exc}")
        return 2


def _resolve_mode(*, flags: Flags, writer: LineWriter) -> Flags:
    """Resolve an executable run that names no mode per contracts.md **Mode resolution**.

    Without the scheduled marker an invocation is an explicit request to rotate
    now, so a run naming none of `--scheduled`, `--force` or `--dry-run` is
    forced, keeping every refusal `--force` keeps. Saying so is the point: a
    lost marker must degrade to a forced rotation the operator can SEE, never
    to a pass with only the plain triggers live and nothing to say about it.
    """
    if flags.scheduled or flags.force or flags.dry_run:
        return flags
    writer(UNSCHEDULED_LINE)
    return replace(flags, force=True)


def _main_pass_runner(*, writer: LineWriter) -> PassRunner:
    def runner(*, flags: Flags) -> int:
        return run_pass(flags=flags, stdout=writer)

    return runner


class _StdoutLine:
    def __call__(self, line: str) -> None:
        streams.write_stdout(text=line + "\n")


_stdout_line = _StdoutLine()


if __name__ == "__main__":
    raise SystemExit(main())

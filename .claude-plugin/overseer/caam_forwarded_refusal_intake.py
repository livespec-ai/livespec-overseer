"""Collect each listed host's refusal over the verified delivery-push ssh session.

A refusal observed on another host holds the active account fleet-wide only when
the role holder can tell the host really observed it.  The delivery push already
reaches every listed host over ssh with `StrictHostKeyChecking=yes` against the
role holder's own known-hosts record, so that session is the authentication: the
role holder runs `FORWARD_SCRIPT` there, takes the one reply line, and stamps what
it read with the host label and ssh target it just ran against.  Nothing the reply
or the anthropic loop's state says about its own origin is believed.

The stamped records live in a private file in the push service's state directory
(`delivery-forwarded-refusals.json`).  Each pass `verified_forwarded_state` loads
them into the loop state for the duration of the observation only, REPLACING any
forwarded-refusal keys already there, and removes them afterwards, so a record that
was merely written into loop state is never read.  A stored record counts as the
listed host's own only while the host is still listed under the ssh target it was
collected from.  No token or credential is ever read or stored: the host program
forwards one account identifier, one instant and one provider phrase.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import caam_delivery_service
import jsonio
import streams
from caam_delivery_push_state import (
    KNOWN_HOSTS,
    MAX_RESULT_CHARS,
    STATE_DIR,
    Host,
    load_config,
    load_hosts,
    seconds,
)
from caam_forwarded_refusals import DELIVERY_HOSTS_KEY, FORWARDED_REFUSALS_KEY

__all__: list[str] = [
    "FORWARDED_FILE",
    "FORWARD_INTERVAL_S",
    "FORWARD_SCRIPT",
    "forward_if_due",
    "forward_refusals",
    "verified_forwarded",
    "verified_forwarded_state",
]

FORWARDED_FILE = f"{STATE_DIR}/delivery-forwarded-refusals.json"
FORWARD_INTERVAL_S = 60.0
_REPLY_PREFIX = "forwarded-refusal "
_CLEAR_REPLY = "no-refusal"

Runner = Callable[..., tuple[int, str]]

# The host-side program, sent on `python3 -`'s stdin like the apply step.  It reads
# only the default configuration directory (the live credential's), matches the same
# structural error marker and provider phrases the role holder's own reader does,
# skips any authentication error and any line naming no account, and prints one line:
# the newest refusal's own account (the one its line names, never the host's current
# one, which may have switched since), instant and the matched phrase (with its reset
# epoch or retry-after), or `no-refusal`.
FORWARD_SCRIPT = r"""
import datetime, glob, json, os, re
TAIL = 65536
FILES = 20
MARKER = re.compile(r'"isApiErrorMessage"\s*:\s*true|"type"\s*:\s*"error"', re.I)
PHRASE = re.compile(
    r"weekly limit reached|hit your weekly limit|weekly usage limit|usage limit reached"
    r"|hit your session limit|hit your usage limit|rate_limit_error|rate limit exceeded",
    re.I,
)
DENIED = re.compile(
    r"authentication error|unauthorized|invalid api key|expired credential|revoked credential",
    re.I,
)
STAMP = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
ACCOUNT = re.compile(r'"accountUuid"\s*:\s*"([^"]+)"')
EPOCH = re.compile(r"limit reached\|(\d{9,11})")
RETRY = re.compile(r"retry[-_ ]after\D{0,4}(\d{1,6})", re.I)
def modified(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
def tail(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - TAIL))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines if end <= TAIL else lines[1:]
def refusal(line):
    if not MARKER.search(line) or DENIED.search(line):
        return None
    phrase, stamp, who = PHRASE.search(line), STAMP.search(line), ACCOUNT.search(line)
    if not phrase or not stamp or not who:
        return None
    try:
        at = datetime.datetime.fromisoformat(stamp.group(1).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    message = phrase.group(0).lower()
    epoch, retry = EPOCH.search(line), RETRY.search(line)
    if epoch and message.endswith("limit reached"):
        message += "|" + epoch.group(1)
    elif retry:
        message += " retry-after " + retry.group(1)
    return at, message, who.group(1)
def main():
    home = os.path.expanduser("~")
    best = None
    paths = glob.glob(os.path.join(home, ".claude", "projects", "*", "*.jsonl"))
    for path in sorted(paths, key=modified, reverse=True)[:FILES]:
        for line in tail(path):
            found = refusal(line)
            if found and (best is None or found[0] > best[0]):
                best = found
    if best is None:
        print("no-refusal")
    else:
        print("forwarded-refusal " + json.dumps(
            {"account": best[2], "recorded_at": best[0], "provider_message": best[1]}
        ))
main()
"""


def forward_refusals(*, home: Path, now: float, run: Runner) -> dict[str, str]:
    """Ask every listed host over `run`, the verified ssh runner; label -> outcome.

    A host that answers `no-refusal` has its stored record withdrawn.  A host whose
    session failed, or whose reply could not be read, keeps whatever it last
    forwarded: attribution's own staleness rules decide whether that still holds.
    """
    hosts = load_hosts(home=home)
    if not hosts:
        return {}
    settings = load_config(home=home)
    known_hosts = str(home / KNOWN_HOSTS)
    timeout = seconds(settings=settings, key="push_timeout_s")

    def ask(*, host: Host) -> str:
        return run(
            target=host.target,
            program=FORWARD_SCRIPT,
            key=str(settings["ssh_key"]),
            known_hosts=known_hosts,
            timeout=timeout,
        )[1]

    with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = [(host, pool.submit(ask, host=host)) for host in hosts]
        replies = [(host, future.result()) for host, future in futures]
    listed = {host.label for host in hosts}
    store = {label: entry for label, entry in _store(home=home).items() if label in listed}
    outcomes = {
        host.label: _fold(store=store, host=host, reply=reply, now=now) for host, reply in replies
    }
    caam_delivery_service.write_private_json(path=home / FORWARDED_FILE, value=dict(store))
    return outcomes


def forward_if_due(*, home: Path, now: float, due_at: float, run: Runner) -> float:
    """One forwarding round when `now` has reached `due_at`; the next due instant."""
    if now < due_at:
        return due_at
    for label, outcome in forward_refusals(home=home, now=now, run=run).items():
        streams.write_stdout(text=f"forwarded-refusal {label}: {outcome}\n")
    return now + FORWARD_INTERVAL_S


def verified_forwarded(*, home: Path) -> tuple[list[str], list[object]]:
    """The listed host labels and the stored records, stamped for the reader.

    `authenticated_host` is the label only for a record collected from the ssh
    target the host is listed under now; any other stored record carries none.
    """
    hosts = load_hosts(home=home)
    targets = {host.label: host.target for host in hosts}
    records: list[object] = [
        {
            "host": label,
            "authenticated_host": label if targets.get(label) == entry.get("target") else None,
            "account": entry.get("account"),
            "recorded_at": entry.get("recorded_at"),
            "provider_message": entry.get("provider_message"),
        }
        for label, entry in _store(home=home).items()
    ]
    return list(targets), records


@contextmanager
def verified_forwarded_state(*, home: Path, state: dict[str, object]) -> Iterator[None]:
    """Hold the verified store in `state` for one observation, replacing anything already there."""
    hosts, records = verified_forwarded(home=home)
    state[DELIVERY_HOSTS_KEY] = hosts
    state[FORWARDED_REFUSALS_KEY] = records
    try:
        yield
    finally:
        _ = state.pop(DELIVERY_HOSTS_KEY, None)
        _ = state.pop(FORWARDED_REFUSALS_KEY, None)


def _fold(*, store: dict[str, dict[str, object]], host: Host, reply: str, now: float) -> str:
    if reply == _CLEAR_REPLY:
        _ = store.pop(host.label, None)
        return "none"
    entry = _entry(reply=reply) if reply.startswith(_REPLY_PREFIX) else None
    if entry is None:
        return "unread"
    store[host.label] = {**entry, "target": host.target, "received_at": now}
    return "forwarded"


def _entry(*, reply: str) -> dict[str, object] | None:
    parsed = jsonio.parse_object(text=reply.removeprefix(_REPLY_PREFIX))
    body = None if jsonio.is_parse_failure(result=parsed) else parsed.unwrap()
    if body is None:
        return None
    account, message = body.get("account"), body.get("provider_message")
    recorded_at = jsonio.as_float(value=body.get("recorded_at"))
    if (
        not isinstance(account, str)
        or not account
        or recorded_at is None
        or not isinstance(message, str)
        or len(message) > MAX_RESULT_CHARS
    ):
        return None
    return {"account": account, "recorded_at": recorded_at, "provider_message": message}


def _store(*, home: Path) -> dict[str, dict[str, object]]:
    path = home / FORWARDED_FILE
    if not path.exists():
        return {}
    parsed = jsonio.parse_object(text=path.read_text(encoding="utf-8"))
    body = None if jsonio.is_parse_failure(result=parsed) else parsed.unwrap()
    return {key: value for key, value in (body or {}).items() if isinstance(value, dict)}

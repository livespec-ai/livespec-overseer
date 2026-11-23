"""The production pane driver lists every Herdr agent over the real adapter.

``overseer-3xc62h``: the status snapshot projects one row per listed Herdr agent,
which only holds in the running daemon if the driver the daemon actually builds
(``pane_router.default_pane_driver``) implements the listing.  A fake that grows
the method proves the tick's loop and nothing about production, so this drives the
real ``MixedPaneDriver`` and ``HerdrAdapter`` against a real socket peer whose
replies are scripted from the measured ``agent_list`` shape (``herdr api schema
--json``, protocol 22: ``result.agents[]`` of ``AgentInfo``).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import herdr_adapter
import herdr_identity
import pane_router
import pytest

__all__: list[str] = []

PANE_LIST = {
    "type": "pane_list",
    "panes": [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"}],
}


def _agent(*, pane_id: str, status: str, name: str | None, title: str | None = None):
    return {
        "terminal_id": "term_1",
        "workspace_id": "w1",
        "tab_id": "w1:t1",
        "pane_id": pane_id,
        "focused": False,
        "revision": 0,
        "agent_status": status,
        "name": name,
        "title": title,
    }


@pytest.fixture(name="socket_dir")
def _socket_dir() -> Iterator[Path]:
    created = tempfile.mkdtemp(prefix="hrag")
    yield Path(created)
    shutil.rmtree(created, ignore_errors=True)


def _serve(*, address: Path, results: list[dict[str, object]]) -> list[bytes]:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(address))
    listener.listen(8)
    received: list[bytes] = []

    def run() -> None:
        listener.settimeout(5.0)
        for index, result in enumerate(results, start=1):
            try:
                conn, _ = listener.accept()
            except OSError:
                break
            with conn:
                conn.settimeout(5.0)
                buffered = b""
                while not buffered.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buffered += chunk
                received.append(buffered)
                reply = {"id": f"rq-{index}", "result": result}
                conn.sendall(json.dumps(reply).encode("utf-8") + b"\n")
        listener.close()

    threading.Thread(target=run, daemon=True).start()
    return received


def _driver(*, address: Path):
    adapter = herdr_adapter.HerdrAdapter(request_ids=(f"rq-{i}" for i in range(1, 64)))
    return pane_router.MixedPaneDriver(herdr=adapter, herdr_endpoints=lambda: (str(address),))


def test_the_production_driver_lists_every_agent_with_an_exact_qualified_pane(*, socket_dir):
    address = socket_dir / "h.sock"
    agents = [
        _agent(pane_id="w1:p1", status="working", name="working-agent"),
        _agent(pane_id="w1:p2", status="idle", name="idle-agent"),
        _agent(pane_id="w1:p3", status="done", name="done-agent"),
        _agent(pane_id="w1:p4", status="unknown", name=None, title="titled-agent"),
        _agent(pane_id="w1:p5", status="blocked", name=None, title=None),
    ]
    received = _serve(
        address=address, results=[PANE_LIST, {"type": "agent_list", "agents": agents}]
    )

    listed = _driver(address=address).herdr_agent_list()

    assert [(row["name"], row["status"]) for row in listed] == [
        ("working-agent", "working"),
        ("idle-agent", "idle"),
        ("done-agent", "done"),
        ("titled-agent", "unknown"),
        ("w1:p5", "blocked"),
    ]
    targets = [herdr_identity.decode_target(value=row["pane"]).herdr for row in listed]
    assert [target.pane_id for target in targets if target] == [
        "w1:p1",
        "w1:p2",
        "w1:p3",
        "w1:p4",
        "w1:p5",
    ]
    assert {target.server_pid for target in targets if target} == {os.getpid()}
    assert json.loads(received[1].decode("utf-8"))["method"] == "agent.list"


def test_a_refused_or_unreadable_listing_contributes_no_agents(*, socket_dir):
    address = socket_dir / "h.sock"
    _ = _serve(
        address=address,
        results=[PANE_LIST, {"type": "agent_list", "agents": [{"name": "no-pane"}]}],
    )
    assert _driver(address=address).herdr_agent_list() == []

    missing = socket_dir / "absent.sock"
    assert _driver(address=missing).herdr_agent_list() == []


def test_a_listing_that_is_not_a_list_or_names_a_non_object_is_refused(*, socket_dir):
    address = socket_dir / "h.sock"
    _ = _serve(
        address=address,
        results=[
            PANE_LIST,
            {"type": "agent_list", "agents": "nope"},
            PANE_LIST,
            {"type": "agent_list", "agents": [5]},
        ],
    )
    driver = _driver(address=address)
    assert driver.herdr_agent_list() == []
    assert driver.herdr_agent_list() == []


def test_a_driver_whose_observer_cannot_list_agents_lists_none(*, socket_dir):
    class _PanesOnly:
        pass

    driver = pane_router.MixedPaneDriver(
        herdr=_PanesOnly(),  # type: ignore[arg-type]
        herdr_endpoints=lambda: (str(socket_dir / "h.sock"),),
    )
    assert driver.herdr_agent_list() == []

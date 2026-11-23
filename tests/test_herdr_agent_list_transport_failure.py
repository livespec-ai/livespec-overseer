"""A transport failure on the ``agent.list`` request lists no agents.

``overseer-3xc62h``: the production driver identifies the server with a
``pane.list`` round trip and then asks the same server for its agents.  When that
second request cannot be completed the adapter reports the failure instead of
raising, and the driver contributes no agents to the status snapshot.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import herdr_adapter
import pane_router
import pytest

__all__: list[str] = []

PANE_LIST = {
    "type": "pane_list",
    "panes": [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"}],
}


@pytest.fixture(name="socket_dir")
def _socket_dir() -> Iterator[Path]:
    created = tempfile.mkdtemp(prefix="hrat")
    yield Path(created)
    shutil.rmtree(created, ignore_errors=True)


def _serve_one_pane_list(*, address: Path) -> None:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(address))
    listener.listen(1)

    def run() -> None:
        listener.settimeout(5.0)
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(5.0)
            buffered = b""
            while not buffered.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buffered += chunk
            reply = {"id": "rq-1", "result": PANE_LIST}
            conn.sendall(json.dumps(reply).encode("utf-8") + b"\n")
        listener.close()

    threading.Thread(target=run, daemon=True).start()


def test_an_agent_list_request_that_cannot_complete_lists_no_agents(*, socket_dir):
    address = socket_dir / "h.sock"
    _serve_one_pane_list(address=address)
    adapter = herdr_adapter.HerdrAdapter(request_ids=(f"rq-{i}" for i in range(1, 64)))
    driver = pane_router.MixedPaneDriver(herdr=adapter, herdr_endpoints=lambda: (str(address),))

    assert driver.herdr_agent_list() == []

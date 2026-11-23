"""Enumerate every agent the reachable Herdr servers list, as routable panes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Protocol, runtime_checkable

import herdr_adapter
import herdr_identity

__all__: list[str] = ["AgentObserver", "HerdrAgent", "herdr_agent_list"]

HerdrAgent = dict[str, str]


@runtime_checkable
class AgentObserver(Protocol):
    def identify(self, *, socket_path: str) -> herdr_adapter.InstanceIdentification: ...

    def list_agents(
        self, *, target: herdr_identity.HerdrPaneTarget
    ) -> herdr_adapter.AgentListing: ...


def herdr_agent_list(
    *, observer: object, endpoints: Callable[[], Iterable[str]]
) -> list[HerdrAgent]:
    """`name`, `status` and the exact qualified `pane` coordinate of every listed agent.

    The pane is qualified by the server generation that answered, so a later read of
    it cannot silently land on another server that reuses the pane id. An endpoint
    that cannot be identified, or whose listing is refused, contributes nothing — the
    same fail-closed reading every other observation takes.
    """
    if not isinstance(observer, AgentObserver):
        return []
    agents: list[HerdrAgent] = []
    for endpoint in endpoints():
        peer = observer.identify(socket_path=endpoint).peer
        if peer is None:
            continue
        probe = herdr_identity.HerdrPaneTarget(
            socket_path=endpoint,
            server_pid=peer.pid,
            server_starttime=peer.starttime,
            pane_id="",
        )
        agents.extend(
            {
                "name": row.name,
                "status": row.status,
                "pane": herdr_identity.encode_herdr_target(
                    target=replace(probe, pane_id=row.pane_id)
                ),
            }
            for row in observer.list_agents(target=probe).agents
        )
    return agents

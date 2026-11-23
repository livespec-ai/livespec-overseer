"""herdr_agents.py — the `agent.list` reply, parsed. PURE, no I/O.

The daemon's status snapshot is an inventory of every agent the backend reports,
not only of the agents a plan mapping or a resumed-session join happens to reach
(`overseer-3xc62h`). This module reads the one reply that enumerates them.

**Measured shape** (`herdr api schema --json`, protocol 22): `agent.list` answers
`result.type == "agent_list"` with `result.agents[]`, each an `AgentInfo` whose
required members are `pane_id` and `agent_status`, and whose `name` and `title`
may be null. Reading is FAIL-CLOSED like :mod:`herdr_calls`: a row that is not an
object or names no pane identifies nothing a caller could address, so the whole
listing is refused rather than silently shortened.
"""

from __future__ import annotations

from dataclasses import dataclass

import herdr_protocol
import jsonio

__all__: list[str] = [
    "EXPECT_AGENT_LIST",
    "METHOD_AGENT_LIST",
    "AgentRow",
    "agent_rows",
]

METHOD_AGENT_LIST = "agent.list"
EXPECT_AGENT_LIST = herdr_protocol.ReplyExpectation(
    result_type="agent_list", required_fields=("agents",)
)


@dataclass(frozen=True, kw_only=True)
class AgentRow:
    """One listed agent: the name an operator reads, its pane, and its status.

    `name` falls back to the title and then to the pane id, so an agent the backend
    lists without a name is still named in the snapshot rather than dropped.
    """

    name: str
    pane_id: str
    status: str


def _text(*, row: dict[str, object], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def _agent_row(*, raw: object) -> AgentRow | None:
    row = jsonio.as_object(value=raw)
    if row is None:
        return None
    pane_id = _text(row=row, key="pane_id")
    if not pane_id:
        return None
    name = _text(row=row, key="name") or _text(row=row, key="title") or pane_id
    return AgentRow(name=name, pane_id=pane_id, status=_text(row=row, key="agent_status"))


def agent_rows(*, result: dict[str, object]) -> tuple[AgentRow, ...] | None:
    """Every listed agent, or None if ANY row is unreadable."""
    raw_rows = jsonio.as_list(value=result.get("agents"))
    if raw_rows is None:
        return None
    parsed = tuple(_agent_row(raw=raw) for raw in raw_rows)
    if any(row is None for row in parsed):
        return None
    return tuple(row for row in parsed if row is not None)

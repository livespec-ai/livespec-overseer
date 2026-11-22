"""The exit of a pass that could not read the active account's usage.

Moved out of `caam_anthropic_pass`, which sits against its LLOC ceiling.
"""

from __future__ import annotations

from caam_anthropic_finish import finish
from caam_decide_context import DecisionContext
from caam_decision import ProfileUsage
from caam_pass_publish import PassPublication, complete_publications
from caam_pass_seams import PassSeams
from caam_pass_table import pass_table_lines

__all__: list[str] = ["finish_unreadable_active"]


def finish_unreadable_active(
    *,
    context: DecisionContext,
    profiles: tuple[ProfileUsage, ...],
    active_name: str,
    seams: PassSeams,
    publication: PassPublication,
    protection_floors: dict[str, float],
) -> int:
    # Published AFTER the report is written and the state persisted, and
    # published at all because spec.md requires a pass that fully resolved
    # the identity but could not read its quota to publish anyway: the
    # identity is known and the missing figures bear only on the report.
    code = finish(
        code=2,
        state=context.state,
        state_path=context.state_path,
        save=seams.save_state,
        stdout=context.stdout,
        lines=(
            *pass_table_lines(profiles=profiles, active_name=active_name, now=context.now),
            f"FAIL cannot read usage for active profile {active_name}",
        ),
    )
    return complete_publications(
        publication=publication,
        code=code,
        profiles=profiles,
        interactive_name=active_name,
        state=context.state,
        protection_floors=protection_floors,
    )

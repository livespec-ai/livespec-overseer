"""The scheduled pass's non-decision alert observations."""

from __future__ import annotations

from caam_anthropic_flags import scheduled_pass
from caam_decide_context import DecisionContext
from caam_pass_dark_login import observe_pass_dark_login_alerts
from caam_pass_factory_probe import observe_pass_factory_probes
from caam_pass_seams import PassSeams

__all__: list[str] = ["observe_pass_alerts"]


def observe_pass_alerts(*, context: DecisionContext, seams: PassSeams) -> None:
    """Report dark-login and scheduled factory-probe conditions outside selection."""
    observe_pass_dark_login_alerts(context=context, post=seams.push_post)
    if scheduled_pass(flags=context.flags):
        observe_pass_factory_probes(context=context, fetcher=seams.fetcher, post=seams.push_post)

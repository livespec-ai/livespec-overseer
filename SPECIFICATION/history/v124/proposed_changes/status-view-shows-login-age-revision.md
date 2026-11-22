---
proposal: status-view-shows-login-age.md
decision: accept
revised_at: 2026-11-22T11:50:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Delegated decision (revise_decision_mode: delegated; coordinator ruling R301). ACCEPT VERBATIM. The proposal narrowly lifts the deferral of login age, mint time and lifetime-cap warning rows for the status command, which the spec's own 'Login age and the lifetime cap' clause already requires of the report; account limits, factory credential probes, undelivered push alerts, forwarded refusals and remote sessions stay deferred. The behavior has a BCP14 clause and a Gherkin scenario, is placed in spec.md and scenarios.md per the authoring splits, and touches none of the other pending proposals (nothing in the enrolled-host-delivery-host-ahead-state clauses changes). The scenario carries a TODO coverage row and debt row owned by overseer-tlwdmm.

## Resulting Changes

- spec.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-22T11:49:30Z
verdict: NO BLOCKERS
proposal_stem: status-view-shows-login-age
content_digest: e92c0c6f17558ae176d39fbc685e016d724ec715c08801dcf91ea8b20d5cf4fe

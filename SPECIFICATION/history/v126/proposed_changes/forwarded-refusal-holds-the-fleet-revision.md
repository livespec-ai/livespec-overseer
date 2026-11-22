---
proposal: forwarded-refusal-holds-the-fleet.md
decision: accept
revised_at: 2026-11-22T14:24:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Delegated decision (revise_decision_mode: delegated). ACCEPT VERBATIM. Lifts the v122 deferral of forwarded refusals per the maintainer ruling on ledger epic overseer-iyfjbo: a usage-limit refusal on any listed host holds the active account fleet-wide, but only when LEGITIMATE (authenticated as the listed host's own observation over the verified ssh push session, and verified as a real usage-limit refusal of the current active account, not stale); otherwise ignored and reported, never carrying credential material. Conflicts with no ratified heading: Remote sessions (tracking and model enforcement) stays deferred, Transport host-key verification is relied on, the role-holder-never-named rule is preserved, and settling-claim re-read semantics are reused. Five scenarios added with TODO coverage and debt rows owned by overseer-tykydt. Other pending proposals untouched.

## Resulting Changes

- spec.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-22T14:24:37Z
verdict: NO BLOCKERS
proposal_stem: forwarded-refusal-holds-the-fleet
content_digest: 0d0d38b4b058fedb0d9d44868d75fdb83d89bf9267319fcbb660791bb76cff2d

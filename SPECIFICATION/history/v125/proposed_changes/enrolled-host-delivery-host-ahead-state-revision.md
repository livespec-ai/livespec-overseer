---
proposal: enrolled-host-delivery-host-ahead-state.md
decision: accept
revised_at: 2026-11-22T13:48:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Delegated decision (revise_decision_mode: delegated). ACCEPT VERBATIM. Adds a closed STATE 'ahead' and has the service move its counter FORWARD past a host-applied sequence, keeping the retry rule intact; conflicts with no ratified heading (Deliveries never move backwards, Moving the role and the retry rule are unchanged or reinforced). Trigger is the observed host answer, so it covers every cause of a lagging counter including every role handover: a new holder with counter 83 against hosts at 84 reads 'stale-sequence 83 host-applied 84', writes the counter to 84 and issues 85, with no hand edit of delivery-sequence.json. Four scenarios added with TODO coverage and debt rows owned by overseer-ceehcd. The forwarded-refusal-holds-the-fleet proposal is untouched.

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
reviewed_at: 2026-11-22T13:48:05Z
verdict: NO BLOCKERS
proposal_stem: enrolled-host-delivery-host-ahead-state
content_digest: 0c282355fb0b18f2c14eeb43df5900b544136188c34802e013c9aa71e7915608

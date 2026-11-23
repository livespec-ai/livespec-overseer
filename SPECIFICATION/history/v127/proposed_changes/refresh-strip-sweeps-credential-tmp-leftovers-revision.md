---
proposal: refresh-strip-sweeps-credential-tmp-leftovers.md
decision: accept
revised_at: 2026-11-23T07:28:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Delegated decision (revise_decision_mode: delegated). ACCEPT VERBATIM. Extends contracts.md Enrolled-host delivery, Moving the role, step 3 so the refresh-token removal also covers ~/.claude/.credentials.json.tmp.* leftovers of interrupted atomic credential writes (a live leftover holding a refresh token was found on a listed host, breaching the plan epic overseer-iyfjbo bullet that no listed host other than the role holder holds a refresh token). Behaviour is stated as MUST clauses with a Given/When/Then scenario per the authoring discipline; value-free read-back, mode preserved, dry run changes nothing. Conflicts with no ratified heading. Debt row owned by overseer-i5zd7r.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-23T07:28:30Z
verdict: NO BLOCKERS
proposal_stem: refresh-strip-sweeps-credential-tmp-leftovers
content_digest: 63e8d2b5aba16d2f16b113d904757289bed1fa69c09707a82be9ca0fc2e9c1fe

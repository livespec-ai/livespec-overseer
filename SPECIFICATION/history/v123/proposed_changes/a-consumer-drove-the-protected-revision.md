---
proposal: a-consumer-drove-the-protected.md
decision: modify
revised_at: 2026-11-22T09:19:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Delegated decision (revise_decision_mode: delegated; coordinator ruling R301 decisions A-C, recorded verbatim in the commit and PR). MODIFY, not accept and not reject: the safety promise (one published protection floor that every selector reads, and a refusal naming account and floor) is sound and is kept, but the proposal as filed had four defects, each fixed here. (a) Terms: 'protected-accounts record', 'numbered credential slot' and 'spender' were undefined; the text now uses the spec's existing CREDENTIAL CONSUMER (spec.md Publication clauses) and defines the PUBLISHED PROTECTION FLOORS in place. (b) Contradiction: 'an account above its floor MUST stay selectable' contradicted 'A protected account MUST NOT be selected while any unprotected account is eligible'; it is replaced by 'the floor alone never excludes an account above it', and such an account stays subject to every rotation rule including that ordering. (c) Units: the floor is stated as a share of the weekly allowance and headroom as usable headroom net of the floor, matching spec.md, and the scenarios give the floor its unit (10 percent of weekly allowance). (d) Placement: the normative floor semantics move into spec.md beside the protection-floor clauses; contracts.md keeps only the publication contract (the protection-floors record, its single writer, its readers, and what a reader must do). Naming clash: spec.md already defines a 'short-window floor' under Rotation triggers; the new clause says it uses 'protection floor' throughout and does not rename the short-window floor, since a rename would exceed the text of this proposal. Reviewer nits not adopted (non-blocking, left for a later proposal): the match key between a consumer's account and a record entry, treatment of a stale record, and a dedicated absent-record scenario. Scenarios carry TODO coverage rows owned by overseer-kzmmn7.

## Modifications

spec.md: new clause 'A protection floor MUST be published once and MUST bind every selection of the account' after the weekly-reserve-release clause (floor as share of weekly allowance, headroom net of floor, refusal naming account and floor, floor alone never excludes an account above it, subject to every rotation rule). contracts.md: 'Published protection floors' publication contract in The account-rotation operation, replacing the proposed 'The published protection floor' subsection in the credential-provider operation. scenarios.md: three scenarios with units replace the two proposed.

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
reviewed_at: 2026-11-22T09:18:30Z
verdict: NO BLOCKERS
proposal_stem: a-consumer-drove-the-protected
content_digest: b3f85adc50d8b9f86e001dba416cfa5d8d5d24ef317cc63cd7783234c1d6085d

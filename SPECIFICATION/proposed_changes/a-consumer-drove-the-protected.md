---
topic: a-consumer-drove-the-protected
author: claude-sonnet-5-5
created_at: 2026-11-22T07:30:38Z
---

## Proposal: A protected account has one published protection floor that every selector reads and a refusal names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under contracts.md section 'The LLM credential-provider operation', add a clause that a per-account protection floor has exactly one published source (caam's protected-accounts record), that every consumer selecting a numbered credential slot (the dispatcher, a judge, a seat, a spender) reads the floor from it and applies no other, and that a selection at or below the floor is refused with a line naming the account and the floor while an account above its floor stays selectable. Add two scenarios to scenarios.md.

### Motivation

Work item overseer-kzmmn7: a consumer drove a protected account past its protection floor, and the maintainer ruled this should never happen; coordinator ruling R301 (2026-11-22) classed it a real contract change, a safety promise about money, not an internal detail. What the spec already says: spec.md 'A protected account MUST retain its own weekly floor' and 'A protection floor MUST NOT be released by the weekly reserve's release' bind the caam rotation operation only, which governs the ACTIVE-account rotation and its own candidate selection. Existing scenarios (for example 'A factory account at its protection floor is replaced on the next pass' and the protected-set scenarios) pin that rotation behavior. Nothing yet says that OTHER consumers which select a numbered credential slot (a dispatch, judge or seat) read the same floor from one source, and nothing requires a refusal that names the account and the floor. That gap is what lets one selector apply a different floor, or none, to an account that another selector protects. This proposal extends the existing floor contract to every selector rather than restating it. The proposal states no account's spend or usage amount.

### Proposed Changes

Two edits.

1. SPECIFICATION/contracts.md, section '## The LLM credential-provider operation': add a third-level subsection '### The published protection floor' (placed after '### Shared lifecycle terminology') with this text.

**A per-account protection floor MUST have exactly one published source.** The source is caam's protected-accounts record, whose floor semantics are those of spec.md 'A protected account MUST retain its own weekly floor'. Every consumer that selects a numbered credential slot, including the dispatcher, a judge, a seat and any spender, MUST read an account's floor from that source and MUST NOT apply a different floor, a private default or an absent floor to the same account. A consumer that cannot read the published source MUST refuse to select a protected-account slot rather than assume a floor.

**A selection at or below the published floor MUST be refused.** A dispatch, judge or seat that attempts to select an account whose remaining headroom is at or below that account's published protection floor MUST be refused, and the refusal line MUST name the account and the floor. An account above its floor MUST stay selectable. This rule MUST NOT weaken any rotation, reserve or ordering rule in spec.md; it adds a refusal at selection time for consumers other than the caam rotation operation.

2. SPECIFICATION/scenarios.md: append these two scenarios.

## Scenario: A selection at or below the published protection floor is refused naming the account and floor

```gherkin
Given an account whose published protection floor is 10
And its remaining headroom is at or below 10
When a dispatch, judge or seat attempts to select it
Then the selection MUST be refused
And the refusal line MUST name the account and the floor
And an account above its floor MUST stay selectable
```

## Scenario: Every selector reads the one published protection floor

```gherkin
Given caam publishes a per-account protection floor
When any consumer selecting a numbered credential slot evaluates that account
Then it MUST use that published floor
And it MUST NOT apply another
```


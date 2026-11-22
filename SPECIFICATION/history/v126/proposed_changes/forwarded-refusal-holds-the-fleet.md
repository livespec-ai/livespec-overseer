---
topic: forwarded-refusal-holds-the-fleet
author: claude-sonnet-5-5
created_at: 2026-11-22T13:10:00Z
---

## Proposal: A legitimate usage-limit refusal observed on any listed host holds the active account fleet-wide

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Lifts the v122 deferral of forwarded refusals. A usage-limit refusal observed on ANY listed host holds the active account fleet-wide, exactly as a refusal on the role holder does, PROVIDED the forwarded refusal is guaranteed legitimate. Legitimacy is stated as a MUST with two conjuncts: the refusal is authenticated as that listed host's own observation, and it is verified as a real usage-limit refusal of the CURRENT active account. A refusal failing either conjunct MUST be ignored and reported.

### Motivation

Maintainer ruling recorded verbatim on ledger epic overseer-iyfjbo (comment "MAINTAINER RULING, VERBATIM", 2026-11-22 12:53). spec.md §"Account rotation and quota supervision" **Forwarded refusals**, **Listing a host does not change the selection rules** and §"Status command" **Deferred to a later revision** defer forwarded refusals until push runs on every reachable Linux host, so today a refusal on a listed host reaches the operation only through account-wide usage readings, which can lag the refusal. The ruling lifts that deferral, on the condition that a forwarded refusal can never hold the fleet illegitimately: a spoofed, stale, wrong-account or misclassified report would otherwise park every host on a healthy account or hide a real exhaustion.

### Proposed Changes

### spec.md §"Account rotation and quota supervision", **Forwarded refusals**

Replace the paragraph with:

> **Forwarded refusals.** A usage-limit refusal observed on any listed host MUST hold the active account fleet-wide: the role holder MUST treat a LEGITIMATE forwarded refusal as a refusal on the role holder, so the account is REFUSAL-HELD, the refusal trigger applies, and the settling, reset and reporting clauses apply to it exactly as they do to a refusal attributed from a tracked session on the role holder. A forwarded refusal is LEGITIMATE only if BOTH of the following hold:
> - It MUST come from a listed host and MUST be authenticated as that host's own observation, so that no other process, no other host and no unlisted machine can produce one.
> - It MUST be verified as a real usage-limit refusal of the CURRENT active account: it MUST name the account that is active on the role holder at the time of verification, it MUST be recent enough that it was observed while that account was active and after any settling claim's re-read recorded against that account, and it MUST be classified as a usage-limit refusal by the same test the operation applies to a refusal on the role holder, so that an authentication error, a revoked or expired credential, a refusal of a different account and a stale message are none of them a usage-limit refusal.
>
> A forwarded refusal that fails either condition MUST be ignored: it MUST NOT hold any account, MUST NOT arm the refusal trigger, and MUST be reported, naming the host, the condition that failed and, where known, the account it named. A forwarded refusal MUST NOT carry or be accompanied by any credential material.

### spec.md §"Account rotation and quota supervision", **Which credential a refusing session used**

Replace the second bullet with:

> - A session on a listed host is not a tracked session in this revision, and no refusal it records is attributed from that session directly; a refusal on a listed host reaches the operation only as a forwarded refusal, which **Forwarded refusals** admits only when legitimate.

### spec.md §"Account rotation and quota supervision", **Listing a host does not change the selection rules**

Replace the last sentence ("In this revision, listing a host does not widen ... state that deferral.") with:

> Listing a host widens the set of refusals the operation observes only as **Forwarded refusals** states; it does not widen the set of sessions whose models those rules observe, which **Remote sessions** states.

### spec.md §"Status command", **Deferred to a later revision**

Replace "Refusals forwarded from listed hosts, and tracking" with "Tracking" and delete the reference to **Forwarded refusals** in the same sentence, so the paragraph defers only tracking and model enforcement of sessions on listed hosts, as **Remote sessions** states.

### contracts.md §"Enrolled-host delivery"

Add a paragraph after **Transport**:

> **Forwarded refusals.** A listed host's observation of a usage-limit refusal MUST reach the role holder only on the existing ssh session the delivery push opens, in the reply the role holder reads from that session, never on a channel the host opens to the role holder, since a listed host's configuration never names the role holder. The role holder MUST treat the reply as the host's own observation only while the session's ssh host key verified as **Transport** requires, and MUST NOT treat any other input, including a file, a message or a process on the role holder, as a forwarded refusal. The forwarded refusal MUST name the observing host, the account it was observed against by stable account identifier, the time it was observed, and the window, reported reset time and refusal class the host's session recorded, and MUST contain no credential material. The role holder MUST apply spec.md **Forwarded refusals** to it before it holds any account. This section does not fix a wire format beyond these fields and this authentication requirement.

### scenarios.md, new scenarios in §"Account rotation and quota supervision"

```gherkin
## Scenario: A legitimate forwarded refusal holds the active account fleet-wide

Given a listed host whose ssh host key verified
And the active account on the role holder is account A
And that host forwards a usage-limit refusal observed against account A while A was active

When the rotation operation evaluates the forwarded refusal

Then account A is refusal-held exactly as a refusal on the role holder would hold it
And the refusal trigger applies to account A
And the operation reports the hold as originating from that listed host

## Scenario: A forwarded refusal for a non-active account is ignored

Given the active account on the role holder is account A
And a listed host forwards a usage-limit refusal observed against account B

When the rotation operation evaluates the forwarded refusal

Then no account is held by it
And the refusal trigger does not fire
And the operation reports that the forwarded refusal was ignored because it did not name the active account

## Scenario: A stale forwarded refusal is ignored

Given the active account on the role holder is account A
And a settling claim's re-read on account A was recorded after a listed host's forwarded refusal was observed

When the rotation operation evaluates the forwarded refusal

Then account A is not held by it
And the operation reports that the forwarded refusal was ignored as stale

## Scenario: An unauthenticated forwarded refusal is ignored

Given a refusal report that does not arrive on a push session whose ssh host key verified
Or that names a host that is not a listed host

When the rotation operation evaluates the report

Then it is not a forwarded refusal and holds no account
And the operation reports that it was ignored, naming the failed condition

## Scenario: A misclassified authentication error is not a usage-limit refusal

Given a listed host forwards a refusal that the operation's refusal test classifies as an authentication error rather than a usage-limit refusal

When the rotation operation evaluates the forwarded refusal

Then no account is held by it
And the operation reports that the forwarded refusal was ignored because it was not a usage-limit refusal
```

These scenario headings are new, so revise MUST add `tests/heading-coverage.json` entries for them in the same change; the `test` MAY be `"TODO"` naming the implementing work item.

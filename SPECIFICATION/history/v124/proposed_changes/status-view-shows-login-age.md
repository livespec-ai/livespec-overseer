---
topic: status-view-shows-login-age
author: claude-sonnet-5-5
created_at: 2026-11-22T07:51:13Z
---

## Proposal: The status command shows login age, mint time and lifetime-cap warnings

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/scenarios.md

### Summary

Under spec.md section 'Enrolled-host credential delivery', narrowly lift the deferral for the login age, mint time and lifetime-cap warning rows of the status command: remove 'login age and lifetime-cap warnings' from the 'Deferred to a later revision' sentence, and add to the 'Status command' paragraph a MUST that the status command on the role holder shows, for every managed account, its current login age and mint time and the lifetime-cap warnings the operation's own report gives. Account limits, factory credential probes, undelivered push alerts, forwarded refusals and remote sessions stay deferred. Add one scenario to scenarios.md.

### Motivation

Work items overseer-tlwdmm (split from overseer-oomnmk) and coordinator ruling R301 (2026-11-22). What the deferral blocks today: spec.md 'Login age and the lifetime cap' already requires the operator-facing REPORT to show each account's login age and mint time and to warn near the cap, and the login-record store and the report are being delivered (PR #3208, overseer-oomnmk). But the 'Deferred to a later revision' paragraph says the status command defines no rows for login age and lifetime-cap warnings, so no implementation may add them and no scenario can pin them; the operator who runs the status command, which is the one view that shows delivery state, cannot see how old each login is or that a cap warning is active. The history (SPECIFICATION/history, v097-v116) and the proposals in flight (PR #3207 protection floor, PR #3093 Parameter Store records, PR #3058 scratch profile seeding, and the pending files under proposed_changes) were checked: all carry login age only for the report or the scenario 'A recorded login shows its age in the report', and none lifts this deferral or adds status-command rows, so this proposal does not duplicate them. This proposal states no account's spend or usage.

### Proposed Changes

Three edits.

1. SPECIFICATION/spec.md, section '## Enrolled-host credential delivery', paragraph '**Deferred to a later revision.**': replace 'for account limits, login age and lifetime-cap warnings, factory credential probes or undelivered push alerts' with 'for account limits, factory credential probes or undelivered push alerts'. Everything else in the paragraph, including the forwarded-refusals and remote-sessions deferral, stays unchanged.

2. SPECIFICATION/spec.md, same section, paragraph '**Status command.**': append this text after the existing last sentence.

The status command on the role holder MUST also show, for every managed account, that account's current login age and mint time, marked as a lower bound when the mint time is `first-seen`. It MUST show a lifetime-cap warning for every account for which the operation's own report warns under **Login age and the lifetime cap**, using the same rule: while the lifetime cap is unset the status command MUST state that the lifetime cap is not yet measured and MUST NOT show a warning. These rows MUST contain no credential material.

3. SPECIFICATION/scenarios.md: add, directly after '## Scenario: A recorded login shows its age in the report', this scenario.

## Scenario: The status command shows each account's login age and mint time

Given the operator has recorded a login for an account and the role holder's report shows its login age

When the operator runs the status command on the role holder

Then it MUST show that account's current login age and mint time

And a first-seen age MUST be marked as a lower bound

And with the lifetime cap unset it MUST state the cap is not yet measured and show no warning

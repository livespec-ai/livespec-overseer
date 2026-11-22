---
topic: refresh-strip-sweeps-credential-tmp-leftovers
author: claude-sonnet-5-5
created_at: 2026-11-22T19:58:30Z
---

## Proposal: Step 3 of moving the role also sweeps credential-file temporary leftovers

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend contracts.md Enrolled-host delivery, Moving the role, step 3 so the removal of every managed account's refresh token also covers the temporary leftovers Claude Code's atomic credential writes leave beside the live credential (`~/.claude/.credentials.json.tmp.*`), and add one scenario for it.

### Motivation

Step 3 says to remove every managed account's refresh token from the old machine, but names no file set. A stale `~/.claude/.credentials.json.tmp.<suffix>` leftover from an interrupted atomic write was found on a listed host still holding a claudeAiOauth refresh token, which breaches the plan epic overseer-iyfjbo bullet that no listed host other than the role holder holds a refresh token for a managed account. The strip tool covers only the live credential and the account manager's snapshots and archives, so the sweep of leftovers has no ratified heading. Work item overseer-i5zd7r extends the tool and needs a heading to cite.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, section "Enrolled-host delivery", immediately after the paragraph that begins `Step 3 MUST complete before step 4`, insert this paragraph:

**Step 3 sweep.** Step 3's removal MUST also cover every temporary leftover of an atomic credential write beside the live credential, that is every file matching `~/.claude/.credentials.json.tmp.*`. A leftover holding a refresh token MUST have that token removed, every other key kept and the file mode kept. A leftover holding no refresh token MUST be left unchanged. A dry run MUST report what it would change and change nothing. The read-back MUST list file names only and MUST NOT print any credential value. The sweep MUST exit non-zero while any such file still holds a refresh token.

2. In `SPECIFICATION/scenarios.md`, immediately after the scenario `## Scenario: Moving the credential-rotation role changes nothing on an enrolled host`, insert this scenario, verbatim:

## Scenario: The refresh-token strip also sweeps credential-file temporary leftovers

Given a machine that is no longer the role holder, whose `~/.claude` directory holds one `.credentials.json.tmp.*` file carrying a refresh token among other keys and another carrying none

When the operator runs the refresh-token strip with `--dry-run`

Then it reports the file that holds a refresh token by name, changes no file, and exits non-zero

When the operator then runs the strip without `--dry-run`

Then the refresh token is removed from the file that held one, its other keys and its file mode are unchanged, and the file that held none is unchanged

And the read-back lists file names only and prints no credential value

And a following run reports no file holding a refresh token and exits zero


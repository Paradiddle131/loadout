# Autopilot profile — <repo>

<!-- Copy to the target's docs/agents/autopilot.md. Keep it under ~60 lines; each slot is optional and defaults as SKILL.md § Profile slots says. -->

Unattended cloud wakes on this repo follow the `cloud:autopilot` skill (if missing, read `cloud/skills/autopilot/SKILL.md` in the collection's clone, which `~/.claude/CLAUDE.md` names) with the slots below.
A wake with no `~/.claude/cloud-target` (the environment's setup didn't run) first runs `bash <clone>/cloud/setup.sh <repo>`.
The routine prompt: "Follow `docs/agents/autopilot.md` in <repo> and do one wake." (optionally "on #n").
Standing permission (owner, <date>): <what wakes may do without asking>.
Every item is one branch `claude/<n>-<slug>` and one PR, reviewed by the `review` skill and merged by the wake when gated and reviewed, unless the merge policy holds it.

<!-- A profile written for the retired train delivery (`Delivery: train …`, `in-train`, `AUTOPILOT_TRAIN`): set `Mode: paused`; have the open train PR reviewed and merged, or closed (then swap `in-train` back to `agent:ready` on its issues); delete the label, the Delivery slot and `AUTOPILOT_TRAIN`; move the train body's owner decisions to `needs-owner` issues and its steering lines to the Digest issue; then unpause. -->

## Merge policy

<none: the wake merges when gated and reviewed | what holds a reviewed PR and who lifts it, e.g. `needs-local-verify` until the local checklist passes; `export AUTOPILOT_HOLD_LABELS="<label> …"` for labels of your own>.

## Review

Sensitive paths and what each tier adds: `REVIEW.md` at the repo root (the `review` skill reads it).

## Digest

Steering lines (SKILL.md § Steering) at the top of pinned issue #<n>'s body, which only the owner edits: `Mode: full` and `Owner lane: none`. Open owner questions are the `needs-owner` issues.

## Queue

1. <epic or map link>: its sub-issues in order.
2. <next source>.

## Gates

`cloud` (every wake runs them through the gate stamp; counts in the handoff):
- <fast command: lint, unit tests, static validation>

`local` (an agent on another machine runs them from the handoff's checklist; leave the list out when cloud is the only environment):
- <long command: end-to-end suite, image build, cluster check> — expect: <output>

## Never

- <repo-specific prohibition, with the positive rule beside it>.

## Known conditions

<!-- One line each: symptom, the check that tells it apart, workaround, `seen <dates>`. A repeat files a fix issue; the fixing PR deletes the line. Conditions every repo shares go to the collection's cloud/CLAUDE.md instead. -->
- <symptom>: <check>; <workaround>; seen <date>.

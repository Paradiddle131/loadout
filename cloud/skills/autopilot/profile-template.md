# Autopilot profile — <repo>

<!-- Copy to the target's docs/agents/autopilot.md. Keep it under ~60 lines; each slot is optional and defaults as SKILL.md § Profile slots says. -->

Unattended cloud wakes on this repo follow the `cloud:autopilot` skill (if missing, read `cloud/skills/autopilot/SKILL.md` in the collection's clone, which `~/.claude/CLAUDE.md` names) with the slots below.
A wake with no `~/.claude/cloud-target` (the environment's setup didn't run) first runs `bash <clone>/cloud/setup.sh <repo>`.
The routine prompt: "Follow `docs/agents/autopilot.md` in <repo> and do one wake." (optionally "on #n").
Standing permission (owner, <date>): <what wakes may do without asking>.

## Delivery

<`train claude/<branch>`: one open train PR, `export AUTOPILOT_TRAIN=claude/<branch>` before the scripts (the default when every gate runs on cloud) | `per-issue`: branch `claude/<n>-<slug>`, one PR per issue>.

## Digest

Open owner questions: <the train PR body's `## Owner decisions` | the body of issue #n>, under the steering lines `Mode: offline` and `Owner lane: none` (SKILL.md § Steering).

## Merge policy

<who merges; what a finished PR waits for, e.g. `needs-local-verify` and the owner's local checklist>.

## Queue

1. <epic or map link>: its sub-issues in order.
2. <next source>.

## Gates

`cloud` (every wake runs them; counts in the handoff):
- <fast command: lint, unit tests, static validation>

`local` (an agent on another machine runs them from the handoff's checklist; leave the list out when cloud is the only environment):
- <long command: end-to-end suite, image build, cluster check> — expect: <output>

## Never

- <repo-specific prohibition, with the positive rule beside it>.

## Known conditions

<!-- One line each: symptom, the check that tells it apart, workaround, `seen <dates>`. A repeat files a fix issue; the fixing PR deletes the line. Conditions every repo shares go to the collection's cloud/CLAUDE.md instead. -->
- <symptom>: <check>; <workaround>; seen <date>.

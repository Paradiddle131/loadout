# Review

What the `review` skill's `tier.sh` reads for a change to this collection, from the default branch.
Every repo that imports the collection runs what these paths hold, so a change to them takes the lens reviewers.

## Sensitive
- `ways/**` — the standing practices every adopting repo follows; lenses: claims-auditor, guardrail-reviewer
- `FEEDBACK.md` — the one rule that writes outside the repo being worked on; lenses: guardrail-reviewer
- `agents/**` — the reviewers themselves; lenses: guardrail-reviewer, control-prober
- `skills/review/**` — the landing path and its scripts; lenses: guardrail-reviewer, control-prober
- `skills/delegating/**` — how work is handed out and checked; lenses: guardrail-reviewer
- `cloud/setup.sh` — runs as root at every cloud session start; lenses: guardrail-reviewer
- `cloud/memory.sh` — writes the user-level instructions; lenses: guardrail-reviewer
- `cloud/gcp/**` — the spend guard and its fences; lenses: guardrail-reviewer, control-prober
- `cloud/skills/autopilot/**` — what an unattended run may do and merge; lenses: guardrail-reviewer, control-prober
- `bin/**` — the collection's own checks; lenses: control-prober

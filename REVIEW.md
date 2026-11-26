# Review

What the `review` skill's `tier.sh` reads for a change to this collection, from the default branch.
Every repo that imports the collection runs what these paths hold, so a first review of a change to them runs the sensitive set (correctness-reviewer and guardrail-reviewer) and the lenses a line names.

## Sensitive
- `ways/**` — the standing practices every adopting repo follows; lenses: claims-auditor
- `FEEDBACK.md` — the rules that write outside the repo being worked on
- `agents/**` — the reviewers themselves
- `skills/review/**` — the landing path and its scripts
- `skills/delegating/**` — how work is handed out and checked
- `skills/debrief/**` — what the owner is shown of merges only reviewers read; lenses: claims-auditor
- `cloud/setup.sh` — runs as root at every cloud session start
- `cloud/memory.sh` — writes the user-level instructions
- `cloud/gcp/**` — the spend guard and its fences; lenses: control-prober
- `cloud/skills/autopilot/**` — what an unattended run may do and merge
- `bin/**` — the collection's own checks
- `bin/friction` — posts from every session to this collection's tracker; lenses: leak-hunter
- `cloud/hooks/merge-guard.py` — the merge guard every landing passes; lenses: control-prober

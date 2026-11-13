# Lessons of unattended runs

Why the `autopilot` skill is shaped the way it is: read before changing it or a profile.
Cloud conditions every repo shares live in [`cloud/CLAUDE.md`](../cloud/CLAUDE.md); the evidence behind each line is in the PR that added it (`git log -S`).

## Carry

- One item at a time, each its own branch and PR, sized for one reviewer's pass (Context, Do, Acceptance as a command, Blocked by); long work lands in slices: a PR read in one sitting keeps review real.
- Review between green gates and the merge, by fresh subagents at a tier computed from the paths, findings verified, and never by the author: gates pass work that leaks, and an unattended landing without review once leaked personal data that fresh reviewers found afterwards.
- Three review-and-fix cycles, then park the item with its findings: a finding that survives three fixes is the owner's question, and the wake's time goes further elsewhere.
- The wake merges, through a script the merge guard backs, at the head that was checked: "never merge" in prose left PRs piling up unread, and a rule a hook enforces needs no memory.
- A head behind the default branch takes it in and is stamped again before it merges: two branches can each pass and still collide once both land (the same next tag), and git merges that without a conflict.
- Steering lines sit in a pinned issue only the owner edits, and the open questions are the `needs-owner` label: steering needs no PR, and a list no wake writes cannot drift or race.
- A wake keeps taking items until nothing is pickable: the routine exists to use idle time.
- Claims are leases with a wake id, and the earliest claim wins on re-read: overlapping wakes never double-claim.
- Take new ids at landing, never at orient, or two wakes collide on a number.
- The mechanical steps are scripts with `--dry-run` and tests from the start: prose steps drift, and script bugs surface early.
- Decision packets: at most three questions, A/B/C with one trade-off line each, a recommendation; the owner answers in a few characters and usually takes the recommendation.
- Build ahead on a reversible recommendation instead of idling while a packet waits.
- One handoff comment per PR, edited in place, five lines outside `<details>`; local resume edits the same comment and removes the label.
- PRs waiting on the owner never cap new work; only dependencies do. Stack only on a held PR, targeting its branch: a stack aimed at the default branch merges the held work beneath it.
- Needing the owner's machine to verify never makes work local-only: build it, verify what cloud can, hand off the rest.
- The issue body is the spec: when newer facts change the ask, rewrite the body and cite the source.
- Park what a wake can't advance (`needs-owner`, `blocked: *`) so the next wake doesn't redo it.
- Reproduce first, and say "red before the fix" in the handoff; reality-check a plan's claims against real data.
- File every finding the work did not fix, related ones together; nothing found is left only in a comment.
- Known conditions are one line (symptom, check, workaround, dates), recorded only after a real call confirms one: a second sighting files a fix, and the fix deletes the line.
- A known flake names itself in the test output, and the handoff quotes both counts.
- A bot comment starts with `🤖` when bot and owner share a login.
- One `Went wrong:` line per handoff, kinds named, a delegated agent's error among them: it reads as finished, and no other kind named it.
- The brief leads with sensitive merges (what was checked, what was not), then parked items: once wakes merge, the owner's reading afterwards is the check on the review.

## Drop

- A posted brief comment, heartbeats and a run board: they repeated what claims and PRs said.
- Run feedback after the first few runs and per-run environment probes: fold blockers into known conditions once.
- The train, one long-lived PR the owner merged a few times a day: it grew to thousands of lines per merge, so the sign-off became a formality, and wakes raced on its body.
- A digest kept in two places, or one a wake writes: it drifts, and the next wake races it.
- A cap on new issues a wake: it hid findings behind a number.
- Two label vocabularies, and labels nobody uses.
- A three-tier charter: "non-negotiable" reads as beyond question instead of "ask before crossing" ([`guardrails.md`](guardrails.md)).
- An ADR per step, process ids in checked-in files, and plan, ledger and lessons files: the tree comes to depend on its own history ([`finished.md`](finished.md#decisions)).
- Prose for edge cases that never happen: fold them into the scripts.

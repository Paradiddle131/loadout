# Lessons of unattended runs

Why the `autopilot` skill is shaped the way it is: read before changing it or a profile.
Cloud conditions every repo shares live in [`cloud/CLAUDE.md`](../cloud/CLAUDE.md); the evidence behind each line is in the PR that added it (`git log -S`).

## Carry

- One item at a time, each its own branch and PR, sized for one reviewer's pass (Context, Do, Acceptance as a command, Blocked by); long work lands in slices: a PR read in one sitting keeps review real, and every item stays resumable.
- Review between green gates and the merge, by fresh subagents at a tier the change sets, their findings verified: gates pass work that leaks, and the one unattended landing without review leaked personal data that fresh reviewers, run after it, found.
- The author never writes its own verdict, and a session with no subagent tool leaves the PR unreviewed rather than walking the checklist itself: an author's reading finds what it meant to write.
- Three review-and-fix cycles, then park the item with its findings and take the next: a finding that survives three fixes is a question for the owner, and the wake's time goes further elsewhere.
- The wake merges, by a script that checks both statuses on the head and names that head in the merge: "never merge" in prose left PRs piling up unread, and a check a hook can enforce is one nobody has to remember.
- A head behind the default branch merges it in and is gated and reviewed again before its merge: two branches can each pass and still collide once both land (parallel version bumps, the same next tag), which git merges without a conflict.
- The owner's lines (`Mode`, `Owner lane`) live in a pinned issue only the owner edits, and the open questions are the `needs-owner` label: steering needs no PR and takes effect at the next read, and a list no wake writes cannot drift or race.
- A wake keeps taking items until nothing is pickable: the routine exists to use idle time, and a cap on items or issues stops a wake that could keep working.
- Claims are leases with a wake id, and the earliest claim wins on re-read: overlapping wakes never double-claim.
- Take new ids at landing, never at orient, or two wakes collide on a number.
- The mechanical steps are scripts with `--dry-run` and tests from the start: prose steps drift, and script bugs surface early.
- Decision packets: at most three questions, A/B/C with one trade-off line each, a recommendation; the owner answers in a few characters and usually takes the recommendation.
- Build ahead on a reversible recommendation instead of idling while a packet waits.
- One handoff comment per PR, edited in place, five lines outside `<details>`, gates as a ticked checklist; local resume edits the same comment and removes the label.
- PRs waiting on the owner never cap new work; only dependencies do, and a PR its merge policy holds can be stacked on; any other item starts from the fresh default branch.
- A stacked PR targets the PR below it and is retargeted when that one merges: targeting the default branch early would merge the held work beneath it.
- Needing the owner's machine to verify never makes work local-only: build it, verify what cloud can with host-side stand-ins, hand off the rest.
- The issue body is the spec: when newer facts change the ask, rewrite the body and cite the source.
- Park what a wake can't advance (`needs-owner`, `blocked: *`) so the next wake doesn't redo it.
- Reproduce first, and say "red before the fix" in the handoff.
- Reality-check a plan's claims against real data; a wrong premise becomes a bug issue.
- File every finding the work did not fix, related ones together, an existing issue's as a comment there; bound refill and build-ahead instead: a cap on filing hid findings, and nothing found is left only in a comment.
- Known conditions are one line (symptom, check, workaround, dates): a second sighting files a fix, the fix deletes the line, and the owner may rule one "expected".
- Record a condition only after a real call confirms it; a misleading status command once recorded a false one.
- A known flake names itself in the test output, and the handoff quotes both counts.
- A bot comment starts with `🤖` when bot and owner share a login; answers relayed from a local session count as answers.
- When the whole queue waits on the owner, exit within a minute and say so.
- Take cheap, reversible choices yourself; packet only what is costly to undo or new scope.
- One `Went wrong:` line per handoff, kinds named: the owner's brief after a night of wakes gathers them in one place, which run feedback never did.
- A delegated agent's wrong or unfounded work is a kind of its own: it reads as finished, and no other kind named it.
- The brief leads with sensitive landings (what was checked, what was not), then parked items: once wakes merge, the owner's reading afterwards is the review of the review.

## Drop

- A posted brief comment: nobody reads it; the PR's `Briefed on:` line replaces it.
- Heartbeats and a run board: wakes end well inside a 3-hour lease, and the board repeated what claims and PRs said.
- Run feedback after the first few runs: it repeats the same blockers; fold them into known conditions once.
- Per-run environment probes: probe once per environment.
- A digest kept in two places, which drifts; and one a wake writes, which races with the next wake.
- The train, one long-lived branch and PR the owner merged a few times a day: it grew to dozens of issues and thousands of lines per merge, so the sign-off became a formality, and wakes raced on its body.
- At most three new issues a wake: it hid findings behind a number.
- Two label vocabularies, and labels nobody uses.
- A three-tier charter: "non-negotiable" reads as beyond question instead of "ask before crossing" ([`guardrails.md`](guardrails.md)).
- An ADR per step: most are steps, not forks, and immutability breeds renumbering ([`finished.md`](finished.md#decisions)).
- Process ids (issue, PR, phase, decision) in checked-in files, and plan, ledger and lessons files: the tree comes to depend on its own history, a reader of the code has no tracker, and every decision needs a sweep of the lines that cite it.
- Prose for edge cases that never happen: fold them into the scripts.
- Evidence inside known-condition lines: one line, evidence in the fix issue.

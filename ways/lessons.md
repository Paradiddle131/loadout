# Lessons of unattended runs

Why the `autopilot` skill is shaped the way it is: read before changing it or a profile.
Cloud conditions every repo shares live in [`cloud/CLAUDE.md`](../cloud/CLAUDE.md); the evidence behind each line is in the PR that added it (`git log -S`).

## Carry

- One issue per wake, sized to one wake (Context, Do, Acceptance as a command, Blocked by): wakes stay short and resumable.
- A train suits a repo whose gates all run on cloud; per-issue PRs with a local checklist suit one whose real checks need the owner's machine, which catches defects cloud runs miss.
- Switch a profile to a train the day its `local` gates go: a night of hourly per-issue wakes leaves the owner a stack of PRs to retarget, parallel version bumps, and collisions git merges without a conflict (two branches taking the same next tag).
- Steer a running routine from lines in the digest (`Mode`, `Owner lane`) instead of switching it off: the owner works beside it, and a line edit takes effect at the next wake.
- Claims are leases with a wake id, and the earliest claim wins on re-read: overlapping wakes never double-claim.
- A moved train is normal: merge and retry; take new ids at landing, never at orient, or two wakes collide on a number.
- The mechanical steps are scripts with `--dry-run` and tests from the start: prose steps drift, and script bugs surface early.
- Decision packets: at most three questions, A/B/C with one trade-off line each, a recommendation; the owner answers in a few characters and usually takes the recommendation.
- Build ahead on a reversible recommendation instead of idling while a packet waits.
- One handoff comment per PR, edited in place, five lines outside `<details>`, gates as a ticked checklist; local resume edits the same comment and removes the label.
- PRs waiting on the owner never cap new work; only dependencies do, and an open PR's branch can be stacked on.
- A stacked PR is retargeted when its base merges, or its merge lands on a dead branch.
- Needing the owner's machine to verify never makes work local-only: build it, verify what cloud can with host-side stand-ins, hand off the rest.
- The issue body is the spec: when newer facts change the ask, rewrite the body and cite the source.
- Park what a wake can't advance (`needs-owner`, `blocked: *`) so the next wake doesn't redo it.
- Reproduce first, and say "red before the fix" in the handoff.
- Reality-check a plan's claims against real data; a wrong premise becomes a bug issue.
- File every out-of-scope finding as an issue; nothing found is left only in a comment.
- Known conditions are one line (symptom, check, workaround, dates): a second sighting files a fix, the fix deletes the line, and the owner may rule one "expected".
- Record a condition only after a real call confirms it; a misleading status command once recorded a false one.
- A known flake names itself in the test output, and the handoff quotes both counts.
- A bot comment starts with `🤖` when bot and owner share a login; answers relayed from a local session count as answers.
- When the whole queue waits on the owner, exit within a minute and say so.
- Take cheap, reversible choices yourself; packet only what is costly to undo or new scope.
- One `Went wrong:` line per handoff, kinds named: the owner's brief after a night of wakes gathers them in one place, which run feedback never did.

## Drop

- A posted brief comment: nobody reads it; the PR's `Briefed on:` line replaces it.
- Heartbeats and a run board: wakes end well inside a 3-hour lease, and the board repeated what claims and PRs said.
- Run feedback after the first few runs: it repeats the same blockers; fold them into known conditions once.
- Per-run environment probes: probe once per environment.
- A digest kept in two places, which drifts; one place per repo.
- Two label vocabularies, and labels nobody uses.
- A three-tier charter: "non-negotiable" reads as beyond question instead of "ask before crossing" ([`guardrails.md`](guardrails.md)).
- An ADR per step: most are steps, not forks, and immutability breeds renumbering ([`finished.md`](finished.md#decisions)).
- Process ids (issue, PR, phase, decision) in checked-in files, and plan, ledger and lessons files: the tree comes to depend on its own history, a reader of the code has no tracker, and every decision needs a sweep of the lines that cite it.
- Issue handoffs that repeat the train line, and unbounded train bodies: one line per issue, evidence in the issue.
- Prose for edge cases that never happen: fold them into the scripts.
- Evidence inside known-condition lines: one line, evidence in the fix issue.

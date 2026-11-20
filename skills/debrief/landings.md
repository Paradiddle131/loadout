# Landings

What landed or waits in the window, so the owner sees every change that only reviewers read, or that none did.
None goes silent: each gets one short line, and the expected ones stay short rather than vanish.

## What gets a line

- Every PR merged, closed unmerged, or still open in the window that is not provably the owner's own (a head under `claude/`, a `🤖` comment or body, or opened by an agent session).
- Every commit on the default branch in the window that no merged PR holds: it landed outside review.

## Order

After the big picture: what touched sensitive paths, what waits on the owner (held, parked, failing, unreviewed, closed unmerged) and any change to how a guardrail is enforced come first; everything else follows, one line each.

## Each line

In plain words: what it does; how it was reviewed and what that review left unchecked; what it waits on, if anything; the issues filed; each steering line of its review, redacted; the link to its record.

- The review is the newest `🤖 Gates` and the newest `🤖 Review` comment by an `OWNER`, `MEMBER` or `COLLABORATOR`; say plainly when either is missing, edited, failing, posted after the merge, or names a commit other than the PR's head.
- The depth that counts is the higher of what that record names and what `tier.sh` gives for the change's own diff (for a merged PR, `--base <merge commit>^1 --head <PR head>`, with `pull/<n>/head` fetched).
- What the review left unchecked is its `Not checked` lines, put plainly on the page, or *not in the record* when it has none.
- A number from a handoff, the author's own account, is shown as *per the handoff*. When unsure what a record means, say so on the line.

# Landings

What landed or waits in the window, so the owner sees every change that only reviewers read, or that none did.
None goes silent: risky and waiting changes get their line in full, and expected ones one short line rather than nothing.

## What gets a line

- Every PR merged, closed unmerged, or still open in the window, unless it is provably the owner's own; a head under `claude/`, a `🤖 Handoff` comment, or an agent session's opening marks it as an agent's.
- Every push to the default branch in the window (`repos/<owner>/<repo>/activity?ref=<default>`) whose commits `repos/<owner>/<repo>/commits/<sha>/pulls` ties to no merged PR: it landed outside review.
- Every force push to the default branch in the window, whatever its commits: name what it removed (`compare/<after>...<before>`) and mark any PR whose merge it undid.

## Order

Landings come after what needs the owner and is not a PR (a run that failed, a cost above zero, an open question).
Among them, first and in full: what touched sensitive paths, what waits on the owner (held, parked, failing, unreviewed, closed unmerged), what landed outside review or was force-pushed away, anything reviewed below its depth or with a record the next section flags, and any change to how a guardrail is enforced.
Then the expected ones, one short line each: what it did and how deep its review went (reviewers passed, or, for a `routine` merge, gates only with no reviewer).

## A full line

In plain words: what it does; its depth and the reviewers run; what that review left unchecked; what it waits on, if anything; the issues filed; each steering line of its review, redacted; the link to its record.

- The review is the newest `🤖 Gates` and the newest `🤖 Review` record by an `OWNER`, `MEMBER` or `COLLABORATOR`, a record being a comment with the `<!-- loadout:<kind> ... -->` marker on its second line, as the merge guard reads it.
  Say plainly when either is missing, edited, malformed, failing, posted after the merge, or names a commit other than the PR's head, or when a newer comment titled like a record has no marker.
- The depth is what `tier.sh` gives for the change's own diff, `--base <the PR's base.sha> --head <PR head>` with `pull/<n>/head` fetched; for a merged PR whose merge commit is not its head, also `--base <merge commit>^1`, taking the higher; for a push, `--base <before> --head <after>`.
  When it is above the record's tier, say the change was reviewed at the lower depth; when `tier.sh` cannot run, say *depth not checked*, with the reason, and put the line first.
- What the review left unchecked is its `Not checked` lines, put plainly, or *not in the record* when it has none.
- A number from a handoff, the author's own account, is shown as *per the handoff*. When unsure what a record means, say so on the line.

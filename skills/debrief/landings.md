# Landings

What landed or waits in the window, so the owner sees every change that only reviewers read, or that none did.
Risky and waiting changes get their line in full, and expected ones one short line rather than nothing.

## What gets a line

Read the default branch's name from `repos/<owner>/<repo>` (`.default_branch`) and its pushes from `repos/<owner>/<repo>/activity?ref=<default>&per_page=100`, following the `after` cursor until an entry is older than the window.
Read the PRs from `repos/<owner>/<repo>/pulls?state=all&sort=updated&direction=desc&per_page=100`, paged by hand with `&page=N` until an entry's `updated_at` is older than the window, and every open PR from `pulls?state=open&per_page=100`, paged to the end, since one nobody touched in the window is still waiting.
The two reads must agree over the window: a `pr_merge` entry in the window whose `after` is no listed PR's `merge_commit_sha` means the PR list is short, and a PR merged into the default branch in the window whose merge commit neither is an entry's `after` nor lies inside a `compare/<before>...<after>` of one means the push list is; say *PRs not checked* or *pushes not checked* in the attention part.

- Every PR merged, closed unmerged, or still open in the window, unless it is provably the owner's own; a head under `claude/`, a `🤖 Handoff` comment, or an agent session's opening marks it as an agent's.
- Every commit a `push` or `force_push` added to the default branch in the window (`compare/<before>...<after>?per_page=100`, paged until its commits number `ahead_by`) that `commits/<sha>/pulls` ties to no merged PR: it landed outside review.
- Every `force_push` to the default branch in the window: say whether the content changed (the two commits' trees differ), name the commits it took off the branch (`compare/<after>...<before>`), and mark each PR that `commits/<sha>/pulls` ties to them, or that the PR list holds with its `merge_commit_sha` or head among them.

## Order

Landings come after what needs the owner and is not a PR (a run that failed, a cost above zero, an open question).
Among them, first and in full: what merged at the `sensitive` tier by its record or its paths, what waits on the owner (held, parked, failing, unreviewed, closed unmerged), what landed outside review or was force-pushed away, anything reviewed below its depth or with a record the next section flags, and any change to how a guardrail is enforced.
Then the expected ones, one short line each: what it did and the reviewers its record names, or *gates only, no reviewer* when it names none; a change whose depth floor is none, merged on its gates record alone, is *gates only, floor none*, not a missing review.

## A full line

In plain words: what it does; its depth and the reviewers run; what that review left unchecked; what it waits on, if anything; the issues filed; each steering line of its review, redacted; the link to its record.

- The review is the newest `🤖 Gates` and the newest `🤖 Review` record by an `OWNER`, `MEMBER` or `COLLABORATOR`, a record being a comment with the `<!-- loadout:<kind> ... -->` marker on its second line, as the merge guard reads it.
  Say plainly when either is missing, edited, malformed, failing, posted after the merge, or names a commit other than the PR's head, or when a newer comment titled like a record has no marker.
- The depth is the record's `depth` against the floor the `review` skill's `scripts/plan.py floor` gives for the change's own diff (for a record without `depth`, its tier against `scripts/tier.sh`'s, which takes the same `--base` and `--head`), the higher of each form that applies: `--base <the PR's base.sha> --head <PR head>` with `pull/<n>/head` fetched; for a merged PR whose merge commit is not its head, also `--base <merge commit>^1`; for a push, `--base <before> --head <after>`, and for a force push also `--base <after> --head <before>`, the side it removed.
  When the floor is above the record's depth (or the tier above its tier), say the change was reviewed at the lower depth; when the script cannot run, say *depth not checked*, with the reason, and put the line first.
- What the review left unchecked is its `Not checked` lines, put plainly, or *not in the record* when it has none.
- A number from a handoff, the author's own account, is shown as *per the handoff*. When unsure what a record means, say so on the line.

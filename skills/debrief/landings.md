# Landings

Which agent PRs a debrief names, so that what only reviewers read reaches the owner.
The merge guard decides what may stay quiet; a debrief never restates its rules.

## The quiet case

A PR stays quiet (one short line, or a count) only when all of these hold:

- it merged in the window;
- run from a clone of its repo with the default branch fetched, `python3 <collection>/cloud/hooks/merge-guard.py --check <owner>/<repo>#<n>` exits 0, so its newest gates and review records pass on its head and the review's tier is not below what its paths give;
- that review record names the `standard` tier.

## Every other PR gets its line

Every other agent PR merged in the window, and every agent PR still open, gets a line of its own; when unsure, give it one.
After the big picture, the attention part opens with these: `sensitive` merges first, then what waits on the owner (held, parked, failing, unreviewed), then the rest, `routine` merges included.
Any change to how a guardrail is enforced gets its line whatever its tier and state.
A PR the guard refused shows its reason in plain words; a merge the guard would have refused landed outside it, which is attention in itself.

Each line, in plain words: what the PR does; its tier and the reviewers run; what its review left unchecked (the verifier's `Not checked` lines, put plainly on the page, as written behind the record's link, or *not in the record* when it has none); the issues filed; each steering line, redacted; and the record's link.
A number from a handoff, the author's own account, is shown as *per the handoff*.

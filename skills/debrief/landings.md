# Landings

How a debrief reads the agent PRs of its window from their records, for the line each one gets.
The owner's reading is the after-the-fact check on what agents merged, so these lines are never left out as "the expected".

## Records

- The records of a PR are its newest unedited `🤖 Gates` comment and its newest unedited `🤖 Review` comment by an `OWNER`, `MEMBER` or `COLLABORATOR`, each carrying its marker, as [`lib.sh`](../review/scripts/lib.sh) defines them for the merge guard.
- A review whose reviewed commit is neither the PR's head nor differs from it only by a clean merge is shown as *for an older head*, never as a pass.
- A handoff is the author's account: a number from it is shown as *per the handoff*, and never fills a record field.
- A record with no `Not checked` section shows *not in the record* for what was left unchecked.

## Which PRs, in this order

Every agent PR merged or open in the window, from its labels and records:

1. **Sensitive merges:** merged at the `sensitive` tier; only reviewers read them before they landed.
2. **Routine merges:** merged at the `routine` tier, with no reviewer: say so.
3. **Unreviewed:** labelled `needs-review`, or open with no review record.
4. **Held:** labelled `owner-merges`, the merge policy's hold label or `needs-local-verify`.
5. **Parked:** labelled `needs-owner` after review, its open findings the reason.
6. **Guardrail changes:** any change, merged or open, to how a guardrail is enforced, whatever its tier.
7. **Standard merges** whose review passed: one short line each, or a count.

## Each line

What the PR does, in plain words, then: its tier, the reviewers run, what the review left unchecked (the verifier's `Not checked` lines put in plain words on the page, as written behind the record's link), the issues filed, and each steering line, redacted.
A sensitive merge's unchecked lines are on the page, not only behind the link.

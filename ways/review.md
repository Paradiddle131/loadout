# Review before landing

How every change reaches the default branch, attended or unattended, so a flaw of judgement is caught before it lands, not after.
Green tests catch what a test was written for; the flaws that ship are leaked data, silently wrong numbers, false claims in docs, over-broad grants and checks that pass on nothing.
Only an independent reader who runs things finds those.

## One landing path

Every change takes it, an urgent one included; the [`review` skill](../skills/review/SKILL.md) is the procedure, and each stage names its step.

1. **Brief** (the [`delegating` skill](../skills/delegating/SKILL.md)): the worker gets the issue and its done-when, which every later stage checks against.
2. **Work in a worktree:** one item, one PR off the default branch; long work lands in slices, each its own PR, with no long-lived collecting branch.
3. **Gate stamp** (step 2): a commit status on a clean pushed head, because a typed test count is not evidence.
4. **Find** (steps 1 and 3): the changed paths set the tier, never the author or the size of the change; fresh reviewers, one lens each, get the diff and the quoted issue, never the author's summary, and verify by running things.
5. **Verify and rank** (step 4): a reviewer asked to find problems always finds something, so only a reproduced `must-fix` is acted on.
6. **Fix, capped** (step 5): one cap counts fix rounds, red stamps and integrate rounds alike, so no item loops forever, and a cap ends an item, never the session.
7. **Integrate and re-gate** (step 6): the review reads the head with the default branch merged in, so the verdict covers what will land.
8. **Verdict on record** (step 7): the verifier's raw output on the PR, naming the reviewed commit and the head, and a second commit status; the author never reviews its own change, and records only a `routine` verdict, which the script's tier decides.
9. **Merge** (step 8): an agent merges only on both statuses, and never a guardrail change without the owner's answer cited; where a repo's own rule keeps the merge with the owner (this collection's [`FEEDBACK.md`](../FEEDBACK.md) does for its own PRs), the path ends at the verdict, the PR listed as ready.
10. **Owner's brief** (step 9): the lead is reviewed too, every unfixed finding is an issue, and a decision that weakens how a guardrail is enforced goes to the owner ([`guardrails.md`](guardrails.md)).

# Review before landing

How every change reaches the default branch, attended or unattended, so a flaw of judgement is caught before it lands, not after.
Green tests catch what a test was written for; the flaws that ship are leaked data, silently wrong numbers, false claims in docs, over-broad grants and checks that pass on nothing.
Only an independent reader who runs things finds those.

## One landing path

Every change takes it, an urgent one included; the [`review` skill](../skills/review/SKILL.md) is the procedure, and each stage names its step.

1. **Brief** (the [`delegating` skill](../skills/delegating/SKILL.md)): the author, the lead itself or a worker it briefs, gets the issue and its done-when, which every later stage checks against.
2. **Work in a worktree:** one item, one PR off the default branch; long work lands in slices, each its own PR, with no long-lived collecting branch.
3. **Gate stamp** (step 2): a record on the PR for a clean pushed head, because a typed test count is not evidence.
4. **Find** (steps 1 and 3): the changed paths and the repo's `REVIEW.md` set the tier and the depth floor (none, light, focused or full), never the author or the size of the change; a script plans the lenses and each one's effort from them, which the lead may raise, never lower; fresh reviewers, one lens each, get the diff and the quoted issue, never the author's summary, and verify by running things.
5. **Verify and rank** (step 4): a reviewer asked to find problems always finds something, so only a reproduced `must-fix` the verifier lists with the harm it names is acted on.
6. **Fix, capped** (step 5): one cap counts fix rounds, red stamps and integrate rounds alike, so no item loops forever, and a cap ends an item, never the session.
   A fix round reruns only the lenses its must-fix findings came from, correctness and the verifier, so a round costs what it answers; the whole set returns when the fix touches a file no earlier round reviewed.
   On a sensitive change a fix round changes only the listed must-fix findings, and its nits go to one issue, so a round adds no new surface to review.
   A class found again after its fix goes to a rethink, not another patch.
7. **Integrate and re-gate** (step 6): the review reads the head with the default branch merged in, so the verdict covers what will land.
8. **Verdict on record** (step 7): the verifier's raw output on the PR, naming the reviewed commit and the head, as a second record; the author never reviews its own change; it may post the verifier's output unedited, and its own verdict only where the script's depth floor is none.
9. **Merge** (step 8): an agent merges only on both records (the gates record alone where its depth floor is none and the merge guard runs in a clone holding the head and GitHub's tip of the default branch; where the clone lacks that tip, fetch it, or on routine paths record `verdict.sh --tier routine`), and never a guardrail change without the owner's answer cited; where a repo's own rule keeps the merge with the owner, the path ends at the verdict, the PR listed as ready.
10. **Owner's brief** (step 9): the lead is reviewed too, every unfixed finding is an issue, and a decision that weakens how a guardrail is enforced goes to the owner ([`guardrails.md`](guardrails.md)).

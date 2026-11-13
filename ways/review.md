# Review before landing

How every change reaches the default branch, attended or unattended, so a flaw of judgement is caught before it lands, not after.
Green tests catch what a test was written for; the flaws that ship are leaked data, silently wrong numbers, false claims in docs, over-broad grants and checks that pass on nothing.
Only an independent reader who runs things finds those.

## One landing path

brief → work in a worktree → gate stamp → find → verify and rank → fix, capped → integrate and re-gate → verdict on record → merge → owner's brief.

- Every change takes this path; a session with the owner watching takes it too, and an urgent change takes it fast, never around it.
- The [`review` skill](../skills/review/SKILL.md) is the procedure for each step; the [`delegating` skill](../skills/delegating/SKILL.md) writes the brief.
- One item, one PR: long work lands in slices, each its own PR off the default branch; no long-lived collecting branch.

## Tiers

The change sets its tier, never its author or the lead's sense of risk: the highest tier any touched path reaches.

- **routine** (docs, copy, small contained edits): gate stamp only.
- **standard** (ordinary code and tests): one fresh correctness reviewer, then the verify pass.
- **sensitive** (the paths the repo's `REVIEW.md` lists): one reviewer per lens it names, the verify pass, and the landing listed first in the owner's brief.
- With no `REVIEW.md`, sensitive by default: personal data, permissions and access grants, spend and guardrail checks, security controls, an evaluation's scorers and frozen question sets, and the review machinery itself.
- A reviewer may raise a tier; nobody lowers one.

## Reviewers

- A reviewer is a subagent with fresh context and one lens, on Opus at high effort, set in the call: the lead's own model is never assumed.
- It gets the commit range and the issue; never the author's summary of the work.
- It works read-only in its own detached worktree.
- It verifies by running things: the code, a probe, a mutation of a test, real data where the repo allows; a claim it could not check is `unverified`, neither confirmed nor refuted.
- It reviews against the issue's done-when and the repo's guardrails and skips style: a reviewer asked to find problems always finds something, so only a verified `must-fix` is acted on.
- The author of a change never produces its review verdict.

## Evidence

- Evidence is a commit status on the head commit: `loadout/gates` from the gate stamp, `loadout/review` from the verdict.
- A typed test count is not evidence; the stamp is.
- The verdict is the reviewer's raw output, posted on the PR with the head commit it read.

## Fix loop

- Findings go back to the worker that wrote the change; a later pass reads only the new diff.
- Nits are capped at five, listed, and never block.
- After three review-and-fix cycles on one item with a `must-fix` still open: rethink the approach once from a fresh brief, or park the item for the owner and take the next one.
- A cap ends an item's loop, never the session.

## Merge

- An agent may merge its item's PR when `loadout/gates` and `loadout/review` are both `success` on the PR's head commit; a hook refuses the merge otherwise.
- Where the owner keeps the merge (an autopilot profile's merge policy, or the owner's word), the path stops at the verdict and the PR goes in the owner's brief as ready.

## The lead

- The lead is reviewed too: `handoff-auditor` checks the handoff and the decisions in it against the record before it reaches the owner.
- A decision that weakens how a guardrail is enforced is never the lead's: it goes to the owner as a decision packet ([`guardrails.md`](guardrails.md)).
- The handoff states which item got which tier and which reviewers, with each verdict's link.
- Every finding left unfixed is an issue (the `issue` skill) before the handoff names it.

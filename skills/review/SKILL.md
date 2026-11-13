---
name: review
description: "Use before any change lands on a default branch, in any repo, attended or unattended: tier the change, stamp its gates, run fresh reviewers, verify their findings, fix, record the verdict, merge."
---

# Review

The procedure the session landing a change follows, from a pushed head to a merged PR and a line in the owner's brief.
The lead runs it; the author of the change only fixes, and never writes the verdict.
`$R` is this skill's folder; [`templates.md`](templates.md) holds the reviewer brief, the finding shape and a `REVIEW.md` template.

## 1. Tier the change

- Base is the default branch (`git symbolic-ref --short refs/remotes/origin/HEAD`); list the paths with `git diff --name-only <base>...<head>`.
- Read the tiers from `REVIEW.md` at the root of the default branch (`git show <base>:REVIEW.md`), never from the change under review.
- The tier is the highest any path reaches:
  - **routine:** docs, copy, small contained edits, as `REVIEW.md` lists them.
  - **standard:** every other code or test path.
  - **sensitive:** the paths `REVIEW.md` lists as sensitive; with no `REVIEW.md`, any path touching personal data, permissions and access grants, spend and guardrail checks, security controls, an evaluation's scorers and frozen question sets, or the review machinery (this skill, its scripts, the reviewer agents, merge hooks, `REVIEW.md`).
- Done when every path has a tier and the change has one, written down with the lenses step 3 runs.

## 2. Stamp the gates

- The author's tree is clean and its head pushed; run `$R/scripts/gate_stamp.sh` from the repo root.
- It runs the repo's fast gates on that head and records the commit status `loadout/gates`.
- Red: back to the author; no reviewer starts on a red stamp.
- Done when `loadout/gates` is `success` on the head; a `routine` change goes to step 6.

## 3. Find

Start each reviewer as a subagent in the foreground, in parallel, on Opus at high effort set in the call, each with the brief in [`templates.md`](templates.md): the commit range, the issue, its lens, and the path of its own detached worktree (`git worktree add --detach <scratch>/review-<lens> <head>`).
Give no summary of the work, the author's or yours; the PR body goes only to `claims-auditor`, as material under audit.

| Reviewer | Runs on | Looks for |
|---|---|---|
| [`correctness-reviewer`](../../agents/correctness-reviewer.md) | standard, sensitive | the change failing its done-when, on inputs it will meet |
| [`claims-auditor`](../../agents/claims-auditor.md) | sensitive; standard when a doc in the diff or the PR body states a number or an absolute (all, every, never, zero) | each number and absolute claim in docs, comments, test names and the PR body against what the code or a test computes |
| [`guardrail-reviewer`](../../agents/guardrail-reviewer.md) | sensitive: permissions, grants, spend, guardrail checks, security controls, review machinery | a breach of the repo's guardrails; any grant wider than its use |
| [`leak-hunter`](../../agents/leak-hunter.md) | sensitive: personal data, or any output written from real data | personal or secret data in an output, run on real data where the repo allows |
| [`control-prober`](../../agents/control-prober.md) | sensitive: security controls, guardrail checks, scorers, review machinery | a control's test that still passes with the control empty, disarmed or removed |

A `REVIEW.md` that names lenses for a path replaces this table's choice for it; it may add a lens, and `correctness-reviewer` always runs above `routine`.
Done when every reviewer has returned its raw findings; remove the worktrees.

## 4. Verify and rank

- Give [`finding-verifier`](../../agents/finding-verifier.md) every reviewer's raw output, the same range and the issue.
- It reproduces each finding, drops what it cannot confirm, keeps `unverified` claims apart, and ranks the rest `must-fix`, `nit` or `pre-existing` (true before this change).
- It reports at most five nits.
- Done when every finding is reproduced and ranked, dropped, or marked `unverified`.

## 5. Fix, capped

- Send each `must-fix`, with the verifier's reproduction, to the worker that wrote the change (resume that subagent; if you wrote it, you fix it and a fresh reviewer still reviews).
- A nit is applied only when it is cheap; it never blocks.
- After the fix: re-stamp (step 2), then steps 3 and 4 on the new commits only (`<reviewed head>..<new head>`), with the lenses that found a `must-fix` plus `correctness-reviewer`.
- One find, verify and fix round is a cycle; after the third with a `must-fix` still open:
  - **rethink** once per item, when the findings point at the approach: a fresh worker from a fresh brief that carries them, from step 2 with the count at zero;
  - **park** otherwise, or when the rethink hits the cap too: label the issue `needs-owner`, comment the open findings, take the next item.
- Done when no `must-fix` is open, or the item is parked.

## 6. Integrate and re-gate

- Bring the default branch into the PR branch in the repo's style, push, and run `$R/scripts/gate_stamp.sh` on the new head.
- A conflict resolved by hand in a reviewed file is a new diff: steps 3 to 5 on it.
- Done when `loadout/gates` is `success` on the final head.

## 7. Record the verdict

- A session other than the author runs `$R/scripts/verdict.sh` on the final head (its header gives the arguments) with the verifier's output unedited; for `routine`, with the tier line from step 1.
- It posts that output as a PR comment that starts with `🤖` and names the head commit, and records the commit status `loadout/review`: `success` only with no open `must-fix`.
- Done when both statuses are `success` on the PR's head commit.

## 8. Merge

- Merge the item's PR when both statuses are `success` on its head commit; a hook refuses it otherwise.
- Where the owner keeps the merge (the autopilot profile's merge policy, or the owner's word), stop here: the PR goes in the owner's brief as ready.

## 9. File and brief

- Before the handoff, file an issue (the `issue` skill) for each finding left unfixed: each parked `must-fix`, each `pre-existing`, each `unverified` claim, and one per PR for its unapplied nits.
- The owner's brief lists sensitive landings first; per item: its tier, the reviewers that ran, the verdict comment's link, and the issues filed.
- A decision the session took that weakens how a guardrail is enforced is not in the brief as taken: it is a decision packet on its issue (`ways/guardrails.md`), labelled `needs-owner`.
- Give the handoff and the decisions in it to [`handoff-auditor`](../../agents/handoff-auditor.md) with the PR links and issues; fix what it confirms before the owner sees it.
- Done when the auditor has returned and every unfixed finding has an issue the brief links.

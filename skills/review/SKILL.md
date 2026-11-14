---
name: review
description: "Use before any change lands on a default branch, in any repo, attended or unattended: tier the change, stamp its gates, run fresh reviewers, verify their findings, fix, record the verdict, merge."
---

# Review

From a pushed head to a merged PR and a line in the owner's brief.
The author of a change fixes it and never reviews it; with no fresh-context subagent available, stop after step 2: the PR stays unmerged and the owner's brief lists it as unreviewed.
`$R` is this skill's folder; [`templates.md`](templates.md) holds the reviewer brief and a `REVIEW.md` template; the finding shape is each agent's own `## Output`.

## 1. Tier the change

- Run `$R/scripts/tier.sh [--base <ref>]`: it prints `routine`, `standard` or `sensitive` and the paths that decided it.
- The changed paths decide, never the author or the change's size; the highest tier wins:
  - **sensitive:** a built-in floor, always applied: agent instruction and rule files (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, the rule files they import), hook and agent-settings directories (`.claude/**`, `.githooks/**`, `**/hooks/**`), CI workflow files; plus the globs under `REVIEW.md § Sensitive`, which can only add to it.
  - **routine:** the globs under `REVIEW.md § Routine`; with no such list, prose documentation (`**/*.md`, `**/*.txt`, licence files) outside the sensitive set.
  - **standard:** every other path.
- `REVIEW.md` is read from the default branch, never from the change.
- Raise to sensitive when the change touches what paths cannot show: personal data, permissions and access grants, spend, guardrail checks, security controls, an evaluation's scorers and frozen question sets. The lead or a reviewer may raise the tier; nobody lowers it.
- Done when the tier and step 3's lenses are written down.

## 2. Stamp the gates

- With the default branch merged in, a clean tree and the head pushed, run `$R/scripts/gate_stamp.sh [--pr <n>] -- <the repo's fast gates>`: it runs them on that head and posts the `🤖 Gates` record, a comment on the item's PR naming the head (open the draft PR first).
- Red: back to the author, as a cycle (step 5); no reviewer starts on red.
- Done when the gates record is `success` on the head; a `routine` change goes to step 6.

## 3. Find

Start the reviewers as subagents, in parallel and in the foreground, on Opus at high effort set in the call (the collection's default reviewer model, set explicitly because a subagent does not inherit the session's effort; a repo's instructions may name another).
Give each the brief in [`templates.md`](templates.md): the repo, the range `$(git merge-base <default> <head>)..<head>`, the issue body and its done-when quoted; each agent makes and removes its own detached worktree.
Give no summary of the work; the PR body goes only to `claims-auditor`, as material under audit.

| Reviewer | Runs on |
|---|---|
| [`correctness-reviewer`](../../agents/correctness-reviewer.md) | standard, sensitive |
| [`claims-auditor`](../../agents/claims-auditor.md) | sensitive; standard when a doc in the diff or the PR body states a number or an absolute (all, every, never, zero) |
| [`guardrail-reviewer`](../../agents/guardrail-reviewer.md) | sensitive: grants, spend, guardrails, security, review machinery |
| [`leak-hunter`](../../agents/leak-hunter.md) | sensitive: personal data, or output from real data |
| [`control-prober`](../../agents/control-prober.md) | sensitive: security, guardrail checks, scorers, review machinery |

A `REVIEW.md` line's `lenses: a, b` adds those lenses for its paths; `correctness-reviewer` always runs above `routine`.
A change to a line of the repo's guardrails section fails `guardrail-reviewer` unless the PR cites the owner's answer to a conflict packet (`ways/guardrails.md`).
Done when every reviewer has returned its raw findings; remove the worktrees.

## 4. Verify and rank

- Give [`finding-verifier`](../../agents/finding-verifier.md) every reviewer's raw output, the same range and the quoted issue.
- It reproduces each finding, drops the unconfirmed, keeps `unverified` claims apart, and ranks the rest `must-fix`, `nit` (at most five) or `pre-existing` (true before this change).
- Done when every finding is reproduced and ranked, dropped, or marked `unverified`; note the head it read as the reviewed commit.

## 5. Fix, capped

- Send each `must-fix`, with its reproduction, to the worker that wrote the change (if you wrote it, you fix it); a nit is applied only when cheap, and never blocks.
- Then steps 2 to 4 on the new commits only (`<reviewed>..<new head>`), with step 1's lenses for their paths plus the lenses that found a `must-fix`.
- A cycle is a fix round, a red stamp, or an integrate round (step 6); after the third with a `must-fix` or red stamp still open:
  - **rethink** once per item, when the findings point at the approach: a fresh worker, a fresh brief carrying them, the count at zero;
  - **park** otherwise: label the issue `needs-owner`, comment the open findings, take the next item.
- Done when no `must-fix` is open, or the item is parked.

## 6. Integrate and re-gate

- If the default branch moved, merge it into the PR branch, push, and re-stamp (step 2); this counts as a cycle.
- A clean merge needs no new review; any other new commit goes through steps 3 to 5 on the new diff.
- Done when the gates record is `success` on the PR's head.

## 7. Record the verdict

- Run `$R/scripts/verdict.sh --reviewed <sha>` (its header gives the other arguments) with the verifier's output unedited; for `routine`, `verdict.sh --tier routine`, which the change's own author may run.
- It recomputes the tier and refuses a lower one than the paths give, and refuses unless the PR head equals the reviewed commit or differs from it only by a clean merge of the default branch.
- It posts the output as a PR comment that starts with `🤖` and names the reviewed commit and the head, as the `🤖 Review` record: `success` only with no open `must-fix`.
- Done when both records are `success` on the PR's head commit.

## 8. Merge

- Merge when both records are `success` on the PR's head commit, naming that head in the merge; on cloud a hook refuses it otherwise, and refuses any Bash command that mentions a PR merge, so merge there with the MCP merge tool (`expectedHeadSha`) or a script that calls the hook's `--check <owner>/<repo>#<n>` (`cloud/hooks/merge-guard.py`), as the autopilot's `merge.sh` does.
- Where the owner keeps the merge (a repo's own rule, an autopilot profile's merge policy, or the owner's word), skip the merge and list the PR as ready; step 9 still runs.

## 9. File and brief

- File an issue (the `issue` skill) per unfixed finding: `pre-existing`, `unverified`; one per PR for its unapplied nits; a parked item's `must-fix` findings stay in its `needs-owner` packet, not also in issues.
- The owner's brief lists sensitive landings first, then unreviewed ones; per item: tier, reviewers run, verdict link, issues filed.
- A decision that weakens how a guardrail is enforced is never the session's: it is a conflict packet on its issue (`ways/guardrails.md`), labelled `needs-owner`.
- Before the owner sees it, [`handoff-auditor`](../../agents/handoff-auditor.md) checks the handoff and its decisions against the PRs and issues; fix what it confirms.
- Done when the auditor has returned and every unfixed finding has an issue the brief links.

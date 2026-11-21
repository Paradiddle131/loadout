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
  - **sensitive:** a built-in floor, always applied: agent instruction and rule files (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, the rule files they import), hook and agent-settings directories (`.claude/**`, `.githooks/**`, `**/hooks/**`), CI workflow files, an unattended run's profile and markers (`docs/agents/**`); plus the globs under `REVIEW.md § Sensitive`, which can only add to it.
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

- Run `$R/scripts/plan.py [--mode light|focused|full] [--add <lens>,...]` (a fix round adds `--since <reviewed> --prior <that round's verifier output>`): it prints the round's lenses, `first` and `then`, from the paths, never the author.
  `--add` takes a lens for what paths cannot show (`leak-hunter` for personal data or output from real data, `control-prober` for a check, guard, scorer or the review machinery, `claims-auditor` on a standard change whose docs or PR body state a number or an absolute); nobody drops a lens it prints.
- The mode is `focused` unless the owner, the repo's instructions or an autopilot profile names another; a lead may raise it to `full`, never lower it:
  - **focused:** the `first` lens alone, then the `then` lenses in parallel, each brief carrying the first lens's findings as raised this round (templates.md), so a lens reports only what they miss;
  - **full:** every lens at once, and a fix round reruns the whole set;
  - **light:** the lenses at once with no first phase; `plan.py` refuses it on a sensitive change's first review.
- Start each lens as a subagent in the foreground, on Opus at high effort set in the call (the collection's default; set it explicitly, because a subagent does not inherit the session's effort; a repo's instructions may name another), and the same model and effort for every lens of a round, which step 7 records.
- Give each the brief in [`templates.md`](templates.md): the repo, the range `$(git merge-base <default> <head>)..<head>`, the issue body and its done-when quoted; each agent makes and removes its own detached worktree.
  Give no summary of the work; the PR body goes only to `claims-auditor`, or to a repo's own lens its `REVIEW.md` names that asks for it, as material under audit.

| Reviewer | First review |
|---|---|
| [`correctness-reviewer`](../../agents/correctness-reviewer.md) | standard, sensitive |
| [`claims-auditor`](../../agents/claims-auditor.md) | sensitive; `--add` on standard when a doc in the diff or the PR body states a number or an absolute (all, every, never, zero) |
| [`guardrail-reviewer`](../../agents/guardrail-reviewer.md) | sensitive |
| [`leak-hunter`](../../agents/leak-hunter.md) | by `REVIEW.md` or `--add`: personal data, or output from real data |
| [`control-prober`](../../agents/control-prober.md) | by `REVIEW.md` or `--add`: security, guardrail checks, scorers, review machinery |

A `REVIEW.md` line's `lenses: a, b` adds those lenses for its paths.
A change to a line of the repo's guardrails section fails `guardrail-reviewer` unless the PR cites the owner's answer to a conflict packet (`ways/guardrails.md`).
Done when every lens has returned its raw findings; remove the worktrees.

## 4. Verify and rank

- Every lens report names the head the verifier will read; a lens behind it reruns first, so no commit goes to the verifier unread.
- Give [`finding-verifier`](../../agents/finding-verifier.md), a fresh subagent that served as no lens in the round, every reviewer's raw output, the same range, the change base, the settled findings and the quoted issue.
- It reproduces each finding, drops the unconfirmed, keeps `unverified` claims apart, and ranks the rest `must-fix`, `nit` (at most five) or `pre-existing` (true at the change's merge-base with the default branch, not at the round's base).
- A finding blocks by the harm it names: a `must-fix` carries a `harm:` line saying who acts wrongly or what breaks once the change lands, and the verifier's one-line `Blocking:` list repeats each with its harm; a real defect this change adds with no such harm is a `nit`.
- **Steering:** any line the lead adds to a lens or verifier brief beyond the template goes in the verifier's brief as a `Steering:` line (templates.md), and the handoff says the round was steered.
  The verifier ranks every finding by its own list whatever a steering line says; its output quotes each steering line, redacted as its Check list says, and the settled lines, and `verdict.sh` posts that output (clipped to fit GitHub's comment limit).
  A lead that wants a `must-fix` lowered posts a conflict packet (step 9).
- Record the round's verdict now by step 7, a `FAIL` included, before any fix is pushed: no round runs without its record on the PR.
- Done when every finding is reproduced and ranked, dropped, or marked `unverified`, and the round's `🤖 Review` record is posted; note the head it read as the reviewed commit.

## 5. Fix, capped

- Send each `must-fix` the verifier's `Blocking:` line lists, with its reproduction, to the worker that wrote the change (if you wrote it, you fix it); a nit is applied only when cheap, and never blocks.
- A fix to code covers the finding's class (every place the same defect occurs) with a test that goes red without it; a fix to a claim says less (narrow or delete the sentence) and adds no new completeness claim.
- Then steps 2 to 4 on the new commits only (`<reviewed>..<new head>`), each brief carrying the settled list, built from the earlier `🤖 Review` records: each finding's ids, its rank as that record posted it (on a record with a `Blocking:` line, a must-fix is one that line lists; on an older one, one its `## Must-fix` section holds), and the record's link (templates.md).
  The lenses are what `plan.py --since <reviewed> --prior <its verifier output>` prints:
  - each lens a must-fix on the round's `Blocking:` line came from, and the lenses `REVIEW.md` names for the paths the fix changed;
  - `correctness-reviewer` when the fix changes a path `tier.sh` does not rank routine; `claims-auditor` when every path it changes is routine; the sensitive set when it changes a sensitive path;
  - every lens the first review took by `--add`: pass the same `--add` on every round of the change;
  - the whole first-review set in `full` mode, or when a blocking id's prefix names no lens;
  - the verifier on every round.
- A cycle is a fix round, a red stamp, or an integrate round (step 6); after the third with a `must-fix` or red stamp still open:
  - **rethink** once per item, when the findings point at the approach: a fresh worker, a fresh brief carrying them, the count at zero;
  - **park** otherwise: label the issue `needs-owner`, comment the open findings, take the next item.
- Done when no `must-fix` is open, or the item is parked.

## 6. Integrate and re-gate

- If the default branch moved, merge it into the PR branch, push, and re-stamp (step 2); this counts as a cycle.
- A clean merge needs no new review; any other new commit goes through steps 3 to 5 on the new diff.
- A recorded verifier output with no `Blocking:` line, from before that line existed, cannot be posted again: run the verifier once more on the reviewed commit.
- Done when the gates record is `success` on the PR's head.

## 7. Record the verdict

- Run `$R/scripts/verdict.sh --reviewed <sha> --mode <mode> --model <model> --effort <effort>` (its header gives the other arguments; `--reviewers` names every lens that ran and the verifier) with the verifier's output unedited (the author may run it; the script cannot tell the verifier's output from a typed one, so the rule is to post it unedited); for `routine`, `verdict.sh --tier routine`, which the change's own author may run.
- It recomputes the tier and refuses a lower one than the paths give, and refuses unless the PR head equals the reviewed commit or differs from it only by a clean merge of the default branch.
- Above `routine` it takes the result from the output's first `VERDICT` line, and refuses an output without the verifier's `VERDICT` and `Reviewed` lines, one whose lines name a commit other than `--reviewed`, one whose `Blocking:` line (right after `Reviewed:`) is missing, lists a must-fix whose harm is missing, under two words or made only of `blocking.py`'s filler words, or whose id opens no `###` heading below it outside a code fence, lists none on a `FAIL` or any on a `PASS`, and a `--result` that contradicts its verdict.
- It posts the output as a PR comment that starts with `🤖` and names the reviewed commit and the head, with a round line under the marker (`mode`, `model`, `effort`, `lenses`) for people and audits, as the `🤖 Review` record: `success` when the verifier's `VERDICT` line says `PASS` (for `routine`, when `--result` is `pass`, its default).
- Done when both records are `success` on the PR's head commit.

## 8. Merge

- Merge when both records are `success` on the PR's head commit, naming that head in the merge; on cloud a hook refuses it otherwise, and refuses any Bash command whose text holds `pr merge` or a `pulls/<n>/merge` endpoint, so merge there with the MCP merge tool (`expectedHeadSha`) or a script that calls the hook's `--check <owner>/<repo>#<n>` (`cloud/hooks/merge-guard.py`), as the autopilot's `merge.sh` does.
- Where the owner keeps the merge (a repo's own rule, an autopilot profile's merge policy, or the owner's word), skip the merge and list the PR as ready; step 9 still runs.

## 9. File and brief

- File an issue (the `issue` skill) per unfixed finding: `pre-existing`, `unverified`; one per PR for its unapplied nits; a parked item's `must-fix` findings stay in its `needs-owner` packet, not also in issues.
- The owner's brief lists sensitive landings first, then unreviewed ones (a `debrief` over several runs follows its own `landings.md`); per item: tier, reviewers run, verdict link, issues filed, and each steering line, quoted with personal or secret values redacted.
- A decision that weakens how a guardrail is enforced is never the session's: it is a conflict packet on its issue (`ways/guardrails.md`), labelled `needs-owner`.
- Before the owner sees it, [`handoff-auditor`](../../agents/handoff-auditor.md) checks the handoff and its decisions against the PRs and issues; fix what it confirms.
- Done when the auditor has returned and every unfixed finding has an issue the brief links.

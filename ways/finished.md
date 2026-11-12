# Finished code base

How a repo reads as finished at every commit, with its roadmap, progress and decisions on the tracker.

## The tree

- Every commit reads as finished: each document describes the system as it is now.
- Standing documents: a README (what it is, how to run it), one architecture document, the agent instruction file, and the operator documents the product itself needs.
- The architecture document holds the current design and each major choice with its reason and the rejected alternative, in words, in a sentence or two: a clone without the tracker still explains itself; the issue holds only the weighing.
- Each standing document is rewritten in place, never appended to, and fits about two screens; a change that pushes one past that merges or deletes in the same diff.
- A plan, roadmap, ledger, changelog of work, lessons file, research note or per-decision record is a tracker item, never a file.
- A lesson that changes behaviour lands as a reason in the architecture document or a rule in the agent instruction file.

A choice in the architecture document:

```markdown
- **<the choice, one sentence; pins and names exact>**: <why, with the evidence in words>; rejected: <option> (<one clause>), <option> (<one clause>).
```

## The tracker

- The roadmap is epics as issues, each with sub-issues for its steps; each issue's `Blocked by` names what must land first.
- Labels name area and kind; one small vocabulary per repo.
- Progress is the issues' state and the PRs that close them.
- A visual, a long analysis or a research finding is an artifact on its issue (the `issue` skill).
- A sub-issue is attached by its `id`, not its number: `gh api -X POST repos/<owner>/<repo>/issues/<epic>/sub_issues -F sub_issue_id=<id>`, the `id` from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`.

## Decisions

- A decision is a fork with real alternatives; a step with none is just an issue and its PR.
- It is weighed on its issue: the options with their cost, a recommendation, the owner's call (the choice under the `issue` skill's `Needs you`).
- One costly to undo (a data model, a vendor, a security boundary) gets a write-up as an artifact on its issue: Context, Options with their cost, Choice and why, Undo cost, Revisit when.
- The agent writes the architecture document's line in final form in the PR that needs it; the PR body lists each new or changed choice under its decisions, and the merge accepts them.
- A choice only the owner can make before the work starts goes as a decision packet on the issue first ([`guardrails.md`](guardrails.md)); the line follows the answer.
- A superseded decision is a new issue linking the old one; the PR that acts on it rewrites the line, and the architecture document states only the outcome.
- A PR that changes behaviour a line describes amends or deletes that line in the same diff; a line nothing depends on any more is deleted.

## References

- Checked-in files cite no process id (`RULES.md`): code, comments and docs say the behaviour and its reason in words.
- Issues and PRs cite code (`path:line`, a commit sha) and each other; commit messages and PR bodies cite anything.
- [`../cloud/githooks/check-process-ids.py`](../cloud/githooks/check-process-ids.py) guards it as a pre-commit hook ([`../cloud/githooks/`](../cloud/githooks/pre-commit)): it refuses an issue, PR, work-label or decision id on a line the commit adds, and in a repo on these ways a new plan, roadmap, ledger, lessons or decision-record file.
- A token the repo defines (a product code, a fixture key) goes in its `.process-ids`, a path to skip as `path: <glob>`; a test fixture's line takes `ref-ok`.

## Finding why

1. The architecture document, for the current reason.
2. `git log -S '<phrase>'` or `git blame`, to the commit, its PR and the issue the PR closes.

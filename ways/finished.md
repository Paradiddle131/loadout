# Finished code base

How a repo reads as finished at every commit, with its roadmap, progress and decisions on the tracker.
An opt-in alternative to the plan and its decision register ([`decisions.md`](decisions.md)); a repo adopts it with one more line in its `CLAUDE.md`:

```markdown
Finished code base: [ways/finished.md](https://github.com/<owner>/<collection>/blob/main/ways/finished.md); it replaces the plan and the decision register.
```

## The tree

- Every commit reads as finished: each document describes the system as it is now.
- Standing documents: a README (what it is, how to run it), one architecture document, the agent instruction file, and the operator documents the product itself needs.
- The architecture document holds the current design and each major choice with its reason and the rejected alternative, in words, in a sentence or two: a clone without the tracker still explains itself; the issue holds only the weighing.
- Each standing document is rewritten in place, never appended to, and fits about two screens; a change that pushes one past that merges or deletes in the same diff.
- A plan, roadmap, ledger, changelog of work, lessons file or per-decision record is a tracker item, never a file.
- A lesson that changes behaviour lands as a reason in the architecture document or a rule in the agent instruction file.
- A default ([`guardrails.md`](guardrails.md)) changes in the PR that needs it; the architecture document carries its new reason.

## The tracker

- The roadmap is epics as issues, each with sub-issues for its steps; each issue's `Blocked by` names what must land first.
- Labels name area and kind; one small vocabulary per repo.
- A decision is weighed on an issue: the options with their cost, a recommendation, the owner's call (the `issue` skill, the choice under `Needs you`).
- A visual or long analysis is an artifact on its issue (the `issue` skill).
- A superseded decision is a new issue linking the old one; the architecture document states only the outcome.
- Progress is the issues' state and the PRs that close them.
- A sub-issue is attached by its `id`, not its number: `gh api -X POST repos/<owner>/<repo>/issues/<epic>/sub_issues -F sub_issue_id=<id>`, the `id` from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`.

## Finding why

1. The architecture document, for the current reason.
2. `git log -S '<phrase>'` or `git blame`, to the commit, its PR and the issue the PR closes.

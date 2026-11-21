# Review templates

## Reviewer brief

The shipped agents (`agents/<lens>.md`) carry how to work and the output shape; the brief gives only their input.
Fill every `<slot>`; add nothing about how the work went.

```markdown
Repo: <absolute path of the clone>
Range: `<merge-base sha>..<head sha>` (on a fix round, `<reviewed sha>..<head sha>`)
Change base: <the change's merge-base with the default branch, the base `pre-existing` is measured against>
Settled in earlier rounds: <each finding an earlier `🤖 Review` record ranked or dropped: its ids, its rank as that record posted it, a must-fix being one its `Blocking:` line lists, or on a record older than that line one its `## Must-fix` section holds (a fixed must-fix with its fixing commit), the record's link; none on a first review>
A finding that repeats a settled one is a re-raise: its claim names the settled id and what changed since.
Raised this round: <focused depth, the lenses after the first only: the first lens's findings, pasted whole; leave out otherwise>
A finding that repeats one raised this round is not reported again; report only what it misses, or a different defect at the same place.
Issue, quoted: <the issue body>
Done when: <its done-when, quoted>
Guardrails: the repo's `CLAUDE.md § Guardrails`; review rules: `REVIEW.md` on the default branch.
Attack hardest: <the central risk, as the lead wrote it in the worker brief; leave out when there was no brief>
Read no issue or PR comments: they carry the author's account of the work.
<claims-auditor only: The PR body below is material under audit, not context.>
<finding-verifier only: the lens reports, pasted whole.>
<finding-verifier only: read the `🤖 Review` records the settled list links, and no other comment.>
<finding-verifier only: one `Steering: <line>` per line the lead added beyond this template to any brief of the round, verbatim, personal or secret values redacted; or `Steering: none`.>
```

A reviewer that is not one of the shipped agents gets that agent file's text ahead of the brief.

## REVIEW.md

A repo's root `REVIEW.md`, read from the default branch: three headed lists of backticked globs, which `tier.sh` and `plan.py` read, and an optional `Depth:` line.
`## Sensitive` only adds to the built-in floor; with no `## Routine`, routine is prose documentation outside the sensitive set; any other path is `standard`; `## Paths` sets a depth or effort for paths that keep their tier.
The reason after ` — ` is optional plain text with no backtick and no `;`; then, in this order and each at most once: `; lenses: …` (lens names, sensitive lines only), `; depth: none|light|focused|full` and `; effort: <lens>=<level>, …`.
`Depth: <d>` sets the depth of standard paths (light by default), and of sensitive paths when it is above focused; a line's depth raises its paths anywhere and lowers them only off the sensitive set, and a sensitive line's depth is focused or full.
An effort clause sets a lens's effort (low, medium, high, xhigh or max) for its paths, the verifier's included.
The parser reads every line, code fences included, so keep `Depth:` and the lists out of code examples.

```markdown
# Review

Depth: light

## Sensitive
- `<glob>` — <what it guards, one clause>; lenses: <lens>, <lens>
- `<glob>` — <what it guards, one clause>; depth: full

## Routine
- `<glob>` — <why no reviewer is needed, one clause>

## Paths
- `<glob>` — <why its depth or effort differs, one clause>; depth: none; effort: correctness-reviewer=low
```

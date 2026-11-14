# Review templates

## Reviewer brief

The shipped agents (`agents/<lens>.md`) carry how to work and the output shape; the brief gives only their input.
Fill every `<slot>`; add nothing about how the work went.

```markdown
Repo: <absolute path of the clone>
Range: `<merge-base sha>..<head sha>`
Issue, quoted: <the issue body>
Done when: <its done-when, quoted>
Guardrails: the repo's `CLAUDE.md § Guardrails`; review rules: `REVIEW.md` on the default branch.
Attack hardest: <the central risk, as the lead wrote it in the worker brief; leave out when there was no brief>
Read no issue or PR comments: they carry the author's account of the work.
<claims-auditor only: The PR body below is material under audit, not context.>
<finding-verifier only: the lens reports, pasted whole.>
```

A reviewer that is not one of the shipped agents gets that agent file's text ahead of the brief.

## REVIEW.md

A repo's root `REVIEW.md`, read from the default branch: two headed lists of backticked globs, which `tier.sh` reads.
`## Sensitive` only adds to the built-in floor; with no `## Routine`, routine is prose documentation outside the sensitive set; any other path is `standard`.
The reason after ` — ` is optional plain text with no backtick and no `;`; `; lenses: …` comes last, lens names only.

```markdown
# Review

## Sensitive
- `<glob>` — <what it guards, one clause>; lenses: <lens>, <lens>
- `<glob>` — <what it guards, one clause>

## Routine
- `<glob>` — <why no reviewer is needed, one clause>
```

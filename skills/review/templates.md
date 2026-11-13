# Review templates

## Reviewer brief

Fill every `<slot>`; add nothing about how the work went.

```markdown
You review one change through one lens: <lens>.
Change: `<merge-base sha>..<head sha>` in <repo>; your worktree, detached at the head: `<path>`. Work read-only: edit, commit and push nothing.
Issue, quoted: <the issue body>
Done when: <its done-when, quoted>
Read no issue or PR comments: they carry the author's account of the work.
Guardrails: the repo's `CLAUDE.md § Guardrails`; review rules: `REVIEW.md` on the default branch.
<claims-auditor only: The PR body below is material under audit, not context.>

- Review against the done-when and the guardrails; skip style and naming.
- Verify each finding by running something: the code, a probe, a mutated test, real data where the repo allows. Reading alone gives `unverified`.
- A claim you could not check is `unverified`, with why; never count it as confirmed or refuted.
- Report every finding in the shape below, and nothing else.
```

## Finding

```markdown
- **<what is wrong, one line>** — `path:line`
  Verified: `<command>` → <the output that shows it> | Unverified: <what stopped the check>
  Rank: must-fix | nit | pre-existing — <one clause: the done-when or guardrail it breaks>
```

The finder proposes the rank; `finding-verifier` sets it.

## REVIEW.md

A repo's root `REVIEW.md`, read from the default branch: two headed lists of backticked globs, which `tier.sh` reads.
`## Sensitive` only adds to the built-in floor; with no `## Routine`, routine is prose documentation outside the sensitive set; any other path is `standard`.

```markdown
# Review

## Sensitive
- `<glob>` — <what it guards, one clause>; lenses: <lens>, <lens>
- `<glob>` — <what it guards, one clause>

## Routine
- `<glob>` — <why no reviewer is needed, one clause>
```

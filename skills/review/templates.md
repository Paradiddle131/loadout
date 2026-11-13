# Review templates

## Reviewer brief

Fill every `<slot>`; add nothing about how the work went.

```markdown
You review one change through one lens: <lens>.
Change: `<base sha>..<head sha>` in <repo>; your worktree, detached at the head: `<path>`. Work read-only: edit, commit and push nothing.
Issue: <link>; its done-when: <quoted>.
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

A repo's root `REVIEW.md`, read from the default branch; it is itself a sensitive path.

```markdown
# Review

Tiers and lenses for the `review` skill. Any path not listed is `standard`.

## Sensitive
- `<glob>`: <lenses> — <what it guards, one clause>
- `REVIEW.md`, `<hook and script globs>`: control-prober, guardrail-reviewer — the review machinery

## Routine
- `<glob>`: <why no reviewer is needed, one clause>

## Never flag
- <a pattern reviewers keep raising that the repo accepts, with its reason>
```

# The two briefs

Fill the angle-bracketed slots; keep the rest of each brief as it stands.
Each brief is all its agent knows: write it for a peer who never saw this conversation.

## Research brief

```text
You are researching and then writing generic rules for <the collection's skill, e.g. a house report kit>. Take your time; quality over speed.

The reviewer's concern, in their words:
<verbatim>

What it points at: <your diagnosis, one line per part of the work>.
The work as it is now: <before screenshots, paths>; the live work: <path or URL, how to open it, how to switch theme>. Read only; edit nothing there.

The collection you are extending: <worktree path>, branch <branch>. Read <the skill's files> first; your additions must fit its existing rules, not fight them. Its writing rules: <AGENTS.md, the writing-for-agents skill>. Everything you add stays generic: no project names, owners, dates or issue numbers; examples invented.

Research primary sources (design systems, standards bodies, editorial guides, the skill's own references) and cite what you use.

Deliver:
1. A research note at <path>: the diagnosis part by part, the principles with sources, the options you weighed, and your recommendation.
2. The rules as uncommitted edits in the worktree, in the collection's voice: each a one-line rule, its reason, its grounds where not obvious, and when not; plus the smallest support they need (tokens, a component, a check), with its contract documented.
3. The collection's checks run, with their results.

Reply with: the diagnosis in a few bullets, each rule in one line, the support you added, the check results, and what you were unsure of.
```

## Trial brief

```text
You are working on <the work>. Its owner has a concern about it; fix it, following the owner's shared collection of rules.

Your workspace: <worktree path>, branch <branch>. Work only there; commit locally as you go; do not push or open PRs.
Read the work's own rules first: <its AGENTS.md / CLAUDE.md, its notes>.
The collection: <path at the teach branch> (read only). Its rules for this kind of work: <the skill>; follow its steps where they apply.

The owner's concern, in their words:
<verbatim>

Keep what the owner already settled: <decisions on record, one line each>.

Checks before you finish: <the work's checks, how to run each, how long the slow ones take>. Screenshots of <the parts> at <widths> in <themes>, saved to <path>.

Reply with: what you changed and why, the collection's rules and parts you used by name, the check results with numbers, anything in the collection that was missing, unclear or that you worked around, and anything you could not verify.
```

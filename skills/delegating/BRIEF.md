# The briefs

Fill the angle-bracketed slots; keep the rest of each brief as it stands.
Each brief is all its agent knows: write it for a peer who never saw this conversation, and cut a slot's line only when it truly has nothing to say.

## Worker brief

```text
You are implementing one item in <repo>: <the goal, one line>.
Why it matters: <the reason, one or two lines>.

The item: <issue link or text>. It is done when: <the issue's done-when, verbatim>.

Your workspace: <worktree path>, branch <branch>. Work only there and commit as you go (<the repo's commit style>).
No push, PR or GitHub write, unless this line allows one: <none, or what>.

Read first: <the repo's AGENTS.md / CLAUDE.md, its architecture document, the files the item touches, the skills that apply>.

Rules that bind this item (restated: you see none of the lead's instructions):
- <each guardrail that applies, one line each>

Already established, do not redo: <facts the lead checked, with how>.
Already ruled out, do not retry: <approaches and why each failed>.

Out of scope: <what this item does not change>.
A parallel worker owns <its item> on <its files>: do not edit those.
Do not edit the shared files (<README, architecture document, manifests, registries>): put the lines they need in your report.

Checks to run before you finish: <each command>. Quote each command and its output; "tests pass" is not a result.
A reviewer will attack this hardest on: <the central risk>.

Reply with:
1. What you did, file by file.
2. Each check's command and output.
3. Every deviation from this brief, stated as a decision with its reason.
4. The lines the shared files need, verbatim.
5. Problems you met and did not fix (out of scope, or in another worker's files), each with where and how to reproduce it.
6. What you could not verify, and why.
7. Your head commit.
```

## Reviewer brief

The `review` skill holds it ([`../review/templates.md`](../review/templates.md)): the repo, the commit range, the issue and its done-when quoted, the central risk as the lead wrote it, and never the worker's summary.

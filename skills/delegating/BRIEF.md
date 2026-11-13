# The two briefs

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

```text
You are reviewing one change in <repo>, by the review skill, as <the reviewer agent>.

The change: commits <base>..<head> on <branch>. The item it claims to do: <issue link or text>, done when: <done-when, verbatim>.
Your workspace: a detached worktree at <head>, <path>. Read only: edit nothing, commit nothing, write nothing to GitHub.
Its tier: <the tier the review skill's rule gives it>.
Attack hardest: <the central risk, as the lead wrote it in the worker brief>.

Rules the change must keep (restated: you see none of the lead's instructions):
- <each guardrail that applies, one line each>

Reply in the review skill's report shape.
```

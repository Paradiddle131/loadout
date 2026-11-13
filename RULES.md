# Standing rules

Rules for an agent working in any repo, on any machine.
Import them from your user-level instructions (`@<clone>/RULES.md` in `~/.claude/CLAUDE.md`, or paste them into `AGENTS.md`); `cloud/setup.sh` does it on Claude Code on the web.
A repo's own `CLAUDE.md` or `AGENTS.md` wins where it is more specific.
A rule that names a skill applies where that skill is installed.
Every rule here acts inside the repo being worked on; the one rule that writes to this collection's own repo is in [`FEEDBACK.md`](FEEDBACK.md), imported beside this file only where it is wanted.

- Make small, typed, testable changes, and validate them before calling the work done; report outcomes faithfully, including what you could not verify.
- Prefer a mature, framework-native solution to a bespoke workaround; when the better path is a larger refactor, lay out the options with a recommendation instead of choosing the workaround silently.
- When a tool is missing, install it in an isolated way (`uv tool`, `uvx`, `npx`) or state the gap; never pass off a weaker check as the real one.
- Land every change by [`ways/review.md`](ways/review.md) (the `review` skill): a tier its changed paths set, fresh reviewers who verify by running things, and a gates record and a review verdict on its head commit before it merges; the author never reviews its own change.
- Hand work to a subagent by the `delegating` skill: a full brief, its own worktree, model and effort set explicitly, and its report checked, never trusted.
- Start or resume a paid, quota-bound or long measured pass by the `experiment-preflight` skill.
- Write down every problem you find but do not fix: a GitHub issue in the `issue` skill's shape, with the session's durable plan, analysis or visual as an artifact on it.
- Name work for what it does, never by a process id: no phase or milestone numbers, issue or PR numbers, or decision ids in anything checked in (code, comments, test names, documentation, file names); commit messages, PR titles and PR bodies cite issues and PRs freely ([`ways/finished.md § References`](ways/finished.md#references)).
- Order work by dependency and value; never estimate its time or effort.
- A repo says what it does and how to run it; the owner's purpose for it, their employer and what prompted it stay out of it.
- Fix the lint errors, test failures and flaky tests you meet, even when they are unrelated.
- Start a bug fix by reproducing the bug as close to how its user would hit it as the environment allows.
- A report, page or deck for a reader outside the work shows only what that reader understands at a glance: process metadata (hashes, version lineage, issue and PR numbers, file names, run bookkeeping) stays in the commits, PRs and issues, and every term the page shows gets a tooltip or a glossary line.
- In a repo with a UI, follow its `DESIGN.md` (repo root, then `docs/design/`) before any UI change.
- Draw an architecture or system diagram with the `draw-architecture` skill, unless the repo's `DESIGN.md` asks for another style.
- Write PR bodies with the `pr` skill; a repo's own template only renames its sections.
- Commit in the repo's message style (conventional commits by default), with no agent co-author and no session trailer.
- Put each sentence of long Markdown on its own line.
- Follow the [ways of working](ways/README.md) in a repo whose `CLAUDE.md` opts in.

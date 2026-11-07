# Standing rules

Rules for an agent working in any repo, on any machine.
Import them from your user-level instructions (`@<clone>/RULES.md` in `~/.claude/CLAUDE.md`, or paste them into `AGENTS.md`); `cloud/setup.sh` does it on Claude Code on the web.
A repo's own `CLAUDE.md` or `AGENTS.md` wins where it is more specific.

- Make small, typed, testable changes, and validate them before calling the work done; report outcomes faithfully, including what you could not verify.
- Prefer a mature, framework-native solution to a bespoke workaround; when the better path is a larger refactor, lay out the options with a recommendation instead of choosing the workaround silently.
- When a tool is missing, install it in an isolated way (`uv tool`, `uvx`, `npx`) or state the gap; never pass off a weaker check as the real one.
- Write down every problem you find but do not fix: a GitHub issue in the `issue` skill's shape, with the session's durable plan, analysis or visual as an artifact on it.
- Fix the lint errors, test failures and flaky tests you meet, even when they are unrelated.
- Start a bug fix by reproducing the bug as close to how its user would hit it as the environment allows.
- A report, page or deck for a reader outside the work shows only what that reader understands at a glance: process metadata (hashes, version lineage, issue and PR numbers, file names, run bookkeeping) stays in the repo, and every term the page shows gets a tooltip or a glossary line.
- In a repo with a UI, follow its `DESIGN.md` (repo root, then `docs/design/`) before any UI change.
- Draw an architecture or system diagram with the `draw-architecture` skill, unless the repo's `DESIGN.md` asks for another style.
- Write PR bodies with the `pr` skill; a repo's own template only renames its sections.
- Commit in the repo's message style (conventional commits by default), with no agent co-author and no session trailer.
- Put each sentence of long Markdown on its own line.
- Follow the [ways of working](ways/README.md) in a repo whose `CLAUDE.md` opts in.
- Improve this collection as you use it: when one of its skills, ways or rules gets something wrong or lacks what the work needed, or the owner corrects how you worked in a way likely to recur in other repos, open a PR on the repo that holds this file (branch `claude/<slug>`), written generic, saying what you hit, the evidence and the smallest change.
  It waits for the owner's review and is never merged by an agent; the current work carries on with a local workaround meanwhile.

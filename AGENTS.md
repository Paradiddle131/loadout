# Working in this repo

This repo is read by people and agents who never saw where it came from: everything in it stays generic.

- Name roles, not instances: `<owner>` and `<repo>` for an account and a repository, derived at run time (`git remote get-url origin`) where a command needs the value; examples are invented (`example-owner/example-repo`).
- A line's history is git's: dates, issue and PR numbers, and what one project measured go in the PR body, where `git log -S` finds them.
- [`ways/portable.md`](ways/portable.md) is the long form of both rules.
- A skill adapted from another repo keeps `metadata.upstream*` in its frontmatter and that repo's licence beside it; take upstream changes by hand after `bin/check-upstream --diff <skill>`, then move `upstream-commit`.
- A review agent goes in `agents/` (one lens each, read-only, model and effort explicit) and is added to nothing else.
- A new skill goes in `skills/` (any machine) or `cloud/skills/` (Claude Code on the web only), and is added to nothing else: the plugins pick up every folder there.
- One skill names another by its bare name (the `issue` skill), which holds whether it came in a plugin or alone (`npx skills`, `gh skill`).
- Writing a skill or an instruction file: the `writing-for-agents` skill.

## Checks

The pre-commit hook runs them (`git config core.hooksPath .githooks`; the cloud session-start hook sets it):

- `bin/check-plugins.sh`: every plugin skill path holds a skill, and every agent under `agents/` has full frontmatter (a documented model and effort, read-only tools, no `:` in its name) and the same `## How you work` block;
- `bin/check-refs`: every link, backticked repo path and `<plugin>:<skill>` name resolves;
- `gitleaks protect --staged`: no secrets;
- `bin/check-generic.sh`: no owner login, sibling repo name, date or issue number in shared content (extra words from `$GENERIC_DENY_FILE`);
- `cloud/githooks/check-process-ids.py`: no issue, PR, phase or decision id on an added line (the other clones run it too; exemptions in `.process-ids`).

Tests:

```bash
uvx --from pytest==8.4.2 pytest -q bin/tests cloud/skills/autopilot/scripts/tests cloud/gcp/tests cloud/githooks/tests cloud/hooks/tests skills/review/scripts/tests skills/experiment-preflight/scripts/tests
node skills/report-kit/tests/scope.test.cjs
node skills/report-kit/tests/dialog.test.cjs
claude plugin validate --strict .
```

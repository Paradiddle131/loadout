# loadout

Agent skills, ways of working and standing rules, packaged as a [Claude Code](https://code.claude.com) plugin marketplace, plus a setup for Claude Code on the web.

## What's inside

| Plugin | Holds | For |
|---|---|---|
| `loadout` | `pr`, `issue`, `review`, `delegating`, `experiment-preflight`, `draw-architecture`, `report-kit`, `grilling`, `writing-for-agents`, `concern-to-rule`; review agents `correctness-reviewer`, `claims-auditor`, `guardrail-reviewer`, `leak-hunter`, `control-prober`, `finding-verifier`, `handoff-auditor` | any machine |
| `cloud` | `autopilot`, `autopilot-brief`, `image-cache`, and session hooks | [Claude Code on the web](cloud/README.md) |

- [`RULES.md`](RULES.md): standing rules for an agent in any repo.
- [`FEEDBACK.md`](FEEDBACK.md): the one rule that writes back to this collection's own repo, kept apart so a machine can leave it out.
- [`ways/`](ways/README.md): ways of working a repo can adopt with one line in its `CLAUDE.md`.

The skills follow the [Agent Skills](https://agentskills.io) format, so agents other than Claude Code can read them from `skills/` as they are.

## Install

**Claude Code**, every skill (`/loadout:` lists them):

```bash
claude plugin marketplace add <owner>/loadout
claude plugin install loadout@loadout
```

`claude plugin marketplace update loadout` takes the latest.

**Any agent, picked skills:** both tools prompt for the skills and the agent when run bare, and copy only the skill folders named, with no hooks or settings.

```bash
npx skills add <owner>/loadout --skill pr --skill issue -a github-copilot -g
gh skill install <owner>/loadout pr --agent github-copilot --scope user
```

- `npx skills` (Node 22.20+): `npx skills update` takes the latest; it sends anonymous telemetry unless `DO_NOT_TRACK=1`.
- `gh skill` (GitHub CLI 2.90+): `gh skill update` takes the latest, `--pin <tag-or-sha>` holds one.
- A skill installed this way is named bare (`/pr`); install it one way only, or it loads twice.
- `autopilot`, `autopilot-brief` and `image-cache` are for Claude Code on the web; skip them elsewhere.

**Rules** are imported, not installed: clone the repo and add `@<clone>/RULES.md` to `~/.claude/CLAUDE.md` (or paste its rules into another agent's instructions), plus `@<clone>/FEEDBACK.md` only where the work may be described in this collection's repo.
A rule that names a skill applies where that skill is installed.

**Claude Code on the web:** attach this repo to the environment; [`cloud/README.md`](cloud/README.md) has the Setup line, which installs both plugins and imports both rule files.

## Skills adapted from elsewhere

A skill that started from another repo names it in its frontmatter (`metadata.upstream`, `upstream-path`, `upstream-commit`) and keeps that repo's licence beside it.
`bin/check-upstream` lists the upstream commits since the pinned one; it never applies them, so local changes stay put.

## Contributing

Changes go through pull requests; [`AGENTS.md`](AGENTS.md) has the conventions and the checks that run before each commit.

## License

[MIT](LICENSE), except where a skill's own licence file says otherwise.

# loadout

Agent skills, ways of working and standing rules, packaged as a [Claude Code](https://code.claude.com) plugin marketplace, plus a setup for Claude Code on the web.

## What's inside

| Plugin | Skills | For |
|---|---|---|
| `loadout` | `pr`, `issue`, `draw-architecture`, `report-kit`, `grilling`, `writing-for-agents` | any machine |
| `cloud` | `autopilot`, `autopilot-brief`, `image-cache`, and session hooks | [Claude Code on the web](cloud/README.md) |

- [`RULES.md`](RULES.md): standing rules for an agent in any repo.
- [`ways/`](ways/README.md): ways of working a repo can adopt with one line in its `CLAUDE.md`.

The skills follow the [Agent Skills](https://agentskills.io) format, so agents other than Claude Code can read them from `skills/` as they are.

## Install

```bash
git clone https://github.com/<owner>/loadout ~/loadout
claude plugin marketplace add ~/loadout
claude plugin install loadout@loadout
```

A directory marketplace is read in place: `git pull` in the clone, and the next session has the change.
To use the standing rules, add `@~/loadout/RULES.md` to `~/.claude/CLAUDE.md`.

On Claude Code on the web, attach this repo to the environment instead; [`cloud/README.md`](cloud/README.md) has the Setup line.

## Skills adapted from elsewhere

A skill that started from another repo names it in its frontmatter (`metadata.upstream`, `upstream-path`, `upstream-commit`) and keeps that repo's licence beside it.
`bin/check-upstream` lists the upstream commits since the pinned one; it never applies them, so local changes stay put.

## Contributing

Changes go through pull requests; [`AGENTS.md`](AGENTS.md) has the conventions and the checks that run before each commit.

## License

[MIT](LICENSE), except where a skill's own licence file says otherwise.

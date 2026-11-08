# loadout

Agent skills, ways of working and standing rules, packaged as a [Claude Code](https://code.claude.com) plugin marketplace, plus a setup for Claude Code on the web.

## What's inside

| Plugin | Holds | For |
|---|---|---|
| `pr`, `issue`, `draw-architecture`, `report-kit`, `grilling`, `writing-for-agents`, `concern-to-rule` | one skill each, of the same name | any machine |
| `cloud` | `autopilot`, `autopilot-brief`, `image-cache`, and session hooks | [Claude Code on the web](cloud/README.md) |

- [`RULES.md`](RULES.md): standing rules for an agent in any repo.
- [`FEEDBACK.md`](FEEDBACK.md): the one rule that writes back to this collection's own repo, kept apart so a machine can leave it out.
- [`ways/`](ways/README.md): ways of working a repo can adopt with one line in its `CLAUDE.md`.

The skills follow the [Agent Skills](https://agentskills.io) format, so agents other than Claude Code can read them from `skills/` as they are.

## Install

Each skill is a plugin of its own, so a machine gets the skills it names and nothing else:

```bash
git clone https://github.com/<owner>/loadout ~/loadout
claude plugin marketplace add ~/loadout
claude plugin install pr@loadout
claude plugin install issue@loadout
```

A directory marketplace is read in place: `git pull` in the clone, and the next session has the change to the installed skills.
A skill added to the collection later stays off until it is installed by name.
These plugins hold skills only: no hooks, no MCP servers, no downloads, and no change to settings or to other repos.
Everything that does more is in the `cloud` plugin and `cloud/setup.sh`, which only Claude Code on the web runs.

The rules are imported, not installed: add `@~/loadout/RULES.md` to `~/.claude/CLAUDE.md`, and `@~/loadout/FEEDBACK.md` too only where the work may be described in this collection's repo.
A rule that names a skill applies where that skill is installed.

On Claude Code on the web, attach this repo to the environment instead; [`cloud/README.md`](cloud/README.md) has the Setup line, which installs every plugin and imports both rule files.

## Skills adapted from elsewhere

A skill that started from another repo names it in its frontmatter (`metadata.upstream`, `upstream-path`, `upstream-commit`) and keeps that repo's licence beside it.
`bin/check-upstream` lists the upstream commits since the pinned one; it never applies them, so local changes stay put.

## Contributing

Changes go through pull requests; [`AGENTS.md`](AGENTS.md) has the conventions and the checks that run before each commit.

## License

[MIT](LICENSE), except where a skill's own licence file says otherwise.

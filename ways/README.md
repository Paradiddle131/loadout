# Ways of working

How a repo worked on by agents keeps its documents few and current.
A repo adopts it with one line in its `CLAUDE.md` (`<owner>/<collection>`: the GitHub repo holding your copy of this collection):

```markdown
Ways of working: [ways](https://github.com/<owner>/<collection>/tree/main/ways) (on cloud, the `ways/` folder of the clone `~/.claude/CLAUDE.md` names); this file wins where it is more specific.
```

## Placement rule

- **git** holds current state the next person must read before changing code, amended in place: agent instructions, the README, one architecture document, tests.
- **GitHub** holds what is read once or appended to: progress, handoffs, run evidence, decision packets, discussion.
- A document that would be appended to belongs on GitHub: no plan, roadmap, ledger, lessons file, ADR folder or changelog of the agent's work ([`finished.md`](finished.md)).
- The record of a change is its PR body, in the `pr` skill's shape (what and evidence on one screen, the rest under `<details>`); nothing is copied from it into the repo.
- A session's durable outputs (a plan, an analysis, a visual) are artifacts on its issue, in the `issue` skill's shape; the session's other files are scratch.

## Minimal file set

- `CLAUDE.md` (or `AGENTS.md` with a one-line `CLAUDE.md`): the invariants, and a short `## Guardrails` section ([`guardrails.md`](guardrails.md)).
- `README.md`: what it is, how to run it.
- One architecture document: the current design and each major choice's reason ([`finished.md`](finished.md)).
- `DESIGN.md`: only for a repo with a UI surface.
- Nothing else is mandatory; any other document earns its place under the placement rule.

## Practices

Each line: the file, then when to use it.

- [`finished.md`](finished.md): use when planning work, making a choice with real alternatives, writing or pruning a standing document, or a line is about to cite an issue, phase or decision.
- [`guardrails.md`](guardrails.md): use when writing an owner's standing constraints, or when evidence conflicts with one.
- [`portable.md`](portable.md): use when writing or editing a reusable document (a skill, a way, a template), or a line in one names a real account, repo, date or issue.
- [`lessons.md`](lessons.md): use when changing the autopilot skill or a repo's profile; why it carries what it carries and dropped what it dropped.
- [`../skills/pr/`](../skills/pr/SKILL.md) and [`../skills/issue/`](../skills/issue/SKILL.md): use when writing a PR body, or filing an issue and keeping a session's artifacts on it.
- [`../cloud/skills/autopilot/`](../cloud/skills/autopilot/SKILL.md): use when a scheduled cloud run works a repo unattended, or a local session resumes its PRs.

#!/usr/bin/env bash
# Prints the review tier a change's paths call for: one line `routine`, `standard` or `sensitive`, then the
# changed paths that decided it (a sensitive path with the lenses REVIEW.md names for it).
#
# Usage: tier.sh [--base <ref>] [--head <ref>]
#   --base defaults to the remote's default branch (origin/HEAD, else origin/main or origin/master);
#   --head defaults to HEAD. The changed paths are `git diff --name-only --no-renames
#   $(git merge-base <base> <head>) <head>`: a rename lists both its old and its new path.
#
# Rules, highest tier among the changed paths wins; an empty diff is an error (exit 2):
# - sensitive: a built-in floor that always applies, plus the globs under `## Sensitive` in REVIEW.md (a line
#   there may end with `; lenses: a, b`). The floor: agent instruction and rule files at any depth, matched
#   whatever their case (CLAUDE.md, CLAUDE.local.md, AGENTS.md, GEMINI.md, REVIEW.md, RULES.md, SKILL.md),
#   .mcp.json and CODEOWNERS at any depth, **/.claude/**, **/.githooks/**, **/.husky/**, **/hooks/**,
#   **/githooks/**, .github/workflows/**, .github/actions/**, docs/agents/** (an unattended run's profile and
#   markers, which set what it may do and merge), and every file the base's instruction files
#   import with an `@path` line, followed through their own imports (five levels, as Claude Code does).
# - routine: the globs under `## Routine` in REVIEW.md; with no such list, **/*.md, **/*.txt and licence files.
# - standard: everything else.
# REVIEW.md (repo root) is read from the base, never from the change, so a change cannot lower its own tier.
# REVIEW.md lists globs in backticks, one or more per `- ` line, under `## Sensitive`, `## Routine` or `## Paths`
# (paths that keep their tier); each line is optionally followed by ` — <reason>` (plain text with no backtick and
# no `;`) and then by clauses in this order, each at most once: `; lenses: a, b` (lens names, `## Sensitive` only),
# `; depth: none|light|focused|full` (focused or full under `## Sensitive`) and `; effort: <lens>=<level>, ...`.
# One `Depth: <d>` line outside those lists sets the depth of standard paths (of sensitive ones too when above
# focused). The tier ignores depth and effort:
# plan.py reads them (its header has the depth rules). A glob without a slash matches the file name at any depth;
# `**` spans folders, `*` and `?` stay within one. A REVIEW.md this script cannot parse makes every path
# sensitive, with a warning on stderr. The parser is tiers.py, which plan.py shares.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tiers.py" "$@"

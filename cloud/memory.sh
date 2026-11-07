#!/bin/bash
# Writes ~/.claude/CLAUDE.md as imports of this clone's standing rules and cloud conditions, so every session
# reads the fresh clone. Run by cloud/setup.sh and by the session-start hook; the file it writes is regenerated
# each time, so edit RULES.md or cloud/CLAUDE.md instead.
set -u
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
slug=$(git -C "$ROOT" remote get-url origin 2>/dev/null | sed -nE 's#.*github\.com[:/]([^/]+/[^/.]+)(\.git)?$#\1#p')
mkdir -p ~/.claude
rm -f ~/.claude/CLAUDE.md # an older setup may have left a symlink into another clone
cat > ~/.claude/CLAUDE.md <<MD
<!-- Written by $ROOT/cloud/memory.sh; regenerated every session. -->
The collection of skills, ways and rules below is cloned at \`$ROOT\`${slug:+ (\`$slug\` on GitHub)}.

@$ROOT/RULES.md
@$ROOT/cloud/CLAUDE.md
MD

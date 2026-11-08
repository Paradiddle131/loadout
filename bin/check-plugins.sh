#!/usr/bin/env bash
# Fails when a skill path in .claude-plugin/marketplace.json holds no skill: Claude Code then refuses
# to load the whole plugin, so one removed skill would hide every other one.
# Fails too when a skill folder (skills/*, cloud/skills/*) is in no plugin: it would ship nowhere.
# A path is either one skill folder (SKILL.md inside) or a folder of skill folders.
# Run by the pre-commit hook (.githooks/).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - .claude-plugin/marketplace.json <<'EOF'
import json, pathlib, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text())
bad, shipped = [], set()
for p in m["plugins"]:
    root = pathlib.Path(p.get("source", "./"))
    for s in p.get("skills", []):
        d = root / s
        if (d / "SKILL.md").is_file():
            shipped.add(d.resolve())
        elif any(d.glob("*/SKILL.md")):
            shipped.update(f.parent.resolve() for f in d.glob("*/SKILL.md"))
        else:
            bad.append(f"{p['name']}: {s}")
if bad:
    print("check-plugins: no skill at", *bad, sep="\n  ", file=sys.stderr)
    print("check-plugins: drop the path from .claude-plugin/marketplace.json, or bring the skill back.", file=sys.stderr)
    sys.exit(1)
orphans = [str(f.parent) for g in ("skills/*/SKILL.md", "cloud/skills/*/SKILL.md")
           for f in sorted(pathlib.Path().glob(g)) if f.parent.resolve() not in shipped]
if orphans:
    print("check-plugins: in no plugin:", *orphans, sep="\n  ", file=sys.stderr)
    print("check-plugins: give each its own plugin in .claude-plugin/marketplace.json.", file=sys.stderr)
    sys.exit(1)
print(f"check-plugins: {len(m['plugins'])} plugins, every skill path holds a skill")
EOF

#!/usr/bin/env bash
# Fails when a skill path in .claude-plugin/marketplace.json holds no skill: Claude Code then refuses
# to load the whole plugin, so one removed skill would hide every other one.
# A path is either one skill folder (SKILL.md inside) or a folder of skill folders.
# Also fails on a plugin agent (every .md under the plugin's agents/, or the files its `agents` key lists)
# whose frontmatter lacks name, description, tools, model or effort: Claude Code still loads a broken one,
# silently, under its file name and with every field ignored, so it would inherit the session's model and
# every tool. A README or notes file under agents/ would load as an agent too, so none may sit there.
# Run by the pre-commit hook (.githooks/).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - .claude-plugin/marketplace.json <<'EOF'
import json, pathlib, re, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text())
REQUIRED = ("name", "description", "tools", "model", "effort")
bad, agents = [], 0
for p in m["plugins"]:
    root = pathlib.Path(p.get("source", "./"))
    for s in p.get("skills", []):
        d = root / s
        if not ((d / "SKILL.md").is_file() or any(d.glob("*/SKILL.md"))):
            bad.append(f"{p['name']}: no skill at {s}")
    listed = p.get("agents")
    files = [root / a for a in ([listed] if isinstance(listed, str) else listed)] if listed else sorted((root / "agents").rglob("*.md"))
    for f in files:
        agents += 1
        text = f.read_text() if f.is_file() else ""
        head = re.match(r"---\n(.*?)\n---\n", text, re.S)
        keys = dict(re.findall(r"^([A-Za-z]+):[ \t]*(.*)$", head.group(1), re.M)) if head else {}
        missing = [k for k in REQUIRED if not keys.get(k, "").strip()]
        if missing:
            bad.append(f"{p['name']}: agent {f} lacks {', '.join(missing)}")
        elif keys["model"].strip() == "inherit":
            bad.append(f"{p['name']}: agent {f} inherits its model; name one")
if bad:
    print("check-plugins:", *bad, sep="\n  ", file=sys.stderr)
    print("check-plugins: fix the path or the agent's frontmatter in place, or drop it.", file=sys.stderr)
    sys.exit(1)
print(f"check-plugins: {len(m['plugins'])} plugins, every skill path holds a skill, {agents} agents with full frontmatter")
EOF

#!/usr/bin/env bash
# Fails when a skill path in .claude-plugin/marketplace.json holds no skill: Claude Code then refuses
# to load the whole plugin, so one removed skill would hide every other one.
# A path is either one skill folder (SKILL.md inside) or a folder of skill folders.
# Also checks each plugin agent (every .md under the plugin's agents/, or the files its `agents` key lists).
# Claude Code loads a broken one silently, under its file name with every field ignored, so it would run on
# the session's model with every tool; a README under agents/ would load as an agent too. An agent fails on:
# - a missing name, description, tools, model or effort, or a `:` in name (reserved for plugin scope);
# - a model other than sonnet, opus, haiku, fable or a full claude- id (inherit included), or an effort
#   other than low, medium, high, xhigh or max;
# - Edit, Write or NotebookEdit in tools: these are read-only review agents; an editing agent needs this rule changed;
# - a `## How you work` section that differs between agent files: it is one shared block, inlined on purpose.
# Run by the pre-commit hook (.githooks/).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - .claude-plugin/marketplace.json <<'EOF'
import json, pathlib, re, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text())
REQUIRED = ("name", "description", "tools", "model", "effort")
MODELS = {"sonnet", "opus", "haiku", "fable"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
EDITING = {"Edit", "Write", "NotebookEdit"}


def frontmatter(text):
    head = re.match(r"---\n(.*?)\n---\n", text, re.S)
    keys, last = {}, None
    for line in (head.group(1).splitlines() if head else []):
        if (kv := re.match(r"^([A-Za-z]+):[ \t]*(.*?)\s*$", line)):
            last = kv.group(1)
            keys[last] = kv.group(2).strip("'\"")
        elif last and (item := re.match(r"^\s+-\s+(.*?)\s*$", line)):
            keys[last] = (keys[last] + ", " if keys[last] else "") + item.group(1)  # YAML block list
    return keys


bad, agents, blocks = [], 0, {}
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
        keys = frontmatter(text)
        why = [f"lacks {k}" for k in REQUIRED if not keys.get(k, "").strip()]
        if ":" in keys.get("name", ""):
            why.append("has a ':' in name")
        model, effort = keys.get("model", ""), keys.get("effort", "")
        if model and model not in MODELS and not re.fullmatch(r"claude-[a-z0-9.-]+", model):
            why.append(f"names model {model!r}")
        if effort and effort not in EFFORTS:
            why.append(f"names effort {effort!r}")
        tools = {re.sub(r"\(.*", "", t).strip() for t in keys.get("tools", "").strip("[]").split(",")}
        if tools & EDITING:
            why.append(f"grants {', '.join(sorted(tools & EDITING))}")
        if (how := re.search(r"^## How you work\n.*?(?=^## |\Z)", text, re.S | re.M)):
            blocks.setdefault(how.group(0), []).append(str(f))
        else:
            why.append("has no '## How you work' section")
        bad += [f"{p['name']}: agent {f} {w}" for w in why]
if len(blocks) > 1:
    bad.append("the '## How you work' block differs: " + " | ".join(", ".join(v) for v in blocks.values()))
if bad:
    print("check-plugins:", *bad, sep="\n  ", file=sys.stderr)
    print("check-plugins: fix the path or the agent in place, or drop it.", file=sys.stderr)
    sys.exit(1)
print(f"check-plugins: {len(m['plugins'])} plugins, every skill path holds a skill, {agents} read-only agents share one 'How you work' block")
EOF

#!/usr/bin/env python3
"""PreToolUse hook: the owner's effort cap holds on every subagent, workflow agent and created session.

`LOADOUT_MAX_EFFORT` (low, medium, high, xhigh or max) is the cap; unset or empty means no cap, and the hook passes
every call. Any other value refuses every call it reads until the owner fixes it, so a typo never reads as no cap.
The owner sets it in the environment Claude Code starts with: on Claude Code on the web, the cloud environment's
variables in Settings; locally, `env` in `~/.claude/settings.json`. It takes effect at the next session start.

What it reads, with the cap set (levels ranked low < medium < high < xhigh < max; a value is a level only when it is
one of the five words, exactly, in lower case):
- `Agent` (`Task` in older builds): the call's `effort`, refused above the cap or when it is not a level. With no
  `effort`, the definition `subagent_type` names: `<plugin>:<name>` is looked up in that plugin's `agents/` folder
  (this plugin's own, else the install paths `~/.claude/plugins/installed_plugins.json` lists for it), a bare name
  in `<cwd>/.claude/agents/`, `~/.claude/agents/` and this plugin's `agents/`, matched against each file's
  frontmatter `name` and its file name, case-insensitively; every match counts, and one whose `effort` is above the
  cap or not a level refuses.
- `Workflow`: the script, from `scriptPath` (relative to the call's `cwd`), else `script`, else `name` looked up as
  `.claude/workflows/<name>.js` from the `cwd` up and in `~/.claude/workflows/`; a call whose script it cannot read
  (a built-in workflow, a bare `resumeFromRunId`) is refused. Every appearance of the word `effort` in the script,
  in any case, must be an option `effort: '<level>'` (any quote, the key quoted or not) whose value is followed,
  past blanks and line breaks, by a `,` or a `}`, at or below the cap; anything else (a variable, a template, an expression, a comment
  that names it) refuses the whole call, since a computed value cannot be read from the text. `args` is read the
  same way: a key that holds the word must hold a level at or below the cap, and a string that is the word refuses.
- `mcp__<server>__create_session`: its `effort`, as for `Agent`.
Every other tool passes.

Not seen, stated as limits: the effort an omitted field falls back to (the session's, a built-in agent type's, or a
definition this hook cannot find, such as one in a plugin loaded from `--plugin-dir`); a workflow `agent()` call
with no `effort` option; a key spelled so the word does not appear (`'eff' + 'ort'`, an escape); a call made by any
other tool. The merge guard never reads effort, and neither do the review records: they accept a lens at or above
min(plan, cap), and this hook is what refuses a run above the cap.

Hook mode: the hook's JSON on stdin, a deny decision or nothing on stdout, exit 0. With the cap set, input it cannot
read, or a failure of its own, refuses the call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

VAR = "LOADOUT_MAX_EFFORT"
LEVELS = ("low", "medium", "high", "xhigh", "max")
RANK = {e: i for i, e in enumerate(LEVELS)}
ROOT = Path(__file__).resolve().parents[1]  # this plugin's root: agents/ sits beside hooks/
SESSION_TOOL = re.compile(r"mcp__.+__create_session")
WORD = re.compile(r"effort", re.I)
# An option the hook can read: the word as a key (quoted or not), a colon, a quoted level, then the value's end.
OPTION = re.compile(r"""effort['"`]?\s*:\s*(['"`])([A-Za-z]*)\1(?=\s*[,}])""")


class Refusal(Exception):
    """The call is above the cap, or the hook cannot tell that it is not: the reason."""


def cap_of(env: dict[str, str]) -> str | None:
    raw = env.get(VAR, "").strip()
    if not raw:
        return None
    if raw not in RANK:
        raise Refusal(f"{VAR} is {raw!r}, which is none of {', '.join(LEVELS)}, so the cap cannot be read and every "
                      "Agent, Workflow and create_session call is refused; the owner fixes it where it is set (the "
                      "cloud environment's variables in Settings, or `env` in ~/.claude/settings.json) and starts a "
                      "new session")
    return raw


def check_level(value: object, cap: str, what: str) -> None:
    if not isinstance(value, str) or value not in RANK:
        raise Refusal(f"{what} is {value!r}, not one of {', '.join(LEVELS)}, so the hook cannot tell it is at or below "
                      f"the cap {cap}")
    if RANK[value] > RANK[cap]:
        raise Refusal(f"{what} is {value}, above the cap {cap}")


# Agent definitions.


def frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return {}
    head = re.match(r"---\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    keys: dict[str, str] = {}
    for line in head.group(1).split("\n") if head else []:
        if kv := re.match(r"([A-Za-z_-]+):[ \t]*(.*?)\s*$", line):
            keys[kv.group(1).lower()] = kv.group(2).strip().strip("'\"")
    return keys


def config_dir(env: dict[str, str]) -> Path:
    if env.get("CLAUDE_CONFIG_DIR"):
        return Path(env["CLAUDE_CONFIG_DIR"])
    return Path(env.get("HOME") or Path.home()) / ".claude"


def plugin_dirs(plugin: str, env: dict[str, str]) -> list[Path]:
    """The `agents/` folders of the plugin named `plugin`: this one's own, and the install paths listed for it."""
    dirs = [ROOT / "agents"] if plugin == "loadout" else []
    try:
        listed = json.loads((config_dir(env) / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        listed = {}
    plugins = listed.get("plugins") if isinstance(listed, dict) else None
    for key, installs in (plugins.items() if isinstance(plugins, dict) else []):
        if str(key).split("@", 1)[0].lower() != plugin or not isinstance(installs, list):
            continue
        for i in installs:
            if isinstance(i, dict) and isinstance(i.get("installPath"), str):
                dirs.append(Path(i["installPath"]) / "agents")
    return dirs


def definitions(subagent_type: str, cwd: Path, env: dict[str, str]) -> list[tuple[Path, dict[str, str]]]:
    """Every definition file `subagent_type` may name, with its frontmatter (module docstring)."""
    wanted = subagent_type.strip().lower()
    if ":" in wanted:
        plugin, name = wanted.split(":", 1)
        dirs = plugin_dirs(plugin, env)
    else:
        name = wanted
        dirs = [cwd / ".claude" / "agents", config_dir(env) / "agents", ROOT / "agents"]
    found, seen = [], set()
    for d in dirs:
        for f in sorted(d.rglob("*.md")) if d.is_dir() else []:
            keys = frontmatter(f)
            real = f.resolve()
            if real in seen or name not in (keys.get("name", "").lower(), f.stem.lower()):
                continue
            seen.add(real)
            found.append((f, keys))
    return found


def check_agent(inp: dict, cap: str, cwd: Path, env: dict[str, str]) -> None:
    if inp.get("effort") is not None:
        check_level(inp["effort"], cap, "the call's effort")
        return
    kind = inp.get("subagent_type")
    if not isinstance(kind, str) or not kind.strip():
        return  # the built-in default agent: no definition to read (a stated limit)
    for f, keys in definitions(kind, cwd, env):
        if "effort" in keys:
            check_level(keys["effort"], cap, f"the call omits effort, and the definition {kind!r} ({f}) sets effort, "
                        "which")


# Workflows.


def workflow_script(inp: dict, cwd: Path, env: dict[str, str]) -> str:
    path = inp.get("scriptPath")
    if isinstance(path, str) and path.strip():
        p = Path(path).expanduser()
        p = p if p.is_absolute() else cwd / p
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise Refusal(f"the workflow's scriptPath {path!r} cannot be read, so the efforts it sets cannot be "
                          "checked against the cap") from None
    if isinstance(inp.get("script"), str):
        return inp["script"]
    name = inp.get("name")
    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._-]+", name) and ".." not in name:
        places = [d / ".claude" / "workflows" / f"{name}.js" for d in (cwd, *cwd.parents)]
        places.append(config_dir(env) / "workflows" / f"{name}.js")
        for p in places:
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace")
    raise Refusal("the hook cannot read this workflow's script (a built-in or unknown name, or a resume without "
                  "scriptPath), so the efforts it sets cannot be checked against the cap; pass the script inline or "
                  "by scriptPath")


def check_script(text: str, cap: str) -> None:
    options = {m.start(): m for m in OPTION.finditer(text)}
    for w in WORD.finditer(text):
        line = text.count("\n", 0, w.start()) + 1
        m = options.get(w.start())
        if m is None or text[w.start():w.end()] != "effort":
            raise Refusal(f"the workflow script names effort on line {line} other than as an `effort: '<level>'` "
                          "option, so the effort it sets cannot be read from the text")
        check_level(m.group(2), cap, f"the workflow script's effort on line {line}")


def check_args(value: object, cap: str) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if WORD.search(str(k)):
                check_level(v, cap, f"the workflow's args key {k!r}")
            else:
                check_args(v, cap)
    elif isinstance(value, list):
        for v in value:
            check_args(v, cap)
    elif isinstance(value, str) and value.strip().lower() == "effort":
        raise Refusal("the workflow's args hold the word effort as a value, so the effort the script sets from them "
                      "cannot be read")


# The decision.


def decide(event: object, env: dict[str, str]) -> str | None:
    """The refusal's reason, or None when the call passes."""
    if not env.get(VAR, "").strip():
        return None
    tool = event.get("tool_name") if isinstance(event, dict) else None
    if isinstance(tool, str) and tool not in ("Agent", "Task", "Workflow") and not SESSION_TOOL.fullmatch(tool):
        return None  # hooks/hooks.json sends only the three; any other tool passes, under any cap
    try:
        cap = cap_of(env)
        if cap is None:
            return None
        if not isinstance(event, dict):
            raise Refusal("the hook's input cannot be read")
        inp = event.get("tool_input")
        if not isinstance(tool, str) or not isinstance(inp, dict):
            raise Refusal("the call's input cannot be read")
        cwd = Path(event["cwd"]) if isinstance(event.get("cwd"), str) and event["cwd"] else Path.cwd()
        if tool in ("Agent", "Task"):
            check_agent(inp, cap, cwd, env)
        elif tool == "Workflow":
            check_script(workflow_script(inp, cwd, env), cap)
            check_args(inp.get("args"), cap)
        elif inp.get("effort") is not None:
            check_level(inp["effort"], cap, "the created session's effort")
        return None
    except Refusal as exc:
        reason = str(exc)
    except Exception as exc:  # noqa: BLE001  (with a cap set, a failure of its own refuses)
        reason = f"the hook failed ({type(exc).__name__}: {exc})"
    cap = env.get(VAR, "").strip()
    if cap not in RANK:
        return f"Effort cap: refused: {reason}."
    return (f"Effort cap: refused: {reason}. The owner caps every subagent, workflow agent and created session at "
            f"{VAR}={cap}: set effort to {cap} or lower in the call.")


def main() -> int:
    env = dict(os.environ)
    if not env.get(VAR, "").strip():
        return 0
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except ValueError:
        event = None
    reason = decide(event, env)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

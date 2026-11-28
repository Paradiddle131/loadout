"""The effort-cap hook (hooks/effort-cap.py), run as Claude Code runs it: the hook's JSON on stdin, a deny or nothing.

Run: uvx --from pytest==8.4.2 pytest -q hooks/tests
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
HOOK = HOOKS / "effort-cap.py"
ROOT = HOOKS.parent
VAR = "LOADOUT_MAX_EFFORT"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / ".claude").mkdir(parents=True)
    return h


def run(event: object, cap: str | None, home: Path, raw: str | None = None, **extra: str) -> tuple[str | None, str]:
    """The hook's deny reason (None when it passes) and its stderr."""
    env = {k: v for k, v in os.environ.items() if k not in (VAR, "CLAUDE_CONFIG_DIR")}
    env.update({"HOME": str(home), **extra})
    if cap is not None:
        env[VAR] = cap
    done = subprocess.run([sys.executable, str(HOOK)], input=raw if raw is not None else json.dumps(event),
                          env=env, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    if not done.stdout.strip():
        return None, done.stderr
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"], done.stderr


def call(tool: str, cwd: Path | None = None, **inp: object) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp, "cwd": str(cwd or ROOT)}


def agent_file(d: Path, name: str, effort: str | None, stem: str | None = None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", "description: x"] + ([f"effort: {effort}"] if effort else []) + ["---", "body"]
    (d / f"{stem or name}.md").write_text("\n".join(lines) + "\n")


# The cap itself.


@pytest.mark.parametrize("cap", [None, ""])
def test_no_cap_passes_every_call(home: Path, cap: str | None) -> None:
    assert run(call("Agent", effort="max", subagent_type="loadout:correctness-reviewer"), cap, home)[0] is None
    assert run(call("Workflow", script="agent('x', {effort: someVar})"), cap, home)[0] is None


@pytest.mark.parametrize("cap", ["huge", "Medium", "HIGH", "1", "none"])
def test_a_cap_outside_the_five_levels_refuses_naming_the_variable(home: Path, cap: str) -> None:
    reason, _ = run(call("Agent", effort="low"), cap, home)
    assert reason and VAR in reason and repr(cap) in reason and "Settings" in reason


def test_a_bad_cap_still_passes_tools_the_hook_does_not_read(home: Path) -> None:
    assert run(call("Bash", command="ls"), "huge", home)[0] is None


def test_input_it_cannot_read_refuses_under_a_cap(home: Path) -> None:
    assert "cannot be read" in run(None, "medium", home, raw="not json")[0]
    assert "cannot be read" in run({"tool_name": "Agent", "tool_input": "x"}, "medium", home)[0]


# Agent.


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_agent_above_the_cap_refuses_naming_the_cap_and_the_variable(home: Path, tool: str) -> None:
    reason, _ = run(call(tool, effort="high", subagent_type="Explore"), "medium", home)
    assert reason and "high" in reason and f"{VAR}=medium" in reason


@pytest.mark.parametrize("effort", ["low", "medium"])
def test_agent_at_or_below_the_cap_passes(home: Path, effort: str) -> None:
    assert run(call("Agent", effort=effort, subagent_type="loadout:correctness-reviewer"), "medium", home)[0] is None


@pytest.mark.parametrize("effort", ["HIGH", "Medium", "ultra", "", 3, ["low"]])
def test_agent_effort_that_is_not_a_level_refuses(home: Path, effort: object) -> None:
    assert "not one of" in run(call("Agent", effort=effort), "max", home)[0]


@pytest.mark.parametrize("kind", ["loadout:correctness-reviewer", "LOADOUT:Correctness-Reviewer", "correctness-reviewer",
                                  " loadout:correctness-reviewer "])
def test_agent_omitting_effort_reads_the_definition_s_effort(home: Path, kind: str) -> None:
    reason, _ = run(call("Agent", subagent_type=kind), "medium", home)
    assert reason and "correctness-reviewer.md" in reason and "high" in reason
    assert run(call("Agent", subagent_type=kind), "high", home)[0] is None


def test_agent_omitting_effort_passes_a_definition_at_the_cap(home: Path) -> None:
    assert run(call("Agent", subagent_type="loadout:finding-auditor"), "medium", home)[0] is None  # effort: medium


def test_agent_omitting_effort_reads_project_and_user_definitions_by_name(home: Path, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    agent_file(proj / ".claude/agents", "deep-thinker", "xhigh", stem="some-file")
    agent_file(home / ".claude/agents", "user-agent", "max")
    assert "xhigh" in run(call("Agent", cwd=proj, subagent_type="deep-thinker"), "high", home)[0]
    assert "max" in run(call("Agent", cwd=proj, subagent_type="user-agent"), "high", home)[0]
    assert run(call("Agent", cwd=proj, subagent_type="deep-thinker"), "xhigh", home)[0] is None


def test_agent_omitting_effort_reads_another_installed_plugin_s_definition(home: Path, tmp_path: Path) -> None:
    install = tmp_path / "cache/other/1.0"
    agent_file(install / "agents", "reviewer", "max")
    (home / ".claude/plugins").mkdir(parents=True)
    (home / ".claude/plugins/installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"other@example-market": [{"installPath": str(install)}]}}))
    assert "max" in run(call("Agent", subagent_type="other:reviewer"), "high", home)[0]


def test_a_definition_whose_effort_is_not_a_level_refuses(home: Path, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    agent_file(proj / ".claude/agents", "odd", "High")
    assert "not one of" in run(call("Agent", cwd=proj, subagent_type="odd"), "max", home)[0]


def test_agent_omitting_effort_with_no_readable_definition_passes_a_stated_limit(home: Path, tmp_path: Path) -> None:
    for kind in (None, "Explore", "general-purpose", "nowhere:agent"):
        inp = {"prompt": "x"} | ({"subagent_type": kind} if kind else {})
        assert run(call("Agent", cwd=tmp_path, **inp), "low", home)[0] is None
    agent_file(tmp_path / ".claude/agents", "no-effort", None)
    assert run(call("Agent", cwd=tmp_path, subagent_type="no-effort"), "low", home)[0] is None


# create_session.


def test_create_session_above_the_cap_refuses_and_at_it_passes(home: Path) -> None:
    tool = "mcp__claude-code-remote__create_session"
    reason, _ = run(call(tool, effort="xhigh", prompt="x"), "high", home)
    assert reason and "xhigh" in reason and f"{VAR}=high" in reason
    assert run(call(tool, effort="high"), "high", home)[0] is None
    assert run(call(tool, prompt="x"), "low", home)[0] is None  # omitted: the default, a stated limit
    assert "not one of" in run(call(tool, effort="MAX"), "max", home)[0]


# Workflow.

OK_SCRIPT = """export const meta = { name: 'w', description: 'd' }
const a = await agent('one', { effort: 'medium', label: 'a' })
const b = await agent("two", {
  "effort": "low"
})
await agent(`three`, {effort:`medium`})
"""


def test_workflow_with_literal_levels_at_or_below_the_cap_passes(home: Path) -> None:
    assert run(call("Workflow", script=OK_SCRIPT), "medium", home)[0] is None
    assert run(call("Workflow", script="export const meta = {name: 'w', description: 'd'}\nawait agent('x')"),
               "low", home)[0] is None  # no effort option: the session's, a stated limit


@pytest.mark.parametrize("script, why", [
    ("agent('x', { effort: 'high' })", "above the cap"),
    ("agent('x', { effort: 'HIGH' })", "not one of"),
    ("agent('x', { effort: level })", "other than"),
    ("const e = 'high'\nagent('x', { effort: e })", "other than"),
    ("agent('x', { effort })", "other than"),
    ("agent('x', { effort: `${lvl}` })", "other than"),
    ("agent('x', { effort: 'low' + suffix })", "other than"),
    ("agent('x', { effort: 'low'\n ? 'max' : 'low' })", "other than"),
    ("agent('x', { effort: 'low' || 'max' })", "other than"),
    ("const o = {}; o.effort = 'max'; agent('x', o)", "other than"),
    ("const o = {}; o['effort'] = 'max'; agent('x', o)", "other than"),
    ("agent('x', { Effort: 'low' })", "other than"),
    ("agent('x', { EFFORT: 'max' })", "other than"),
    ("agent('x', { ...args.opts, effort: 'low' }) // effort set above", "other than"),
    ("agent('x', { effort: 'low', maxEffort: 'max' })", "other than"),
])
def test_workflow_effort_above_the_cap_or_not_a_literal_level_refuses_the_whole_call(home: Path, script: str,
                                                                                    why: str) -> None:
    reason, _ = run(call("Workflow", script=OK_SCRIPT + script), "medium", home)
    assert reason and why in reason and f"{VAR}=medium" in reason


def test_workflow_script_path_and_saved_name_are_read(home: Path, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "w.js").write_text("agent('x', {effort: 'max'})\n")
    assert "max" in run(call("Workflow", cwd=proj, scriptPath="w.js", script=OK_SCRIPT), "high", home)[0]
    (proj / ".claude/workflows").mkdir(parents=True)
    (proj / ".claude/workflows/saved.js").write_text("agent('x', {effort: 'xhigh'})\n")
    assert "xhigh" in run(call("Workflow", cwd=proj / "sub", name="saved"), "high", home)[0]
    (home / ".claude/workflows").mkdir(parents=True)
    (home / ".claude/workflows/mine.js").write_text("agent('x', {effort: 'low'})\n")
    assert run(call("Workflow", cwd=proj, name="mine"), "low", home)[0] is None


@pytest.mark.parametrize("inp", [{"name": "built-in-or-unknown"}, {"resumeFromRunId": "run-1"},
                                 {"scriptPath": "missing.js"}, {"name": "../../etc/x"}])
def test_workflow_whose_script_cannot_be_read_refuses(home: Path, tmp_path: Path, inp: dict) -> None:
    assert "cannot" in run(call("Workflow", cwd=tmp_path, **inp), "max", home)[0]


@pytest.mark.parametrize("args, passes", [
    ({"effort": "low"}, True), ({"q": "reduce the effort of x"}, True), ({"effort": "high"}, False),
    ({"opts": {"Effort": "max"}}, False), ({"k": "effort", "v": "max"}, False), ([{"effort": None}], False),
])
def test_workflow_args_are_read_like_the_script(home: Path, args: object, passes: bool) -> None:
    reason, _ = run(call("Workflow", script=OK_SCRIPT, args=args), "medium", home)
    assert (reason is None) == passes, reason


# The plugin wiring.


def test_the_loadout_plugin_registers_the_hook_for_the_three_tools() -> None:
    import re
    hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    (entry,) = [h for h in hooks if "effort-cap.py" in h["hooks"][0]["command"]]
    m = re.compile(entry["matcher"])
    for tool in ("Agent", "Task", "Workflow", "mcp__claude-code-remote__create_session"):
        assert m.fullmatch(tool), tool
    for tool in ("Bash", "AgentX", "mcp__x__create_session_later"):
        assert not m.fullmatch(tool), tool
    plugins = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"]
    assert [p for p in plugins if p["name"] == "loadout"][0]["source"] == "./"  # hooks/hooks.json is its default


@pytest.mark.parametrize("doc", ["skills/review/SKILL.md", "skills/delegating/SKILL.md", "RULES.md"])
def test_the_docs_say_where_the_owner_sets_the_cap_and_when_it_holds(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    for words in (VAR, "the cloud environment's variables in Settings", "`env` of `~/.claude/settings.json`",
                  "next session start"):
        assert words in text, (doc, words)

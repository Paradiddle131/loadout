"""The merge guard (cloud/hooks/merge-guard.py) against a stub `gh` (skills/review/scripts/tests/stub_gh.py).

Run: uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
GUARD = HOOKS / "merge-guard.py"
ROOT = HOOKS.parent.parent
STUB = ROOT / "skills/review/scripts/tests/stub_gh.py"
REPO = "example-owner/example-repo"
HEAD, OLD = "b" * 40, "a" * 40
BOTH = {"loadout/gates": "success", "loadout/review": "success"}


@pytest.fixture
def fx(tmp_path: Path) -> Path:
    d = tmp_path / "fx"
    d.mkdir()
    (d / "pr.json").write_text(json.dumps({"number": 12, "head": {"sha": HEAD}}))
    (d / "pulls.json").write_text(json.dumps([{"number": 12}]))
    return d


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    r = tmp_path / "clone"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feature"], cwd=r, check=True)
    subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=r, check=True)
    return r


def statuses(fx: Path, by_sha: dict[str, dict[str, str]]) -> None:
    (fx / "statuses.json").write_text(json.dumps(by_sha))


def run(fx: Path, event: dict, cwd: Path, gh: bool = True, **env: str) -> str | None:
    bin_dir = fx.parent / "bin"
    bin_dir.mkdir(exist_ok=True)
    if gh and not (bin_dir / "gh").exists():
        STUB.chmod(0o755)
        (bin_dir / "gh").symlink_to(STUB)
    event = {"hook_event_name": "PreToolUse", "cwd": str(cwd), **event}
    e = {k: v for k, v in os.environ.items() if k != "GH_REPO"}
    done = subprocess.run(
        [sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, timeout=60,
        env={**e, "PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_DIR": str(fx), **env},
    )
    assert done.returncode == 0, done.stderr
    if not done.stdout.strip():
        return None
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def bash(fx: Path, command: str, cwd: Path, **env: str) -> str | None:
    return run(fx, {"tool_name": "Bash", "tool_input": {"command": command}}, cwd, **env)


def mcp(fx: Path, cwd: Path, **tool_input: object) -> str | None:
    data = {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, **tool_input}
    return run(fx, {"tool_name": "mcp__github__merge_pull_request", "tool_input": data}, cwd)


def gets(fx: Path) -> list[str]:
    p = fx / "calls.jsonl"
    return [json.loads(x)["endpoint"] for x in p.read_text().splitlines()] if p.exists() else []


def test_hooks_json_registers_the_guard_for_bash_and_the_merge_tools() -> None:
    hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    [entry] = [m for m in hooks if any("merge-guard.py" in h["command"] for h in m["hooks"])]
    matcher = re.compile(entry["matcher"])
    for name in ("Bash", "mcp__github__merge_pull_request", "mcp__plugin_x_github__merge_pull_request",
                 "mcp__github__enable_pr_auto_merge"):
        assert matcher.search(name), name
    for name in ("Read", "mcp__github__get_commit", "BashOutput"):
        assert not matcher.search(name), name


def test_mcp_merge_with_both_statuses_on_the_named_head_passes(fx: Path, clone: Path) -> None:
    statuses(fx, {HEAD: BOTH})
    assert mcp(fx, clone, expectedHeadSha=HEAD) is None
    assert f"repos/{REPO}/commits/{HEAD}/status?per_page=100" in gets(fx)


@pytest.mark.parametrize("missing", ["loadout/gates", "loadout/review"])
def test_each_missing_status_is_named_with_its_script(fx: Path, clone: Path, missing: str) -> None:
    statuses(fx, {HEAD: {c: s for c, s in BOTH.items() if c != missing}})
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and f"`{missing}` is absent" in reason
    assert ("gate_stamp.sh" if missing == "loadout/gates" else "verdict.sh") in reason


def test_a_failed_review_refuses(fx: Path, clone: Path) -> None:
    statuses(fx, {HEAD: {**BOTH, "loadout/review": "failure"}})
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "`loadout/review` is failure" in reason


def test_statuses_on_an_older_head_do_not_count(fx: Path, clone: Path) -> None:
    statuses(fx, {OLD: BOTH})
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "lacks a recorded success" in reason and HEAD in reason


def test_a_merge_naming_an_older_head_refuses(fx: Path, clone: Path) -> None:
    statuses(fx, {OLD: BOTH, HEAD: BOTH})
    reason = mcp(fx, clone, expectedHeadSha=OLD)
    assert reason and f"is now {HEAD}" in reason


def test_a_merge_naming_no_head_is_asked_to_name_it(fx: Path, clone: Path) -> None:
    statuses(fx, {HEAD: BOTH})
    reason = mcp(fx, clone)
    assert reason and f"expectedHeadSha: {HEAD}" in reason


@pytest.mark.parametrize("fail_on", [f"pulls/12", f"commits/{HEAD}/status"])
def test_unreadable_github_fails_closed(fx: Path, clone: Path, fail_on: str) -> None:
    statuses(fx, {HEAD: BOTH})
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": HEAD}}, clone, STUB_FAIL=fail_on)
    assert reason and "fails closed" in reason and "HTTP 502" in reason


def test_no_gh_at_all_fails_closed(fx: Path, clone: Path) -> None:
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": HEAD}}, clone, gh=False)
    assert reason and "fails closed" in reason


def test_auto_merge_is_refused(fx: Path, clone: Path) -> None:
    statuses(fx, {HEAD: BOTH})
    assert run(fx, {"tool_name": "mcp__github__enable_pr_auto_merge",
                    "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12}}, clone)
    assert bash(fx, f"gh pr merge 12 --auto --match-head-commit {HEAD}", clone)


SHELL_MERGES = [
    "gh pr merge 12 --squash",
    f"gh pr merge 12 -R {REPO} --squash",
    "gh pr merge https://github.com/example-owner/example-repo/pull/12",
    "gh pr merge feature",
    "gh pr merge",
    "cd {clone} && gh pr merge 12",
    "GH_REPO=example-owner/example-repo gh pr merge 12",
    f"gh api -X PUT repos/{REPO}/pulls/12/merge -f merge_method=squash",
    f"gh api --method PUT /repos/{REPO}/pulls/12/merge",
    "gh api -X PUT 'repos/{{owner}}/{{repo}}/pulls/12/merge'",
    "timeout 30 gh pr merge 12",
    "bash -c 'gh pr merge 12 --squash'",
    "eval gh pr merge 12",
    "bash <<'EOF'\ngh pr merge 12\nEOF",
    "echo start; gh pr merge 12 | tail -1",
]


@pytest.mark.parametrize("command", SHELL_MERGES)
def test_each_shell_merge_is_checked(fx: Path, clone: Path, command: str) -> None:
    command = command.replace("{clone}", str(clone)).replace("{{", "{").replace("}}", "}")
    statuses(fx, {HEAD: {"loadout/gates": "success"}})
    reason = bash(fx, command, clone)
    assert reason and "`loadout/review` is absent" in reason, command
    assert f"repos/{REPO}/pulls/12" in gets(fx), command


def test_a_shell_merge_with_both_statuses_naming_the_head_passes(fx: Path, clone: Path) -> None:
    statuses(fx, {HEAD: BOTH})
    assert bash(fx, f"gh pr merge 12 --squash --match-head-commit {HEAD}", clone) is None
    assert bash(fx, f"gh api -X PUT repos/{REPO}/pulls/12/merge -f sha={HEAD}", clone) is None
    assert bash(fx, "gh pr merge 12 --squash", clone)  # names no head


def test_a_merge_outside_rest_is_refused(fx: Path, clone: Path) -> None:
    assert bash(fx, "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
                clone)
    assert bash(fx, f"curl -X PUT https://api.github.com/repos/{REPO}/pulls/12/merge", clone)


ALLOWED = [
    "gh pr view 12",
    "gh pr list",
    f"gh api repos/{REPO}/pulls/12/merge",  # GET: is it merged?
    f"gh api repos/{REPO}/pulls/12",
    "echo 'gh pr merge 12'",
    "cat > notes.md <<'EOF'\ngh pr merge 12\ngit commit --no-verify\nEOF",
    "git commit -m 'teach the guard about -n and --no-verify'",
    "git commit -am 'x'",
    "git push -n origin main",  # push's -n is --dry-run
    "git push origin feature",
    "ls -la",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_other_commands_pass_without_reading_github(fx: Path, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command
    assert gets(fx) == [], command


NO_VERIFY = [
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git commit -anm x",
    "git -C /tmp/x commit --no-verify",
    "git push --no-verify origin feature",
    "git -c core.hooksPath=/dev/null commit -m x",
    "cd /tmp && git commit -qnm x",
    "bash -c 'git push --no-verify'",
]


@pytest.mark.parametrize("command", NO_VERIFY)
def test_no_verify_is_refused(fx: Path, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "fix what it names" in reason, command


def test_a_guard_failure_on_a_merge_fails_closed_and_passes_other_calls(fx: Path, clone: Path,
                                                                       tmp_path: Path) -> None:
    # A copy of the guard without the GCP guard beside it: the shell parser cannot load.
    lone = tmp_path / "lone" / "hooks"
    lone.mkdir(parents=True)
    shutil.copy(GUARD, lone / "merge-guard.py")
    for command, refused in (("gh pr merge 12", True), ("ls -la", False)):
        done = subprocess.run([sys.executable, str(lone / "merge-guard.py")], capture_output=True, text=True,
                              input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                                                "cwd": str(clone)}), check=True)
        assert bool(done.stdout.strip()) is refused, command
        if refused:
            assert "fails closed" in done.stdout


def test_bad_input_passes_silently(fx: Path) -> None:
    done = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""

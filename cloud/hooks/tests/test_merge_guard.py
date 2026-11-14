"""The merge guard (cloud/hooks/merge-guard.py) against a stub `gh` (skills/review/scripts/tests/stub_gh.py).

Records are built with the review skill's own builder (skills/review/scripts/record.py), so the format the
scripts post and the format the guard reads cannot drift apart unnoticed.
Run: uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests
"""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
GUARD = HOOKS / "merge-guard.py"
ROOT = HOOKS.parent.parent
STUB = ROOT / "skills/review/scripts/tests/stub_gh.py"
RECORD = ROOT / "skills/review/scripts/record.py"
REPO = "example-owner/example-repo"
HEAD, OLD = "b" * 40, "a" * 40
ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def record(kind: str, sha: str = HEAD, state: str = "success", tier: str = "standard") -> str:
    if kind == "gates":
        title, extra = f"🤖 Gates: {state}", []
    else:
        title = f"🤖 Review: {'pass' if state == 'success' else 'fail'} ({tier} tier)"
        extra = ["--tier", tier, "--reviewed", sha]
    return subprocess.run([sys.executable, str(RECORD), "build", "--kind", kind, "--sha", sha, "--state", state,
                           "--title", title, *extra, "--line", "- Head commit: x"],
                          capture_output=True, text=True, check=True).stdout


def pr_answer(head: str, default_branch: str = "main") -> dict:
    return {"number": 12, "head": {"sha": head}, "base": {"ref": default_branch,
                                                         "repo": {"default_branch": default_branch}}}


def comment(body: str, assoc: str = "OWNER", edited: bool = False) -> dict:
    return {"body": body, "author_association": assoc, "edited": edited}


class Fx:
    def __init__(self, d: Path) -> None:
        self.d = d
        self.friction = d.parent / "friction.jsonl"
        (d / "pr.json").write_text(json.dumps(pr_answer(HEAD)))

    def comments(self, *cs: dict) -> None:
        out = []
        for i, c in enumerate(cs):
            at = f"2000-01-01T{i // 60:02d}:{i % 60:02d}:00Z"
            out.append({"id": 1000 + i, "body": c["body"], "author_association": c["author_association"],
                        "created_at": at, "updated_at": "2000-02-01T00:00:00Z" if c["edited"] else at,
                        "html_url": f"https://github.com/{REPO}/pull/12#issuecomment-{1000 + i}"})
        (self.d / "comments.json").write_text(json.dumps(out))

    def both(self, tier: str = "standard") -> None:
        self.comments(comment(record("gates")), comment(record("review", tier=tier)))

    def noted(self) -> list[dict]:
        return [json.loads(x) for x in self.friction.read_text().splitlines()] if self.friction.exists() else []

    def gets(self) -> list[str]:
        p = self.d / "calls.jsonl"
        return [json.loads(x)["endpoint"] for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def fx(tmp_path: Path) -> Fx:
    d = tmp_path / "fx"
    d.mkdir()
    return Fx(d)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    r = tmp_path / "clone"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feature"], cwd=r, check=True)
    subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=r, check=True)
    return r


def guard_env(fx: Fx, gh: bool = True, **env: str) -> dict[str, str]:
    bin_dir = fx.d.parent / "bin"
    bin_dir.mkdir(exist_ok=True)
    if gh and not (bin_dir / "gh").exists():
        STUB.chmod(0o755)
        (bin_dir / "gh").symlink_to(STUB)
    e = {k: v for k, v in os.environ.items() if k != "GH_REPO"}
    return {**e, **ID, "PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_DIR": str(fx.d),
            "LOADOUT_FRICTION_LOG": str(fx.friction), **env}


def run(fx: Fx, event: dict, cwd: Path, gh: bool = True, **env: str) -> str | None:
    event = {"hook_event_name": "PreToolUse", "cwd": str(cwd), **event}
    done = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True,
                          timeout=60, env=guard_env(fx, gh, **env))
    assert done.returncode == 0, done.stderr
    if not done.stdout.strip():
        return None
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def bash(fx: Fx, command: str, cwd: Path, **env: str) -> str | None:
    return run(fx, {"tool_name": "Bash", "tool_input": {"command": command}}, cwd, **env)


def mcp(fx: Fx, cwd: Path, **tool_input: object) -> str | None:
    data = {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, **tool_input}
    return run(fx, {"tool_name": "mcp__github__merge_pull_request", "tool_input": data}, cwd)


def test_hooks_json_registers_the_guard_for_bash_and_the_merge_tools() -> None:
    hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    [entry] = [m for m in hooks if any("merge-guard.py" in h["command"] for h in m["hooks"])]
    matcher = re.compile(entry["matcher"])
    for name in ("Bash", "mcp__github__merge_pull_request", "mcp__plugin_x_github__merge_pull_request",
                 "mcp__github__enable_pr_auto_merge"):
        assert matcher.search(name), name
    for name in ("Read", "mcp__github__get_commit", "BashOutput"):
        assert not matcher.search(name), name


def test_both_records_on_the_named_head_pass(fx: Fx, clone: Path) -> None:
    fx.both()
    assert mcp(fx, clone, expectedHeadSha=HEAD) is None
    assert f"repos/{REPO}/issues/12/comments?per_page=100&page=1" in fx.gets()


@pytest.mark.parametrize("missing", ["gates", "review"])
def test_each_missing_record_is_named_with_its_script(fx: Fx, clone: Path, missing: str) -> None:
    fx.comments(comment(record("review" if missing == "gates" else "gates")))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and f"no {missing} record" in reason
    assert ("gate_stamp.sh" if missing == "gates" else "verdict.sh") in reason


@pytest.mark.parametrize("assoc", ["CONTRIBUTOR", "NONE", "FIRST_TIME_CONTRIBUTOR"])
def test_a_marker_from_outside_the_repo_does_not_count(fx: Fx, clone: Path, assoc: str) -> None:
    fx.comments(comment(record("gates")), comment(record("review"), assoc=assoc))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "no review record" in reason and f"markers by {assoc} do not count" in reason


def test_a_newer_outside_marker_neither_counts_nor_blocks(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")), comment(record("review")),
                comment(record("review", state="failure"), assoc="NONE"))
    assert mcp(fx, clone, expectedHeadSha=HEAD) is None


def test_records_for_an_older_head_do_not_count(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates", sha=OLD)), comment(record("review", sha=OLD)))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and f"is for {OLD}, not the head {HEAD}" in reason


def test_the_newest_record_wins(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")), comment(record("review")), comment(record("review", state="failure")))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "says failure" in reason


@pytest.mark.parametrize("body, why", [
    (record("review").replace("state=success", "state=success state=success"), "malformed marker"),
    (record("review").replace(" tier=standard", " tier=standard extra=1"), "malformed marker"),
    (record("review").replace("<!--", "<!--x"), "no review record"),
    (record("review").replace("🤖 Review: pass", "🤖 Review: fail"), "disagrees"),
    (record("review").replace("(standard tier)", "(routine tier)"), "disagrees"),
    ("🤖 Review: pass (standard tier)\n\n" + record("review"), "no review record"),
    (record("review").replace(HEAD, HEAD[:39]), "malformed"),
])
def test_a_malformed_record_refuses(fx: Fx, clone: Path, body: str, why: str) -> None:
    fx.comments(comment(record("gates")), comment(body))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and why in reason, reason


def test_an_edited_record_refuses(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")), comment(record("review"), edited=True))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "was edited" in reason


def test_comments_are_paged_by_hand(fx: Fx, clone: Path) -> None:
    filler = [comment(f"note {i}") for i in range(150)]
    fx.comments(*filler, comment(record("gates")), comment(record("review")))
    assert mcp(fx, clone, expectedHeadSha=HEAD) is None
    assert f"repos/{REPO}/issues/12/comments?per_page=100&page=2" in fx.gets()


def test_a_merge_naming_an_older_head_refuses(fx: Fx, clone: Path) -> None:
    fx.both()
    reason = mcp(fx, clone, expectedHeadSha=OLD)
    assert reason and f"is now {HEAD}" in reason


def test_a_merge_naming_no_head_is_asked_to_name_it(fx: Fx, clone: Path) -> None:
    fx.both()
    reason = mcp(fx, clone)
    assert reason and f"expectedHeadSha: {HEAD}" in reason


@pytest.mark.parametrize("fail_on", ["pulls/12", "issues/12/comments"])
def test_unreadable_github_fails_closed(fx: Fx, clone: Path, fail_on: str) -> None:
    fx.both()
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": HEAD}}, clone, STUB_FAIL=fail_on)
    assert reason and "fails closed" in reason and "HTTP 502" in reason


def test_no_gh_at_all_fails_closed(fx: Fx, clone: Path) -> None:
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": HEAD}}, clone, gh=False)
    assert reason and "fails closed" in reason


def test_auto_merge_is_refused(fx: Fx, clone: Path) -> None:
    fx.both()
    reason = run(fx, {"tool_name": "mcp__github__enable_pr_auto_merge",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12}}, clone)
    assert reason and "auto-merge" in reason
    assert fx.gets() == []


# The tier check, in a local clone holding the head.


@pytest.fixture
def local(tmp_path: Path, fx: Fx) -> tuple[Path, str]:
    """A clone of the repo whose head changes a hook script (sensitive by the floor), with origin/main beside it."""
    r = tmp_path / "local"
    r.mkdir()
    env = {**os.environ, **ID}
    for args in (["init", "-q", "-b", "main"], ["remote", "add", "origin", f"https://github.com/{REPO}.git"]):
        subprocess.run(["git", *args], cwd=r, check=True, env=env)
    (r / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=r, check=True, env=env)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=r, check=True, env=env)
    subprocess.run(["git", "switch", "-q", "-c", "feature"], cwd=r, check=True, env=env)
    (r / "hooks").mkdir()
    (r / "hooks/x.sh").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "hook"], cwd=r, check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True,
                          check=True).stdout.strip()
    (fx.d / "pr.json").write_text(json.dumps(pr_answer(head)))
    return r, head


def test_a_review_below_the_paths_tier_refuses_in_a_local_clone(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="standard")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "make it sensitive" in reason
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="sensitive")))
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_without_a_local_clone_the_tier_check_is_skipped(fx: Fx, local: tuple[Path, str], clone: Path) -> None:
    _, head = local
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine")))
    assert mcp(fx, clone, expectedHeadSha=head) is None  # `clone` does not hold the head


def test_bad_input_passes_silently(fx: Fx) -> None:
    done = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""


# Check mode, for scripts that merge.


def check(fx: Fx, cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GUARD), *args], cwd=cwd, capture_output=True, text=True,
                          timeout=60, env=guard_env(fx, **env), stdin=subprocess.DEVNULL)


def test_check_mode_passes_and_prints_the_head(fx: Fx, clone: Path) -> None:
    fx.both()
    for arg in (f"{REPO}#12", "12"):
        done = check(fx, clone, "--check", arg)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == HEAD


def test_check_mode_refuses_with_the_reason(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")))
    done = check(fx, clone, "--check", f"{REPO}#12")
    assert done.returncode == 1 and "no review record" in done.stderr and done.stdout == ""
    done = check(fx, clone, "--check", f"{REPO}#12", STUB_FAIL="issues/12/comments")
    assert done.returncode == 1 and "fails closed" in done.stderr


def test_check_mode_usage(fx: Fx, clone: Path) -> None:
    assert check(fx, clone, "--check").returncode == 2
    assert check(fx, clone, "--check", "x#y").returncode == 2


def test_a_slow_github_runs_out_of_budget_and_refuses(fx: Fx, clone: Path) -> None:
    fx.comments(*[comment(f"note {i}") for i in range(250)], comment(record("gates")), comment(record("review")))
    start = time.monotonic()
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": HEAD}}, clone,
                 STUB_SLEEP="0.7", MERGE_GUARD_BUDGET_S="2")
    assert time.monotonic() - start < 6
    assert reason and "budget" in reason and "fails closed" in reason


@pytest.mark.parametrize("data", ["gh pr merge 12", ["x"], 7, None])
def test_a_malformed_tool_input_passes_an_ordinary_call(fx: Fx, clone: Path, data: object) -> None:
    assert run(fx, {"tool_name": "Bash", "tool_input": data}, clone) is None
    assert run(fx, {"tool_name": "Read", "tool_input": data}, clone) is None


def test_a_malformed_merge_tool_input_is_refused(fx: Fx, clone: Path) -> None:
    assert run(fx, {"tool_name": "mcp__github__merge_pull_request", "tool_input": "12"}, clone)
    assert run(fx, {"tool_name": "mcp__github__merge_pull_request",
                    "tool_input": {"owner": ["x"], "repo": 3, "pullNumber": True}}, clone)


def _slow_git(fx: Fx, seconds: float) -> None:
    git = fx.d.parent / "bin" / "git"
    git.parent.mkdir(exist_ok=True)
    git.write_text(f'#!/bin/sh\ncase " $* " in *" show "*) sleep {seconds} ;; esac\nexec /usr/bin/git "$@"\n')
    git.chmod(0o755)


def test_a_tier_check_that_cannot_finish_refuses(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine")))
    _slow_git(fx, 6)
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": head}}, r, MERGE_GUARD_BUDGET_S="3")
    assert reason and "fails closed" in reason and "tier.sh" in reason, reason


def test_a_tier_check_that_fails_refuses(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    # The default branch at the head itself: tier.sh finds no changed path and fails.
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", head], cwd=r, check=True)
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="sensitive")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "tier.sh failed" in reason, reason


def test_the_tier_check_compares_with_the_default_branch_github_names(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    # Neither main nor master, and no origin/HEAD: the base comes from the PR's repo.
    subprocess.run(["git", "update-ref", "refs/remotes/origin/trunk", "refs/remotes/origin/main"], cwd=r, check=True)
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=r, check=True)
    (fx.d / "pr.json").write_text(json.dumps(pr_answer(head, "trunk")))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="standard")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "make it sensitive" in reason, reason


def test_a_clone_without_the_default_branch_skips_the_tier_check(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=r, check=True)
    (fx.d / "pr.json").write_text(json.dumps(pr_answer(head, "develop")))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine")))
    assert mcp(fx, r, expectedHeadSha=head) is None


# The Bash rule: the command's text, never parsed as shell.


def guard_module() -> dict:
    return runpy.run_path(str(GUARD), run_name="merge_guard")


# Each rule with the commands that mention only it: removing a pattern, or its case-insensitivity, turns one red.
ONE_RULE = [
    ("pr-merge", "gh pr merge 12 --squash"),
    ("pr-merge", "GH PR MERGE 12"),
    ("pr-merge", "gh pr\tmerge 12"),
    ("merge-endpoint", f"gh api -X PUT repos/{REPO}/pulls/12/merge -f sha={HEAD}"),
    ("merge-endpoint", "curl -X PUT https://api.github.com/REPOS/o/r/PULLS/$PR/MERGE"),
    ("merge-mutation", "gh api graphql -f query='mutation{mergePullRequest(input:{}){clientMutationId}}'"),
    ("merge-mutation", "gh api graphql -f query='mutation{ENABLEPULLREQUESTAUTOMERGE(input:{}){x}}'"),
    ("no-verify", "git commit --no-verify -m x"),
    ("no-verify", "git push --NO-VERIFY origin feature"),
    ("hooks-path", "git -c core.hooksPath=/dev/null commit -m x"),
    ("hooks-path", "git --config-env=CORE.HOOKSPATH=EMPTY push"),
]


@pytest.mark.parametrize("rule, command", ONE_RULE)
def test_each_rule_refuses_the_commands_that_mention_it(fx: Fx, clone: Path, rule: str, command: str) -> None:
    hits = [r for r, _, pattern, _ in guard_module()["MENTIONS"] if pattern.search(command)]
    assert hits == [rule], (command, hits)
    reason = bash(fx, command, clone)
    assert reason and f"rule `{rule}`" in reason, (command, reason)
    assert fx.gets() == [], command


ORDINARY = [
    "git merge main",
    'git commit -m "merge branch feature"',
    "gh pr view 12",
    "gh pr list --state merged",
    f"gh api repos/{REPO}/pulls/5",
    f"gh api repos/{REPO}/pulls/5 | jq .mergeable",
    "git push origin feature",
    "git config core.hooksPath .githooks",
    'echo "the pr merged on time"',
    'echo "an expr merge step"',
    "ls -la",
]


@pytest.mark.parametrize("command", ORDINARY)
def test_ordinary_commands_pass_without_reading_github(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command
    assert fx.gets() == [] and fx.noted() == [], command


# The autopilot's merge script holds none of the words, so its calls pass; anything added that does is refused.
MERGE_SH_CALLS = [
    "bash /home/user/loadout/cloud/skills/autopilot/scripts/merge.sh 12",
    "$AP/scripts/merge.sh 12 --dry-run",
    "AUTOPILOT_HOLD_LABELS='hold-a hold-b' bash \"$AP/scripts/merge.sh\" 12",
]
MERGE_SH_SMUGGLED = [
    "bash $AP/scripts/merge.sh 5; gh pr merge 6",
    "bash $AP/scripts/merge.sh 5\ngh pr merge 6",
    "bash $AP/scripts/merge.sh $(gh pr merge 6)",
    f"bash $AP/scripts/merge.sh 5 && gh api -X PUT repos/{REPO}/pulls/6/merge",
]


@pytest.mark.parametrize("command", MERGE_SH_CALLS)
def test_the_merge_script_passes(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command


@pytest.mark.parametrize("command", MERGE_SH_SMUGGLED)
def test_a_merge_smuggled_beside_the_merge_script_is_refused(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone), command


def test_the_refusal_says_how_to_merge_and_how_to_write_the_words(fx: Fx, clone: Path) -> None:
    reason = bash(fx, "gh pr merge 12", clone)
    assert reason
    merge_sh = re.search(r"`(\S+/merge\.sh) <pr>`", reason)
    friction = re.search(r"`(\S+/bin/friction) note ", reason)
    assert merge_sh and Path(merge_sh.group(1)).is_file(), reason
    assert friction and Path(friction.group(1)).is_file(), reason
    for words in ("MCP merge tool", "`expectedHeadSha`", "Grep tool", "Write tool", "`git commit -F <file>`",
                  "-F body=@<file>", "--part merge-guard --workaround"):
        assert words in reason, words
    hooks = bash(fx, "git commit --no-verify -m x", clone)
    assert hooks and "fix what it names" in hooks and "MCP merge tool" not in hooks and "Grep tool" in hooks


N = 1_000_000
ADVERSARIAL = {
    "pr then spaces": "pr" + " " * N,
    "pr repeated": "pr " * (N // 3),
    "pulls with no slash after": "pulls/" + "a" * N,
    "pulls repeated": "pulls/" * (N // 6),
    "pulls and segments": "pulls/a" * (N // 7),
    "almost a mutation": "mergePullReques" * (N // 15),
    "almost no-verify": "--no-verif" * (N // 10),
    "hooksPath then spaces": "hooksPath" + " " * N,
    "hooksPath repeated": "hooksPath " * (N // 10),
}


@pytest.mark.parametrize("name", ADVERSARIAL)
def test_a_million_character_line_is_decided_well_under_a_second(name: str) -> None:
    text_rule = guard_module()["text_rule"]
    start = time.monotonic()
    assert text_rule(ADVERSARIAL[name]) == ("", "")
    assert time.monotonic() - start < 0.5, name


def test_a_million_character_command_through_the_hook(fx: Fx, clone: Path) -> None:
    start = time.monotonic()
    reason = bash(fx, "pr " * (N // 3) + "gh pr merge 12", clone)
    assert reason and "rule `pr-merge`" in reason
    assert bash(fx, "pulls/" * (N // 6), clone) is None
    assert time.monotonic() - start < 3


# Failures of the guard itself.


def broken_copy(tmp_path: Path, func: str) -> Path:
    """A copy of the guard whose `func` raises (and with no friction log script beside it)."""
    broken = tmp_path / "broken" / "cloud" / "hooks" / "merge-guard.py"
    broken.parent.mkdir(parents=True)
    src = GUARD.read_text()
    assert src.count(f"def {func}(") == 1
    broken.write_text(src.replace(f"def {func}(", f"def {func}(*a, **k):\n    raise RuntimeError('bug')\n\n\n"
                                                  f"def unused_{func}(", 1))
    return broken


def run_copy(fx: Fx, guard: Path, event: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(guard)], capture_output=True, text=True, env=guard_env(fx),
                          input=json.dumps(event), timeout=60, check=False)


def test_a_guard_failure_on_a_merge_tool_call_fails_closed(fx: Fx, clone: Path, tmp_path: Path) -> None:
    done = run_copy(fx, broken_copy(tmp_path, "check_merge"), {
        "tool_name": "mcp__github__merge_pull_request", "cwd": str(clone),
        "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, "expectedHeadSha": HEAD}})
    assert done.returncode == 0 and "fails closed" in done.stdout, done


def test_a_guard_failure_on_a_bash_command_passes_it(fx: Fx, clone: Path, tmp_path: Path) -> None:
    for command in ("gh pr merge 12", "ls -la"):
        done = run_copy(fx, broken_copy(tmp_path / command[:2], "text_rule"),
                        {"tool_name": "Bash", "cwd": str(clone), "tool_input": {"command": command}})
        assert done.returncode == 0 and done.stdout == "", done


# The friction log: each refusal noted by guard and rule, nothing of the command, and never in the way.


def test_a_bash_refusal_is_noted_without_the_command(fx: Fx, clone: Path) -> None:
    assert bash(fx, "gh pr merge 12 --body 'private-token-xyz in /srv/private/repo'", clone)
    assert fx.noted() and [set(e) for e in fx.noted()] == [{"at", "kind", "guard", "rule"}]
    assert [(e["kind"], e["guard"], e["rule"]) for e in fx.noted()] == [("refusal", "merge-guard", "pr-merge")]
    raw = fx.friction.read_text()
    assert "private" not in raw and "/srv" not in raw


@pytest.mark.parametrize("case, rule", [("records", "merge-records"), ("unreadable", "unreadable"),
                                        ("auto", "auto-merge")])
def test_a_merge_tool_refusal_is_noted_with_its_rule(fx: Fx, clone: Path, case: str, rule: str) -> None:
    fx.comments(comment(record("gates")))
    tool = "mcp__github__enable_pr_auto_merge" if case == "auto" else "mcp__github__merge_pull_request"
    env = {"STUB_FAIL": "pulls/12"} if case == "unreadable" else {}
    assert run(fx, {"tool_name": tool, "tool_input": {"owner": "example-owner", "repo": "example-repo",
                                                      "pullNumber": 12, "expectedHeadSha": HEAD}}, clone, **env)
    assert [e["rule"] for e in fx.noted()] == [rule]


def test_an_allowed_merge_notes_nothing(fx: Fx, clone: Path) -> None:
    fx.both()
    assert mcp(fx, clone, expectedHeadSha=HEAD) is None
    assert fx.noted() == []


def test_an_unwritable_friction_log_leaves_the_decision_alone(fx: Fx, clone: Path, tmp_path: Path) -> None:
    (tmp_path / "a-file").write_text("x")
    for log in (str(tmp_path / "a-file" / "friction.jsonl"), "/proc/version"):
        reason = run(fx, {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"}}, clone,
                     LOADOUT_FRICTION_LOG=log)
        assert reason and "rule `pr-merge`" in reason, log

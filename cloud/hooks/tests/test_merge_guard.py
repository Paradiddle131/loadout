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
import shutil
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


TIER_DEPTH = {"routine": "none", "standard": "light", "sensitive": "focused"}  # each tier's built-in floor


def record(kind: str, sha: str = HEAD, state: str = "success", tier: str = "standard",
           depth: str | None = "floor") -> str:
    """A record as verdict.sh posts it; a review's depth defaults to its tier's floor, and `depth=None` leaves it
    out, as on a record from before review depths."""
    depth = TIER_DEPTH[tier] if depth == "floor" else depth
    if kind == "gates":
        title, extra = f"🤖 Gates: {state}", []
    else:
        title = f"🤖 Review: {'pass' if state == 'success' else 'fail'} ({tier} tier)"
        extra = ["--tier", tier, "--reviewed", sha] + (["--depth", depth] if depth else [])
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

    def both(self, tier: str = "standard", sha: str = HEAD) -> None:
        self.comments(comment(record("gates", sha=sha)), comment(record("review", sha=sha, tier=tier)))

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
    e = {k: v for k, v in os.environ.items() if k not in ("GH_REPO", "LOADOUT_MAX_EFFORT")}
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


def test_both_records_on_the_named_head_pass(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    assert mcp(fx, clone, expectedHeadSha=head) is None
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


def test_a_newer_outside_marker_neither_counts_nor_blocks(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)),
                comment(record("review", sha=head, state="failure"), assoc="NONE"))
    assert mcp(fx, clone, expectedHeadSha=head) is None


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


def test_comments_are_paged_by_hand(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    filler = [comment(f"note {i}") for i in range(150)]
    fx.comments(*filler, comment(record("gates", sha=head)), comment(record("review", sha=head)))
    assert mcp(fx, clone, expectedHeadSha=head) is None
    assert f"repos/{REPO}/issues/12/comments?per_page=100&page=2" in fx.gets()


def test_a_merge_naming_an_older_head_refuses(fx: Fx, clone: Path) -> None:
    fx.both()
    reason = mcp(fx, clone, expectedHeadSha=OLD)
    assert reason and f"is now {HEAD}" in reason


def test_a_merge_naming_no_head_is_asked_to_name_it(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    reason = mcp(fx, clone)
    assert reason and f"expectedHeadSha: {head}" in reason


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
def held(tmp_path: Path, fx: Fx) -> tuple[Path, str]:
    """A clone that holds the PR's head (a standard change, floor light) and GitHub's tip of main: the guard can
    compute the floor, as it must before any merge."""
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    return r, head


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


@pytest.mark.parametrize("tier, depth", [("routine", None), ("sensitive", "full")])
def test_without_a_clone_holding_the_head_the_merge_is_refused(fx: Fx, local: tuple[Path, str], clone: Path,
                                                               tier: str, depth: str | None) -> None:
    _, head = local
    review = record("review", sha=head, tier=tier, depth=depth or "floor")
    fx.comments(comment(record("gates", sha=head)), comment(review))
    reason = mcp(fx, clone, expectedHeadSha=head)  # `clone` does not hold the head
    assert reason and "cannot be checked" in reason and "git fetch origin main" in reason, reason
    done = check(fx, clone, "--check", f"{REPO}#12")
    assert done.returncode == 1 and "cannot be checked" in done.stderr, done.stderr


def test_bad_input_passes_silently(fx: Fx) -> None:
    done = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""


# Check mode, for scripts that merge.


def check(fx: Fx, cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GUARD), *args], cwd=cwd, capture_output=True, text=True,
                          timeout=60, env=guard_env(fx, **env), stdin=subprocess.DEVNULL)


def test_check_mode_passes_and_prints_the_head(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    for arg in (f"{REPO}#12", "12"):
        done = check(fx, clone, "--check", arg)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == head


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


def test_a_tier_check_that_fails_on_githubs_tip_refuses(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    # GitHub names the head itself as the default branch's tip: the check finds no changed path and fails, whatever
    # the clone's origin/main says.
    (fx.d / "branches.json").write_text(json.dumps({"main": head}))
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


def test_a_clone_without_the_default_branch_refuses_the_merge(fx: Fx, local: tuple[Path, str]) -> None:
    r, head = local
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=r, check=True)
    (fx.d / "pr.json").write_text(json.dumps(pr_answer(head, "develop")))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "a copy of develop" in reason, reason


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
                  "-F body=@<file>", "note --file <file> --part merge-guard", "which may be public",
                  "no repo name, path, data or secret"):
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


def test_an_allowed_merge_notes_nothing(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    assert mcp(fx, clone, expectedHeadSha=head) is None
    assert fx.noted() == []


def test_an_unwritable_friction_log_leaves_the_decision_alone(fx: Fx, clone: Path, tmp_path: Path) -> None:
    (tmp_path / "a-file").write_text("x")
    for log in (str(tmp_path / "a-file" / "friction.jsonl"), "/proc/version"):
        reason = run(fx, {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"}}, clone,
                     LOADOUT_FRICTION_LOG=log)
        assert reason and "rule `pr-merge`" in reason, log


def test_a_pr_the_owner_merges_is_refused_whatever_its_records(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    (fx.d / "pr.json").write_text(json.dumps({**pr_answer(head), "labels": [{"name": "Owner-Merges"}]}))
    reason = mcp(fx, clone, expectedHeadSha=head)
    assert reason and "`owner-merges`" in reason and "the merge is the owner's" in reason, reason
    done = check(fx, clone, "--check", f"{REPO}#12")
    assert done.returncode == 1 and "`owner-merges`" in done.stderr and done.stdout == ""
    (fx.d / "pr.json").write_text(json.dumps({**pr_answer(head), "labels": [{"name": "other"}]}))
    assert mcp(fx, clone, expectedHeadSha=head) is None


def nested(tool: str, command: str) -> str:
    deep = "[" * 100_000 + "]" * 100_000
    return json.dumps({"tool_name": tool, "tool_input": {"command": command, "owner": "example-owner",
                                                         "repo": "example-repo", "pullNumber": 12}})[:-1] \
        + f', "x": {deep}}}'


@pytest.mark.parametrize("tool, refused", [("Bash", False), ("mcp__github__merge_pull_request", True),
                                           ("mcp__github__enable_pr_auto_merge", True)])
def test_input_nested_too_deep_fails_closed_for_a_merge_and_passes_a_command(
        fx: Fx, clone: Path, tool: str, refused: bool) -> None:
    done = subprocess.run([sys.executable, str(GUARD)], input=nested(tool, "ls"), capture_output=True, text=True,
                          timeout=60, env=guard_env(fx))
    assert done.returncode == 0 and done.stderr == "", done.stderr[-300:]
    assert bool(done.stdout.strip()) is refused
    if refused:
        assert "fails closed" in done.stdout and [e["rule"] for e in fx.noted()] == ["guard-error"]


def test_check_mode_fails_closed_on_a_guard_error(fx: Fx, clone: Path, tmp_path: Path) -> None:
    fx.both()
    done = subprocess.run([sys.executable, str(broken_copy(tmp_path, "check_merge")), "--check", f"{REPO}#12"],
                          cwd=clone, capture_output=True, text=True, timeout=60, env=guard_env(fx),
                          stdin=subprocess.DEVNULL)
    assert done.returncode == 1 and "the merge guard failed" in done.stderr and "fails closed" in done.stderr
    assert done.stdout == ""


@pytest.mark.parametrize("tool, refused", [("Bash", False), ("mcp__github__merge_pull_request", True)])
def test_input_json_cannot_read_fails_closed_for_a_merge(fx: Fx, clone: Path, tool: str, refused: bool) -> None:
    event = json.dumps({"tool_name": tool, "tool_input": {"command": "ls", "owner": "example-owner",
                                                          "repo": "example-repo", "pullNumber": 12}})
    event = event.replace('"pullNumber": 12', '"pullNumber": 1' + "0" * 5000)  # past the parser's digit limit
    done = subprocess.run([sys.executable, str(GUARD)], input=event, capture_output=True, text=True,
                          timeout=60, env=guard_env(fx))
    assert done.returncode == 0 and done.stderr == "", done.stderr[-300:]
    assert bool(done.stdout.strip()) is refused


# The round line (a record's third line) is for audits: the guard never reads it.


def round_line_of(body: str) -> str:
    return body.split("\n")[2]


def test_the_record_builder_writes_a_round_line_on_line_three() -> None:
    assert round_line_of(record("review")).startswith("<!-- loadout" + ":round v=")
    assert round_line_of(record("gates")).startswith("<!-- loadout" + ":round v=")


def test_both_records_with_their_round_lines_merge(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.both(sha=head)
    assert mcp(fx, clone, expectedHeadSha=head) is None


def without_round(body: str) -> str:
    lines = body.split("\n")
    return "\n".join(lines[:2] + lines[3:])


def test_records_posted_before_the_round_line_still_merge(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    gates, review = without_round(record("gates", sha=head)), without_round(record("review", sha=head))
    assert all("round" not in b for b in (gates, review))
    fx.comments(comment(gates), comment(review))
    assert mcp(fx, clone, expectedHeadSha=head) is None


@pytest.mark.parametrize("garbage", [
    "<!-- loadout" + ":round v=??? kit= lens=a:b -->",
    "<!-- loadout" + f":review sha={OLD} state=failure tier=routine reviewed={OLD} -->",
    "not a marker at all",
    "",
])
def test_a_garbage_round_line_changes_nothing_on_a_good_line_two(fx: Fx, held: tuple[Path, str], garbage: str) -> None:
    clone, head = held
    def spoil(body: str) -> str:
        lines = body.split("\n")
        return "\n".join(lines[:2] + [garbage] + lines[3:])

    fx.comments(comment(spoil(record("gates", sha=head))), comment(spoil(record("review", sha=head))))
    assert mcp(fx, clone, expectedHeadSha=head) is None
    fx.comments(comment(spoil(record("gates", sha=head))), comment(spoil(record("review", sha=head, state="failure"))))
    reason = mcp(fx, clone, expectedHeadSha=head)
    assert reason and "says failure" in reason  # line two still decides


# The depth floor (skills/review/scripts/plan.py): the guard recomputes it for the head in a local clone and requires
# no more. A change whose floor is `none` merges on its gates record alone; a review record without `depth` never
# counts.


def git_in(r: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=r, capture_output=True, text=True, check=True,
                          env={**os.environ, **ID}).stdout.strip()


def change(tmp_path: Path, fx: Fx, *commits: dict[str, str], base: dict[str, str] | None = None,
           pin: bool = True) -> tuple[Path, str, str]:
    """A local clone whose origin/main holds `base` and whose head adds `commits` one by one; GitHub names that head,
    and (with `pin`) origin/main's commit as the default branch's tip. Returns the clone, the head and the tip."""
    r = tmp_path / "change"
    r.mkdir()
    git_in(r, "init", "-q", "-b", "main")
    git_in(r, "remote", "add", "origin", f"https://github.com/{REPO}.git")
    for name, text in {"README.md": "x\n", "src/app.py": "x = 1\n", **(base or {})}.items():
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text(text)
    git_in(r, "add", ".")
    git_in(r, "commit", "-qm", "seed")
    tip = git_in(r, "rev-parse", "HEAD")
    git_in(r, "update-ref", "refs/remotes/origin/main", tip)
    git_in(r, "switch", "-q", "-c", "feature")
    for files in commits:
        for name, text in files.items():
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            (r / name).write_text(text)
        git_in(r, "add", ".")
        git_in(r, "commit", "-qm", "change")
    head = git_in(r, "rev-parse", "HEAD")
    (fx.d / "pr.json").write_text(json.dumps(pr_answer(head)))
    if pin:
        (fx.d / "branches.json").write_text(json.dumps({"main": tip}))
    return r, head, tip


def test_a_floor_none_change_merges_on_gates_alone(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)))
    assert mcp(fx, r, expectedHeadSha=head) is None
    done = check(fx, r, "--check", f"{REPO}#12")
    assert done.returncode == 0 and done.stdout.strip() == head, done.stderr


def test_a_lab_policy_lets_a_standard_change_merge_on_gates_alone(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"}, base={"REVIEW.md": "# Review\n\nDepth: none\n"})
    fx.comments(comment(record("gates", sha=head)))
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_a_routine_record_on_a_floor_none_standard_change_does_not_block_it(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"}, base={"REVIEW.md": "Depth: none\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine",
                                                                   depth="none")))
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_a_floor_none_change_is_still_refused_by_a_failed_review_on_its_head(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, state="failure",
                                                                   tier="standard", depth="light")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "says failure" in reason, reason


def test_a_floor_none_change_still_needs_its_gates(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments()
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "no gates record" in reason


def test_without_a_clone_holding_the_head_a_review_is_still_required(fx: Fx, tmp_path: Path, clone: Path) -> None:
    _, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)))
    reason = mcp(fx, clone, expectedHeadSha=head)
    assert reason and "no review record" in reason


def test_without_githubs_tip_of_the_default_branch_a_review_is_still_required(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"}, pin=False)
    fx.comments(comment(record("gates", sha=head)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "no review record" in reason


def test_a_locally_moved_default_branch_does_not_drop_the_review(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"}, {"docs/guide.md": "x\n"})
    git_in(r, "update-ref", "refs/remotes/origin/main", "HEAD~1")  # the hook commit, so the diff is docs only
    fx.comments(comment(record("gates", sha=head)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "no review record" in reason, reason


@pytest.mark.parametrize("depth", ["none", "light"])
def test_a_record_below_the_floor_refuses(fx: Fx, tmp_path: Path, depth: str) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="sensitive",
                                                                   depth=depth)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and f"depth {depth}" in reason and "focused" in reason, reason


@pytest.mark.parametrize("depth", ["focused", "full"])
def test_a_record_at_or_above_the_floor_merges(fx: Fx, tmp_path: Path, depth: str) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="sensitive",
                                                                   depth=depth)))
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_a_record_s_depth_is_checked_against_a_lab_policy_too(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"},
                        base={"REVIEW.md": "## Paths\n- `src/**`; depth: full\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, depth="light")))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "full" in reason, reason


# The owner's effort cap: a review record's cap= counts only at or above this session's LOADOUT_MAX_EFFORT.


def capped(head: str, cap: str) -> str:
    return record("review", sha=head).replace(" -->", f" cap={cap} -->", 1)


def merge_under(fx: Fx, cwd: Path, head: str, cap: str | None) -> str | None:
    data = {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, "expectedHeadSha": head}
    return run(fx, {"tool_name": "mcp__github__merge_pull_request", "tool_input": data}, cwd,
               **({"LOADOUT_MAX_EFFORT": cap} if cap is not None else {}))


@pytest.mark.parametrize("record_cap, session_cap", [("medium", "medium"), ("high", "medium"), ("max", "low")])
def test_a_capped_review_merges_at_or_above_the_session_s_cap(fx: Fx, tmp_path: Path, record_cap: str,
                                                              session_cap: str) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(capped(head, record_cap)))
    assert merge_under(fx, r, head, session_cap) is None


@pytest.mark.parametrize("record_cap, session_cap, why", [
    ("low", "medium", "below this session's LOADOUT_MAX_EFFORT=medium"),  # a lead's own lower cap
    ("low", None, "sets no LOADOUT_MAX_EFFORT"),  # a cap the owner never set
    ("low", "", "sets no LOADOUT_MAX_EFFORT"),
    ("medium", "huge", "not a level"),
    ("Low", "medium", "malformed"),
    ("", "medium", "malformed"),
])
def test_a_review_under_a_lower_or_unset_cap_refuses(fx: Fx, tmp_path: Path, record_cap: str,
                                                     session_cap: str | None, why: str) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(capped(head, record_cap)))
    reason = merge_under(fx, r, head, session_cap)
    assert reason and why in reason, reason


def test_a_review_with_no_cap_merges_as_before_under_any_session_cap(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    for cap in (None, "low", "max"):
        assert merge_under(fx, r, head, cap) is None, cap


def test_a_capped_review_holds_a_floor_none_merge_too(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/x.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(capped(head, "low")))
    assert "sets no LOADOUT_MAX_EFFORT" in merge_under(fx, r, head, None)


# The owner's override (verdict.sh --owner): a record whose override= names its own depth passes below the floor.


QUOTED = '- Owner override: depth light, by the owner\'s words: "light is enough here"\n'


def carried(n: int, depth: str = "light") -> str:
    """The line a repost writes, linking the n-th comment the fixture posts (Fx.comments numbers them from 1000)."""
    return (f"- Owner override: depth {depth}, carried from the reposted round's record "
            f"(https://github.com/{REPO}/pull/12#issuecomment-{1000 + n}), which quotes the owner\n")


def overridden(head: str, quote: str) -> str:
    return record("review", sha=head, tier="sensitive", depth="light").replace(
        " depth=light -->", " depth=light override=light -->", 1) + quote


def test_an_owner_override_naming_the_record_s_depth_merges_below_the_floor(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(overridden(head, QUOTED)))
    assert mcp(fx, r, expectedHeadSha=head) is None


@pytest.mark.parametrize("chain", [
    [QUOTED, carried(1)],  # a repost of the record that quotes the owner
    [QUOTED, carried(1), carried(2)],  # a repost of a repost
])
def test_a_repost_s_override_counts_when_its_link_leads_to_the_owner_s_words(fx: Fx, tmp_path: Path,
                                                                            chain: list[str]) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    fx.comments(comment(record("gates", sha=head)), *[comment(overridden(head, q)) for q in chain])
    assert mcp(fx, r, expectedHeadSha=head) is None


@pytest.mark.parametrize("chain, spoil", [
    (["- Owner override: depth light, carried from the reposted round's record, which quotes the owner\n"], None),
    ([carried(9)], None),  # a link to no comment of the PR
    (["", carried(1)], None),  # a repost of a record that quotes nobody: the laundering path
    ([carried(2), carried(1)], None),  # a loop
    ([QUOTED.replace("light", "focused", 1), carried(1)], None),  # the linked record quotes another depth
    ([QUOTED, carried(1)], "edited"),  # the linked record was edited after it was posted
    ([QUOTED, carried(1)], "outsider"),  # the linked record is not by the owner, a member or a collaborator
    ([QUOTED, carried(1)], "no-override"),  # the linked record's marker carries no override
    ([QUOTED, carried(9)], None),  # words on another record, but the link names none of the PR's comments
    ([QUOTED, carried(1).replace("depth light", "depth focused")], None),  # the carried line names another depth
    ([QUOTED, carried(1).replace(", which quotes the owner", ", which quotes the owner, honest")], None),  # extra text
    ([QUOTED, carried(1).replace("carried from the reposted round's record", "carried from somewhere")], None),
    ([QUOTED, carried(1)], "gates"),  # the linked comment is a gates record, not a review record
])
def test_a_repost_s_override_without_a_path_to_the_owner_s_words_refuses(fx: Fx, tmp_path: Path, chain: list[str],
                                                                       spoil: str | None) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    bodies = [overridden(head, q) for q in chain]
    if spoil == "no-override":
        bodies[0] = bodies[0].replace(" override=light", "", 1)
    if spoil == "gates":
        bodies[0] = record("gates", sha=head).replace(" -->", " override=light -->", 1) + chain[0]
    first = comment(bodies[0], assoc="NONE" if spoil == "outsider" else "OWNER", edited=spoil == "edited")
    fx.comments(comment(record("gates", sha=head)), first, *[comment(b) for b in bodies[1:]])
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "quoting the owner's words" in reason, reason


@pytest.mark.parametrize("quote", ["", '- Owner override: depth light, by the owner\'s words: ""\n',
                                   QUOTED.replace("depth light", "depth focused"), "x " + QUOTED])
def test_an_owner_override_without_the_owner_s_quote_refuses(fx: Fx, tmp_path: Path, quote: str) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    body = record("review", sha=head, tier="sensitive", depth="light").replace(" depth=light -->",
                                                                                " depth=light override=light -->", 1)
    fx.comments(comment(record("gates", sha=head)), comment(body + quote))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "quoting the owner's words" in reason, reason


@pytest.mark.parametrize("marker", [" depth=light override=focused -->", " depth=light override=none -->",
                                    " depth=light override= -->", " depth=light override=light override=light -->"])
def test_an_override_that_does_not_name_the_record_s_depth_refuses(fx: Fx, tmp_path: Path, marker: str) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    body = record("review", sha=head, tier="sensitive", depth="light").replace(" depth=light -->", marker, 1)
    fx.comments(comment(record("gates", sha=head)), comment(body))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and ("malformed" in reason or "depth light" in reason), reason


@pytest.mark.parametrize("files, tier, marker", [
    ({"hooks/x.sh": "x\n"}, "sensitive", " depth=none override=none -->"),  # an override never skips review
    ({"src/app.py": "x = 2\n"}, "standard", " depth=focused override=light -->"),  # above the floor, yet malformed
])
def test_an_override_marker_out_of_shape_refuses_even_where_the_floor_would_not(fx: Fx, tmp_path: Path,
                                                                                 files: dict[str, str], tier: str,
                                                                                 marker: str) -> None:
    r, head, _ = change(tmp_path, fx, files)
    body = record("review", sha=head, tier=tier, depth=None).replace(" -->", marker, 1)
    fx.comments(comment(record("gates", sha=head)), comment(body))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "malformed" in reason, reason


def test_an_override_never_lowers_the_tier(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    body = record("review", sha=head, tier="standard", depth="light").replace(" depth=light -->",
                                                                               " depth=light override=light -->", 1)
    fx.comments(comment(record("gates", sha=head)), comment(body))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "tier" in reason, reason


@pytest.mark.parametrize("body", [
    record("review", depth=None).replace(" -->", " depth=deep -->", 1),
    record("review", depth=None).replace(" -->", " depth= -->", 1),
    record("review", depth=None).replace(" -->", " depth=light depth=full -->", 1),
])
def test_a_malformed_depth_refuses(fx: Fx, clone: Path, body: str) -> None:
    fx.comments(comment(record("gates")), comment(body))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "malformed" in reason, reason


def test_a_well_formed_depth_is_accepted(fx: Fx, held: tuple[Path, str]) -> None:
    clone, head = held
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, depth=None).replace(" -->", " depth=light -->", 1)))
    assert mcp(fx, clone, expectedHeadSha=head) is None


# A review record without depth (two lines, or with the round line, as posted before review depths) never counts,
# whatever its tier, with a clone or without one.


@pytest.mark.parametrize("shape", ["two-line", "round-line"])
@pytest.mark.parametrize("files, tier", [
    ({"src/app.py": "x = 2\n"}, "standard"),
    ({"src/app.py": "x = 2\n"}, "sensitive"),
    ({"hooks/x.sh": "x\n"}, "sensitive"),
])
def test_a_record_without_depth_refuses(fx: Fx, tmp_path: Path, shape: str, files: dict[str, str],
                                        tier: str) -> None:
    r, head, _ = change(tmp_path, fx, files)
    gates, review = record("gates", sha=head), record("review", sha=head, tier=tier, depth=None)
    if shape == "two-line":
        gates, review = without_round(gates), without_round(review)
    fx.comments(comment(gates), comment(review))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "carries no depth" in reason, reason
    done = check(fx, r, "--check", f"{REPO}#12")
    assert done.returncode == 1 and "carries no depth" in done.stderr, done.stderr


def test_a_record_without_depth_refuses_without_a_clone(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")), comment(record("review", depth=None)))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "carries no depth" in reason, reason


def test_on_gates_alone_a_record_without_depth_holds_the_merge(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine", depth=None)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "carries no depth" in reason and "holds the merge" in reason, reason


def test_a_record_without_depth_for_an_older_head_still_reads_as_older(fx: Fx, clone: Path) -> None:
    fx.comments(comment(record("gates")), comment(record("review", sha=OLD, depth=None)))
    reason = mcp(fx, clone, expectedHeadSha=HEAD)
    assert reason and "older head" in reason and "carries no depth" not in reason, reason


# On the gates-alone path the newest trusted review record still holds the merge unless it is an unedited, well-formed
# success or a record for an older head: every way a record fails to count elsewhere holds it here too.


def spoiled(state: str, how: str, head: str) -> dict:
    body = record("review", sha=head, tier="standard", state=state, depth="light")
    if how == "edited":
        return comment(body, edited=True)
    if how == "malformed marker":
        return comment(body.replace(" -->", " bogus=1 -->", 1))
    if how == "malformed first line":
        return comment(body.replace("🤖 Review:", "🤖 Reveiw:", 1))
    return comment(body.replace("(standard tier)", "(sensitive tier)", 1))  # title and marker disagree


@pytest.mark.parametrize("state", ["success", "failure"])
@pytest.mark.parametrize("how", ["edited", "malformed marker", "malformed first line", "disagreeing"])
def test_on_gates_alone_a_review_record_that_does_not_count_holds_the_merge(fx: Fx, tmp_path: Path, state: str,
                                                                           how: str) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)), spoiled(state, how, head))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "holds the merge" in reason, reason
    assert check(fx, r, "--check", f"{REPO}#12").returncode == 1


@pytest.mark.parametrize("review", ["absent", "older head", "success"])
def test_on_gates_alone_only_an_absent_older_or_counting_success_lets_gates_merge(fx: Fx, tmp_path: Path,
                                                                                  review: str) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    cs = [comment(record("gates", sha=head))]
    if review == "older head":
        cs.append(comment(record("review", sha=OLD, tier="standard", state="failure", depth="light")))
    elif review == "success":
        cs.append(comment(record("review", sha=head, tier="routine", depth="none")))
    fx.comments(*cs)
    assert mcp(fx, r, expectedHeadSha=head) is None


@pytest.mark.parametrize("review", [None, "routine"])
def test_without_githubs_tip_a_floor_none_change_is_told_to_fetch_it(fx: Fx, tmp_path: Path,
                                                                    review: str | None) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"}, base={"REVIEW.md": "Depth: none\n"}, pin=False)
    cs = [comment(record("gates", sha=head))]
    if review:
        cs.append(comment(record("review", sha=head, tier="routine", depth="none")))
    fx.comments(*cs)
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "git fetch origin main" in reason and "review it at that tier" not in reason, reason
    assert "--tier routine" not in reason  # a standard change's routine record is refused here: never advise one


def test_without_githubs_tip_a_routine_change_may_also_record_a_routine_verdict(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"}, pin=False)
    fx.comments(comment(record("gates", sha=head)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "git fetch origin main" in reason and "--tier routine" in reason, reason
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine", depth="none")))
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_a_floor_check_that_exits_non_zero_refuses_whatever_it_printed(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    guard = tmp_path / "copy" / "cloud" / "hooks" / "merge-guard.py"
    guard.parent.mkdir(parents=True)
    guard.write_text(GUARD.read_text())
    fake = tmp_path / "copy" / "skills" / "review" / "scripts" / "plan.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("import sys\nprint('routine none')\nsys.exit(1)\n")  # an answer that would waive the review
    fx.comments(comment(record("gates", sha=head)))
    done = run_copy(fx, guard, {"tool_name": "mcp__github__merge_pull_request", "cwd": str(r),
                                "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                               "expectedHeadSha": head}})
    assert done.returncode == 0 and "tier.sh failed" in done.stdout, done.stdout + done.stderr


def test_a_session_above_its_clones_finds_the_repo_s_clone_by_name(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    clones = tmp_path / "clones"
    clones.mkdir()
    r.rename(clones / REPO.split("/")[1])  # where a cloud session keeps the clone of this repo
    copy = tmp_path / "copy"
    shutil.copytree(GUARD.parents[2] / "skills" / "review" / "scripts", copy / "skills" / "review" / "scripts")
    guard = copy / "cloud" / "hooks" / "merge-guard.py"
    guard.parent.mkdir(parents=True)
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    event = {"tool_name": "mcp__github__merge_pull_request", "cwd": str(tmp_path),  # above the clones
             "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                            "expectedHeadSha": head}}
    for where, refused in ((clones, False), (tmp_path / "elsewhere", True)):
        guard.write_text(GUARD.read_text().replace('CLONES = Path("/home/user")', f"CLONES = Path({str(where)!r})", 1))
        done = run_copy(fx, guard, event)
        assert done.returncode == 0 and ("cannot be checked" in done.stdout) == refused, done.stdout + done.stderr



def test_a_floor_none_head_merges_past_a_repost_whose_link_leads_to_the_owner_s_words(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    fx.comments(comment(record("gates", sha=head)), *[comment(overridden(head, q)) for q in [QUOTED, carried(1)]])
    assert mcp(fx, r, expectedHeadSha=head) is None


def test_a_dense_web_of_reposts_is_read_in_linear_time(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    links = "".join(carried(j) for j in range(1, 31))  # 30 records, each linking all 30, none quoting the owner
    fx.comments(comment(record("gates", sha=head)), *[comment(overridden(head, links)) for _ in range(30)])
    started = time.monotonic()
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "quoting the owner's words" in reason and time.monotonic() - started < 15, reason


def test_a_merge_naming_the_repo_in_another_case_reads_the_same_clone(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    assert mcp(fx, r, owner="Example-Owner", repo="Example-Repo", expectedHeadSha=head) is None


def test_a_clone_of_another_repo_is_never_read(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    git_in(r, "remote", "set-url", "origin", "https://github.com/other-owner/example-repo.git")
    reason = mcp(fx, r, expectedHeadSha=head)  # it holds the head, but it is not this repo's clone
    assert reason and "cannot be checked" in reason, reason


def test_an_origin_in_another_case_reads_the_same_clone(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    git_in(r, "remote", "set-url", "origin", "https://github.com/Example-Owner/Example-Repo.git")
    assert mcp(fx, r, expectedHeadSha=head) is None


@pytest.mark.parametrize("folder, named", [("Example-Repo", "example-repo"), ("example-repo", "Example-Repo")])
def test_a_session_above_its_clones_finds_the_clone_by_name_in_any_case(fx: Fx, tmp_path: Path, folder: str,
                                                                       named: str) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    clones = tmp_path / "clones"
    clones.mkdir()
    r.rename(clones / folder)
    copy = tmp_path / "copy"
    shutil.copytree(GUARD.parents[2] / "skills" / "review" / "scripts", copy / "skills" / "review" / "scripts")
    guard = copy / "cloud" / "hooks" / "merge-guard.py"
    guard.parent.mkdir(parents=True)
    guard.write_text(GUARD.read_text().replace('CLONES = Path("/home/user")', f"CLONES = Path({str(clones)!r})", 1))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    event = {"tool_name": "mcp__github__merge_pull_request", "cwd": str(tmp_path),  # above the clones
             "tool_input": {"owner": "example-owner", "repo": named, "pullNumber": 12, "expectedHeadSha": head}}
    done = run_copy(fx, guard, event)
    assert done.returncode == 0 and done.stdout.strip() == "", done.stdout + done.stderr


def test_owner_words_in_a_record_s_first_three_lines_do_not_count(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    lines = overridden(head, "").split("\n")
    lines[2] = QUOTED.strip()  # on the round line, which only the record's builder writes
    fx.comments(comment(record("gates", sha=head)), comment("\n".join(lines)))
    reason = mcp(fx, r, expectedHeadSha=head)
    assert reason and "quoting the owner's words" in reason, reason


def guard_with_clones(tmp_path: Path, clones: Path) -> Path:
    """A copy of the guard whose CLONES is `clones`, beside the review scripts it runs."""
    copy = tmp_path / "copy"
    if not copy.exists():
        shutil.copytree(GUARD.parents[2] / "skills" / "review" / "scripts", copy / "skills" / "review" / "scripts")
    guard = copy / "cloud" / "hooks" / "merge-guard.py"
    guard.parent.mkdir(parents=True, exist_ok=True)
    text = GUARD.read_text()
    assert 'CLONES = Path("/home/user")' in text
    guard.write_text(text.replace('CLONES = Path("/home/user")', f"CLONES = Path({str(clones)!r})", 1))
    return guard


def test_the_session_s_own_clone_rating_is_kept_over_a_same_named_folder(fx: Fx, tmp_path: Path) -> None:
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    clones = tmp_path / "clones"
    clones.mkdir()
    shutil.copytree(r, clones / "example-repo")  # a folder of the repo's name that holds another repo's clone
    git_in(clones / "example-repo", "remote", "set-url", "origin", "https://github.com/other-owner/example-repo.git")
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    event = {"tool_name": "mcp__github__merge_pull_request", "cwd": str(r),
             "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, "expectedHeadSha": head}}
    done = run_copy(fx, guard_with_clones(tmp_path, clones), event)
    assert done.returncode == 0 and done.stdout.strip() == "", done.stdout + done.stderr


def test_the_exactly_spelled_clone_folder_is_rated_first(fx: Fx, tmp_path: Path) -> None:
    # Two clones of the repo hold the head, against their own copies of main (GitHub's tip is not pinned): the exact
    # spelling's rates the change sensitive (it touches a hook), the other's finds nothing changed and fails to rate.
    # The refusal names the sensitive tier only when the exact spelling is read first; read the other way, the guard
    # refuses for another cause. This pins the order, not a safety property.
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"}, pin=False)
    clones = tmp_path / "clones"
    clones.mkdir()
    shutil.copytree(r, clones / "Example-Repo")
    r.rename(clones / "example-repo")
    git_in(clones / "Example-Repo", "update-ref", "refs/remotes/origin/main", head)
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="standard")))
    event = {"tool_name": "mcp__github__merge_pull_request", "cwd": str(tmp_path),  # above the clones
             "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12, "expectedHeadSha": head}}
    done = run_copy(fx, guard_with_clones(tmp_path, clones), event)
    assert done.returncode == 0 and "make it sensitive" in done.stdout, done.stdout + done.stderr

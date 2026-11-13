"""The merge guard (cloud/hooks/merge-guard.py) against a stub `gh` (skills/review/scripts/tests/stub_gh.py).

Records are built with the review skill's own builder (skills/review/scripts/record.py), so the format the
scripts post and the format the guard reads cannot drift apart unnoticed.
Run: uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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
        (d / "pr.json").write_text(json.dumps(pr_answer(HEAD)))
        (d / "pulls.json").write_text(json.dumps([{"number": 12}]))

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
    return {**e, **ID, "PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_DIR": str(fx.d), **env}


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
    assert run(fx, {"tool_name": "mcp__github__enable_pr_auto_merge",
                    "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12}}, clone)
    assert bash(fx, f"gh pr merge 12 --auto --match-head-commit {HEAD}", clone)


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


# Shell merges.

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
def test_each_shell_merge_is_checked(fx: Fx, clone: Path, command: str) -> None:
    command = command.replace("{clone}", str(clone)).replace("{{", "{").replace("}}", "}")
    fx.comments(comment(record("gates")))
    reason = bash(fx, command, clone)
    assert reason and "no review record" in reason, command
    assert f"repos/{REPO}/pulls/12" in fx.gets(), command


def test_a_shell_merge_with_both_records_naming_the_head_passes(fx: Fx, clone: Path) -> None:
    fx.both()
    assert bash(fx, f"gh pr merge 12 --squash --match-head-commit {HEAD}", clone) is None
    assert bash(fx, f"gh api -X PUT repos/{REPO}/pulls/12/merge -f sha={HEAD}", clone) is None
    assert bash(fx, "gh pr merge 12 --squash", clone)  # names no head


def test_a_merge_outside_rest_is_refused(fx: Fx, clone: Path) -> None:
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
def test_other_commands_pass_without_reading_github(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command
    assert fx.gets() == [], command


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
def test_no_verify_is_refused(fx: Fx, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "fix what it names" in reason, command


def test_a_guard_failure_on_a_merge_fails_closed_and_passes_other_calls(fx: Fx, clone: Path,
                                                                       tmp_path: Path) -> None:
    # A copy of the guard whose command reading is broken: a bug must neither wave a merge through nor block.
    broken = tmp_path / "broken" / "merge-guard.py"
    broken.parent.mkdir()
    src = GUARD.read_text()
    assert src.count("def command_of(words: list[str])") == 1
    broken.write_text(src.replace("def command_of(words: list[str])",
                                  "def command_of(words: list[str]) -> None:\n    raise RuntimeError('bug')\n\n\n"
                                  "def unused(words: list[str])"))
    for command, refused in (("gh pr merge 12", True), ("ls -la", False)):
        done = subprocess.run([sys.executable, str(broken)], capture_output=True, text=True, env=guard_env(fx),
                              input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                                                "cwd": str(clone)}), check=True)
        assert bool(done.stdout.strip()) is refused, command
        if refused:
            assert "fails closed" in done.stdout
    assert fx.gets() == []


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


# Forms a fresh review found the guard let through, each now checked.

HIDDEN_MERGES = [
    "if gh pr checks 12; then gh pr merge 12 --squash; fi",
    "for p in 12; do gh pr merge 12; done",
    "while true; do gh pr merge 12; break; done",
    "gh pr checks 12 && { gh pr merge 12; }",
    "! gh pr merge 12",
    "( gh pr merge 12 )",
    "bash -lc 'gh pr merge 12'",
    "bash -ec 'gh pr merge 12'",
    "bash -c -- 'gh pr merge 12'",
    "sh -xc 'gh pr merge 12'",
    f"gh -R {REPO} pr merge 12",
    f"gh --repo {REPO} pr merge 12",
    f"gh --repo={REPO} pr merge 12",
    f"gh pr -R {REPO} merge 12",
    f"gh -R{REPO} pr merge 12",
    f"gh api -XPUT repos/{REPO}/pulls/12/merge",
    f"gh api --method=PUT repos/{REPO}/pulls/12/merge",
]


@pytest.mark.parametrize("command", HIDDEN_MERGES)
def test_merges_behind_keywords_flags_and_attached_values_are_checked(fx: Fx, clone: Path,
                                                                      command: str) -> None:
    fx.comments(comment(record("gates")))
    reason = bash(fx, command, clone)
    assert reason and "no review record" in reason, command


def test_a_repo_flag_before_the_subcommand_names_the_repo(fx: Fx, tmp_path: Path) -> None:
    nowhere = tmp_path / "nowhere"  # no clone here: the repo can only come from the flag
    nowhere.mkdir()
    fx.comments(comment(record("gates")))
    reason = bash(fx, f"gh -R {REPO} pr merge 12", nowhere)
    assert reason and f"PR 12 of {REPO}" in reason


@pytest.mark.parametrize("command", [
    f"gh -R {REPO} pr merge 12 --auto",
    f"gh --repo={REPO} pr merge --auto 12",
    "if true; then gh pr merge 12 --auto; fi",
])
def test_auto_merge_behind_a_repo_flag_or_keyword_is_refused(fx: Fx, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "auto-merge" in reason


@pytest.mark.parametrize("command", [
    f"curl -XPUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"curl --request=PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    "gh api graphql -F query=@merge.graphql",
    "gh api graphql --input body.json",
    "curl -d @q.json https://api.github.com/graphql",
])
def test_merges_the_guard_cannot_read_are_refused(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone), command


def test_an_inline_graphql_read_passes(fx: Fx, clone: Path) -> None:
    assert bash(fx, "gh api graphql -f query='{ viewer { login } }'", clone) is None


@pytest.mark.parametrize("command", [
    "git commit --no-veri -m x",
    "git push --no-verif origin feature",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
    "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=CORE.HOOKSPATH GIT_CONFIG_VALUE_0=/x git push",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x; git commit -m x",
    "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/x'\" git commit -m x",
    "git --config-env=core.hooksPath=EMPTY commit -m x",
    "git -c Core.HooksPath=/x push",
    "bash -lc 'git commit -n -m x'",
    "if true; then git commit --no-verify -m x; fi",
])
def test_more_hook_bypasses_are_refused(fx: Fx, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "fix what it names" in reason, command


@pytest.mark.parametrize("command", [
    "git commit -uno -m x",
    "git commit -Skey -m x",
    "git commit --no-verbose -m x",
    "git push --no-ver",  # ambiguous in git (`--no-verbose`), so git itself refuses it
])
def test_options_that_only_look_like_no_verify_pass(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command


def test_a_slow_github_runs_out_of_budget_and_refuses(fx: Fx, clone: Path) -> None:
    import time

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


# The token-to-decision points, each probed with unusual spellings: a shell's options, wrappers and their
# values, runners, substitution and quoting, gh's flag forms, methods, endpoints, PR selectors and repos.

CHECKED_MERGES = [
    # shell options that take a value, `+` options, options after -c, here-strings
    "bash -o pipefail -c 'gh pr merge 12'",
    "sh -O extglob -c 'gh pr merge 12'",
    "bash +x -c 'gh pr merge 12'",
    "bash -c -e 'gh pr merge 12'",
    "bash --rcfile /dev/null -c 'gh pr merge 12'",
    "bash --norc --noprofile -c 'gh pr merge 12'",
    "bash -co pipefail 'gh pr merge 12'",
    "bash <<< 'gh pr merge 12'",
    "zsh -fc 'gh pr merge 12'",
    # wrappers with option values, substitution, quoting
    "sudo -u root gh pr merge 12",
    "timeout -s KILL 5 gh pr merge 12",
    "timeout --kill-after=1 5 gh pr merge 12",
    "env -i gh pr merge 12",
    "env -S 'gh pr merge 12'",
    "nice -n 5 gh pr merge 12",
    "command gh pr merge 12",
    "echo `gh pr merge 12`",
    "x=$(gh pr merge 12)",
    "gh pr $'merge' 12",
    "g\\h pr merge 12",
    "/usr/local/bin/gh pr merge 12",
    # gh's flag forms, methods, endpoints
    f"gh -R={REPO} pr merge 12",
    f"gh pr merge 12 --repo {REPO}",
    f"gh api -X GET -X PUT repos/{REPO}/pulls/12/merge",
    f"gh api -X PUT -X GET repos/{REPO}/pulls/12/merge",
    f"gh api -X=PUT repos/{REPO}/pulls/12/merge",
    f"gh api -iXPUT repos/{REPO}/pulls/12/merge",
    f"gh api -X put repos/{REPO}/pulls/12/merge",
    f"gh api -f merge_method=squash repos/{REPO}/pulls/12/merge",
    f"gh api -X PUT REPOS/{REPO}/PULLS/12/MERGE",
    f"gh api -X PUT repos/{REPO}/pulls/12/../12/merge",
    f"gh api -X PUT repos%2F{REPO.replace('/', '%2F')}%2Fpulls%2F12%2Fmerge",
    f"gh api -X PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"gh api -X PUT /repos/{REPO}/pulls/12/merge/",
    # PR selectors
    "gh pr merge '#12'",
    "gh pr merge HTTPS://GITHUB.COM/example-owner/example-repo/pull/12/files",
    "gh pr merge -- 12",
    # a line continuation, substitutions inside double quotes, a `#` inside a word
    "gh pr \\\nmerge 12",
    "echo \"$(gh pr merge 12)\"",
    "x=\"`gh pr merge 12`\"",
    "echo a#b; gh pr merge 12",
]


@pytest.mark.parametrize("command", CHECKED_MERGES)
def test_every_spelling_of_a_merge_reaches_the_record_check(fx: Fx, clone: Path, command: str) -> None:
    fx.comments(comment(record("gates")))
    reason = bash(fx, command, clone)
    assert reason and "no review record" in reason, (command, reason)


NOT_MERGES = [
    "bash script.sh 'gh pr merge 12'",  # arguments of a script, not commands
    "bash -o pipefail -c 'ls -la'",
    "sudo -u root ls",
    "timeout -s KILL 5 ls",
    f"gh api --method=GET repos/{REPO}/pulls/12/merge",
    f"gh api -XGET repos/{REPO}/pulls/12/merge",
    f"gh api -X HEAD repos/{REPO}/pulls/12/merge",
    "gh api graphql -F n=@count.txt -f query='{viewer{login}}'",
    "gh api graphql -fquery='{viewer{login}}'",
    "curl -u someone@example.com -d '{\"query\":\"{viewer{login}}\"}' https://api.github.com/graphql",
    "curl -H 'X-Note: a@b' -d '{\"query\":\"{viewer{login}}\"}' https://api.github.com/graphql",
    f"curl -s https://api.github.com/repos/{REPO}/pulls/12/merge",
]


@pytest.mark.parametrize("command", NOT_MERGES)
def test_look_alikes_that_merge_nothing_pass(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command


GRAPHQL_REFUSED = [
    "gh api graphql --input=q.json",
    "gh api graphql --input q.json",
    "gh api graphql -Fquery=@q.graphql",
    "gh api graphql -F=query=@q.graphql",
    "gh api graphql --field=query=@q.graphql",
    "gh api graphql --field query=@q.graphql",
    "gh api graphql -iFquery=@q.graphql",
    "gh api graphql -fquery='mutation{mergePullRequest(input:{}){clientMutationId}}'",
    "gh api graphql -f=query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
    "gh api graphql --raw-field=query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
    "gh api graphql --raw-field 'query=mutation{MERGEPULLREQUEST(input:{}){clientMutationId}}'",
    "gh api graphql -F query='mutation{enablePullRequestAutoMerge(input:{}){clientMutationId}}'",
    "gh api /graphql -F query=@q.graphql",
    "gh api https://api.github.com/graphql --input q.json",
    "curl -d @q.json https://api.github.com/graphql",
    "curl --data-binary @q.json https://api.github.com/graphql",
    "curl -d@q.json https://api.github.com/graphql",
    "curl -T q.json https://api.github.com/graphql",
    "curl --json @q.json https://API.GITHUB.COM/graphql",
    "wget --post-file=q.json https://api.github.com/graphql",
    "http POST https://api.github.com/graphql @q.json",
    "curl -d '{\"query\":\"mutation{mergePullRequest(input:{}){clientMutationId}}\"}' https://api.github.com/graphql",
]


@pytest.mark.parametrize("command", GRAPHQL_REFUSED)
def test_every_spelling_of_an_unreadable_or_merging_graphql_call_is_refused(fx: Fx, clone: Path,
                                                                           command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "GraphQL" in reason, (command, reason)


HTTP_MERGES = [
    f"curl -sSXPUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"curl -X PUT -X GET https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"curl -d '{{}}' https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"curl --request PUT HTTPS://API.GITHUB.COM/repos/{REPO}/pulls/12/merge",
    f"curl -X PUT api.github.com//repos/{REPO}/pulls/12/merge",
    f"wget --method=PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"http PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
    f"xh put https://api.github.com/repos/{REPO}/pulls/12/merge merge_method=squash",
]


@pytest.mark.parametrize("command", HTTP_MERGES)
def test_every_http_client_merge_is_refused(fx: Fx, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "HTTP client" in reason, (command, reason)


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


# Forms outside what the guard covers pass unchecked, as its header says; ordinary searches among them.

OUT_OF_SCOPE = [
    "find docs -name '*.md' -exec grep -l 'gh pr merge' {} +",
    "strace -f -e trace=execve grep 'gh pr merge' README.md",
    "parallel echo ::: 'gh pr merge 5'",
    "setsid gh pr merge 12",
    "find . -maxdepth 0 -exec gh pr merge 12 \\;",
    "su -c 'gh pr merge 12' someone",
    "echo 'gh pr merge 12' | bash",
    "echo 12 | xargs gh pr merge",
    "busybox sh -c 'gh pr merge 12'",
    "x=merge; gh pr $x 12",
]


@pytest.mark.parametrize("command", OUT_OF_SCOPE)
def test_forms_outside_the_covered_ones_pass_without_reading_github(fx: Fx, clone: Path, command: str) -> None:
    assert bash(fx, command, clone) is None, command
    assert fx.gets() == [], command


@pytest.mark.parametrize("command", ["time -p gh pr merge 5", "time gh pr merge 5", "time -f %e gh pr merge 5"])
def test_time_with_its_options_is_a_wrapper(fx: Fx, clone: Path, command: str) -> None:
    fx.comments(comment(record("gates")))
    reason = bash(fx, command, clone)
    assert reason and "PR 5" in reason, reason


@pytest.mark.parametrize("command", [
    f"curl -X PUT https://api.github.com/repos%2F{REPO.replace('/', '%2F')}%2Fpulls%2F12%2Fmerge",
    f"curl -X PUT https://api.github.com/repos/{REPO}/pulls/12/../12/merge",
    f"curl -X PUT 'https://api.github.com/repos/{REPO}/pulls/12/merge?x=1'",
    f"curl -X PUT https://api.github.com/REPOS/{REPO}/PULLS/12/MERGE/",
    f"curl -X PUT --url https://api.github.com/repos/{REPO}/pulls/12/merge",
])
def test_an_http_client_merge_path_is_decoded_as_gh_does(fx: Fx, clone: Path, command: str) -> None:
    reason = bash(fx, command, clone)
    assert reason and "HTTP client" in reason, (command, reason)

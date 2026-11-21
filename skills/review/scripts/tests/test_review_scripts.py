"""The review skill's scripts (gate_stamp.sh, verdict.sh, tier.sh, record.py) against a stub `gh` (stub_gh.py)
and throwaway git repos with a local bare remote.

Nothing reaches GitHub: the stub answers reads from files and records every write.
Run: uvx --from pytest==8.4.2 pytest -q skills/review/scripts/tests
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
STUB = Path(__file__).resolve().parent / "stub_gh.py"
NAMES = ("lib.sh", "gate_stamp.sh", "verdict.sh", "tier.sh")
ROUND = ("--mode", "focused", "--model", "opus", "--effort", "medium")  # how a review round ran, which verdict.sh records
UVX = shutil.which("uvx")
SHELLCHECK_PY_VERSION = "0.11.0.1"
# Marker prefixes, split so the repo's reference check does not read them as plugin skill names.
GATES, REVIEW = "<!-- loadout" + ":gates", "<!-- loadout" + ":review"
ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    STUB.chmod(0o755)
    (bin_dir / "gh").symlink_to(STUB)
    fx = tmp_path / "fx"
    fx.mkdir()
    e = {**os.environ, **ID, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_DIR": str(fx),
         "REVIEW_REPO": "example-owner/example-repo", "HOME": str(tmp_path / "home")}
    for k in ("DRY_RUN", "STUB_FAIL", "STUB_MANGLE"):
        e.pop(k, None)
    return e


class World:
    """A bare remote with `main`, and a clone on branch `feature` with PR 12 pointing at its pushed head."""

    def __init__(self, tmp_path: Path, env: dict[str, str]) -> None:
        self.env, self.fx = env, Path(env["STUB_DIR"])
        self.remote = tmp_path / "remote.git"
        self.git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.remote))
        seed = tmp_path / "seed"
        seed.mkdir()
        self.git(seed, "init", "-q", "-b", "main")
        (seed / "README.md").write_text("seed\n")
        (seed / "src").mkdir()
        (seed / "src/app.py").write_text("x = 1\n")
        self.git(seed, "add", ".")
        self.git(seed, "commit", "-qm", "seed")
        self.git(seed, "push", "-q", str(self.remote), "main")
        self.seed = seed
        self.repo = tmp_path / "repo"
        self.git(tmp_path, "clone", "-q", str(self.remote), str(self.repo))
        self.git(self.repo, "switch", "-q", "-c", "feature")
        (self.fx / "pulls.json").write_text(json.dumps([{"number": 12}]))

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                              env=self.env).stdout.strip()

    def commit(self, files: dict[str, str], msg: str = "change", push: bool = True) -> str:
        for name, text in files.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-qm", msg)
        head = self.git(self.repo, "rev-parse", "HEAD")
        if push:
            self.push()
        return head

    def push(self) -> None:
        self.git(self.repo, "push", "-q", "-f", "origin", "feature")
        head = self.git(self.repo, "rev-parse", "HEAD")
        (self.fx / "pr.json").write_text(json.dumps({"number": 12, "head": {"sha": head}}))

    def main_moves(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            (self.seed / name).write_text(text)
        self.git(self.seed, "commit", "-qam", "main moves")
        self.git(self.seed, "push", "-q", str(self.remote), "main")
        self.git(self.repo, "fetch", "-q", "origin")

    def run(self, script: str, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPTS / script), *args], cwd=self.repo, env={**self.env, **extra},
                              capture_output=True, text=True, errors="replace", timeout=60)

    def comments(self) -> list[dict]:
        p = self.fx / "comments.json"
        return json.loads(p.read_text()) if p.exists() else []

    def writes(self) -> list[dict]:
        p = self.fx / "calls.jsonl"
        calls = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
        return [c for c in calls if c["method"] != "GET"]


@pytest.fixture
def w(tmp_path: Path, env: dict[str, str]) -> World:
    return World(tmp_path, env)


def test_scripts_are_executable_and_parse() -> None:
    for name in NAMES:
        subprocess.run(["bash", "-n", str(SCRIPTS / name)], check=True)
        if name != "lib.sh":
            assert os.access(SCRIPTS / name, os.X_OK), name


@pytest.mark.skipif(UVX is None, reason="uvx not installed")
def test_shellcheck_clean() -> None:
    assert UVX
    done = subprocess.run(
        [UVX, "--from", f"shellcheck-py=={SHELLCHECK_PY_VERSION}", "shellcheck", "-x", "-P", str(SCRIPTS)]
        + [str(SCRIPTS / n) for n in NAMES],
        capture_output=True, text=True, timeout=240, cwd=SCRIPTS,
    )
    assert done.returncode == 0, done.stdout + done.stderr


# gate_stamp.sh


def test_gate_stamp_posts_a_gates_record_for_the_head(w: World) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--", "bash", "-c", "echo running; echo '12 passed in 0.3s'")
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    lines = c["body"].split("\n")
    assert lines[0] == "🤖 Gates: success"
    assert lines[1] == f"{GATES} sha={head} state=success -->"
    assert "- Exit code: 0" in c["body"] and "12 passed in 0.3s" in c["body"] and "<details>" in c["body"]
    assert f"Gates on {head}: success, recorded on PR 12" in done.stdout
    assert "exit 0" in done.stdout


def test_gate_stamp_posts_the_last_40_non_blank_lines_whatever_they_say(w: World, tmp_path: Path) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    log = tmp_path / "log.txt"
    # Installer-shaped lines stay like any other line.
    shapes = ["lockfile drift:", " - numpy==1.26.0", " + numpy==2.0.0", "- total == 3", "Downloaded report.csv",
              "Collecting garbage failed hard", "Installed 3 packages in 2ms", "Resolved 41 packages in 3ms"]
    lines = [f"early line {i}" for i in range(200)] + [f"late line {i}" for i in range(31)] + shapes
    lines += ["", "\x1b[32m1 failed in 0.3s\x1b[0m"]
    log.write_text("\n".join(lines) + "\n")
    done = w.run("gate_stamp.sh", "--", "bash", "-c", f"cat {log}; exit 1")
    assert done.returncode == 1, done.stderr
    body = w.comments()[0]["body"]
    assert len(body) < 4000, len(body)
    assert "- Exit code: 1" in body and "- Last line: 1 failed in 0.3s" in body
    assert "late line 0\n" in body and "early line" not in body and "\x1b" not in body
    assert [x for x in shapes if x not in body] == []
    assert f"<summary>Output: its last 40 non-blank lines of {len(lines)}</summary>" in body


@pytest.mark.parametrize("odd", [b"\x00", b"\xff"])
@pytest.mark.parametrize("on_last", [False, True])
def test_gate_stamp_records_output_holding_a_nul_or_invalid_byte(w: World, tmp_path: Path, odd: bytes,
                                                                on_last: bool) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    log = tmp_path / "log.txt"
    middle, last = b"middle line", b"12 passed in 0.3s"
    if on_last:
        last += b" " + odd
    else:
        middle += b" " + odd
    log.write_bytes(b"line one\n" + middle + b"\n" + last + b"\n")
    done = w.run("gate_stamp.sh", "--", "cat", str(log), LC_ALL="C.UTF-8")
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    body = c["body"]
    assert "- Last line: 12 passed in 0.3s" in body and "line one\nmiddle line" in body
    assert "its last 3 non-blank lines of 3</summary>" in body and "\x00" not in body


def test_gate_stamp_gives_whitespace_only_lines_no_tail_slot(w: World, tmp_path: Path) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    log = tmp_path / "log.txt"
    log.write_text("".join(f"line {i}\n" for i in range(60)) + "   \n\t\n" * 5 + "done\n")
    done = w.run("gate_stamp.sh", "--", "cat", str(log))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert "```text\nline 21\n" in body and "line 20\n" not in body and "line 59\ndone\n" in body


def test_gate_stamp_counts_a_short_output_as_it_is(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--", "printf", "a\\nb\\nc\\n")
    assert done.returncode == 0, done.stderr
    assert "<summary>Output: its last 3 non-blank lines of 3</summary>" in w.comments()[0]["body"]


def test_gate_stamp_records_failure_and_keeps_the_exit_code(w: World) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--pr", "12", "--", "bash", "-c", "echo '1 failed'; exit 4")
    assert done.returncode == 4
    [c] = w.comments()
    assert c["body"].startswith(f"🤖 Gates: failure\n{GATES} sha={head} state=failure -->")


def test_gate_stamp_refuses_a_dirty_tree(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    (w.repo / "new.txt").write_text("untracked\n")
    done = w.run("gate_stamp.sh", "--", "touch", str(w.repo / "ran"))
    assert done.returncode == 2 and "uncommitted changes" in done.stderr
    assert not (w.repo / "ran").exists() and w.writes() == []


def test_gate_stamp_refuses_a_head_the_pr_does_not_have(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    w.commit({"src/app.py": "x = 3\n"}, push=False)
    done = w.run("gate_stamp.sh", "--", "touch", str(w.repo.parent / "ran"))
    assert done.returncode == 2 and "push (or pull)" in done.stderr
    assert not (w.repo.parent / "ran").exists() and w.writes() == []


def test_gate_stamp_needs_an_open_pr(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    (w.fx / "pulls.json").write_text("[]")
    done = w.run("gate_stamp.sh", "--", "true")
    assert done.returncode == 2 and "open the draft PR first" in done.stderr


def test_gate_stamp_refuses_a_command_that_moves_head(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--", "git", "commit", "-q", "--allow-empty", "-m", "sneaky")
    assert done.returncode == 2 and "moved HEAD" in done.stderr and w.writes() == []


def test_gate_stamp_dry_run_posts_nothing(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--dry-run", "--", "true")
    assert done.returncode == 0
    assert w.writes() == []
    assert "dry-run: gh api -X POST repos/example-owner/example-repo/issues/12/comments" in done.stderr
    assert GATES in done.stderr and "not posted (dry run)" in done.stdout


@pytest.mark.parametrize("extra", [{"STUB_FAIL": "/comments"}, {"STUB_MANGLE": "1"}])
def test_gate_stamp_exits_3_when_the_record_is_not_posted_whole(w: World, extra: dict[str, str]) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--", "true", **extra)
    assert done.returncode == 3 and "NOT recorded" in done.stdout


# tier.sh


def tier(w: World, **extra: str) -> tuple[int, list[str], str]:
    done = w.run("tier.sh", **extra)
    return done.returncode, done.stdout.splitlines(), done.stderr


def test_tier_docs_only_is_routine_and_code_is_standard(w: World) -> None:
    w.commit({"docs/guide.md": "hi\n", "NOTES.txt": "n\n"})
    assert tier(w)[1] == ["routine", "NOTES.txt", "docs/guide.md"]
    w.commit({"src/app.py": "x = 2\n"})
    assert tier(w)[1] == ["standard", "src/app.py"]


@pytest.mark.parametrize("path", ["AGENTS.md", "sub/CLAUDE.md", ".claude/settings.json", ".githooks/pre-commit",
                                  "cloud/hooks/x.sh", "a/githooks/y", ".github/workflows/ci.yml", "RULES.md"])
def test_tier_floor_is_sensitive(w: World, path: str) -> None:
    w.commit({path: "x\n"})
    assert tier(w)[1] == ["sensitive", path]


def test_tier_floor_is_not_removable_by_review_md(w: World) -> None:
    (w.seed / "REVIEW.md").write_text("## Routine\n- `**`\n")
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "rules")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "rebase", "-q", "origin/main")
    w.commit({".githooks/pre-commit": "x\n", "src/app.py": "y\n"})
    assert tier(w)[1] == ["sensitive", ".githooks/pre-commit"]


@pytest.mark.parametrize("path", ["docs/agents/autopilot.md", "docs/agents/no-session-gcp",
                                  "docs/agents/cloud-setup.local.sh"])
@pytest.mark.parametrize("review_md", [None, "## Routine\n- `docs/**`\n- `**/*.md`\n"])
def test_tier_floor_holds_an_unattended_runs_profile(w: World, path: str, review_md: str | None) -> None:
    if review_md:
        base_has(w, {"REVIEW.md": review_md})
    w.commit({path: "x\n"})
    code, out, err = tier(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert out == ["sensitive", path]


def test_tier_reads_review_md_from_the_base_not_the_change(w: World) -> None:
    (w.seed / "REVIEW.md").write_text("# Review\n\n## Sensitive\n- `src/**`; lenses: security, data\n")
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "rules")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "rebase", "-q", "origin/main")
    # The change drops src/** from REVIEW.md and edits src: the base's rule still holds.
    w.commit({"REVIEW.md": "## Routine\n- `src/**`\n", "src/app.py": "x = 2\n"})
    code, out, _ = tier(w)
    assert out[0] == "sensitive" and "src/app.py (lenses: data, security)" in out


def test_tier_review_md_routine_list_replaces_the_default(w: World) -> None:
    (w.seed / "REVIEW.md").write_text("## Routine\n- `docs/**`\n")
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "rules")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "rebase", "-q", "origin/main")
    w.commit({"notes.md": "x\n"})
    assert tier(w)[1] == ["standard", "notes.md"]


def test_tier_unparsable_review_md_fails_closed(w: World) -> None:
    (w.seed / "REVIEW.md").write_text("## Routine\nanything goes here\n")
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "rules")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "rebase", "-q", "origin/main")
    w.commit({"docs/a.md": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and out[0] == "sensitive" and "cannot be parsed" in err


def template_review_md() -> str:
    """The `REVIEW.md` sample in templates.md, its placeholders filled: globs a/**, b/**, c/**, lenses one, two."""
    text = (SCRIPTS.parent / "templates.md").read_text()
    block = text.split("## REVIEW.md", 1)[1].split("```markdown\n", 1)[1].split("```", 1)[0]
    for glob in ("a/**", "b/**", "c/**"):
        block = block.replace("<glob>", glob, 1)
    block = block.replace("<lens>, <lens>", "one, two")
    assert "<glob>" not in block and "<lens>" not in block
    return re.sub(r"<[^<>]+>", "a reason, in plain words", block)


@pytest.mark.parametrize("files, expected", [
    ({"a/x.py": "x\n", "b/y.py": "y\n"}, ["sensitive", "a/x.py (lenses: one, two)", "b/y.py"]),
    ({"c/z.py": "z\n"}, ["routine", "c/z.py"]),
])
def test_tier_reads_the_template_lines(w: World, files: dict[str, str], expected: list[str]) -> None:
    base_has(w, {"REVIEW.md": template_review_md()})
    w.commit(files)
    code, out, err = tier(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert out == expected


def test_tier_reads_this_repos_review_md_with_its_lenses(w: World) -> None:
    base_has(w, {"REVIEW.md": (SCRIPTS.parents[2] / "REVIEW.md").read_text()})
    w.commit({"cloud/gcp/guard.py": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and err == "", err
    assert out == ["sensitive", "cloud/gcp/guard.py (lenses: control-prober, guardrail-reviewer)"]


def test_tier_takes_the_debrief_skill_as_sensitive_by_this_repos_review_md(w: World) -> None:
    base_has(w, {"REVIEW.md": (SCRIPTS.parents[2] / "REVIEW.md").read_text()})
    w.commit({"skills/debrief/landings.md": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and err == "", err
    assert out == ["sensitive", "skills/debrief/landings.md (lenses: claims-auditor, guardrail-reviewer)"]


@pytest.mark.parametrize("line, lenses", [
    ("- `src/**` — keeps the lenses honest; lenses: one, two", "one, two"),  # the word in a reason is text
    ("- `src/**` — lenses: one", ""),  # no `;`: a reason, not a lenses clause
    ("- `src/**`, `lib/**`", ""),  # the bare form
])
def test_tier_a_reason_is_never_read_as_a_lens(w: World, line: str, lenses: str) -> None:
    base_has(w, {"REVIEW.md": f"## Sensitive\n{line}\n"})
    w.commit({"src/app.py": "x = 2\n", "docs/a.py": "x\n", "tier.sh": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert out == ["sensitive", f"src/app.py (lenses: {lenses})" if lenses else "src/app.py"], out


@pytest.mark.parametrize("line", [
    "- `src/**` guards things",  # text with no em dash
    "- `src/**` - guards things",  # a hyphen is not the reason's dash
    "- `src/**` — guards; things",  # a `;` in a reason
    "- `src/**` — and `docs/**`; lenses: one",  # a glob written in the reason by mistake
    "- `src/**` — x; lenses: one; two",  # a lenses clause that does not end the line
    "- `src/**`; lenses: one two",  # lens names only
])
def test_tier_a_malformed_item_fails_closed(w: World, line: str) -> None:
    base_has(w, {"REVIEW.md": f"## Sensitive\n{line}\n"})
    w.commit({"docs/a.md": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and out[0] == "sensitive" and "cannot be parsed" in err, (line, out, err)


def test_tier_a_rename_counts_its_old_path(w: World) -> None:
    w.commit({".githooks/check": "x\n"})
    w.git(w.repo, "push", "-q", "origin", "feature:main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "mv", ".githooks/check", "check.md")
    w.git(w.repo, "commit", "-qm", "move")
    assert tier(w)[1][0] == "sensitive"


def test_tier_empty_diff_is_an_error(w: World) -> None:
    code, _, err = tier(w)
    assert code == 2 and "changes nothing" in err


# verdict.sh


HARM = "an operator trusts a total that drops rows"
BLOCKING_LINE = 'Blocking: [{"ids": "COR-1", "harm": "%s"}]' % HARM
BLOCKING = f"## Must-fix\n### COR-1\n- rank: must-fix\n- harm: {HARM}\n"


def review_file(tmp: Path, sha: str, verdict: str = "PASS", text: str | None = None,
                blocking: str | None = None) -> str:
    """A verifier's output (agents/finding-verifier.md § Output): its verdict, reviewed and blocking lines, then
    `text` (by default no findings for a PASS, one must-fix that names its harm for a FAIL)."""
    if blocking is None:
        blocking = BLOCKING_LINE if verdict == "FAIL" else "Blocking: none"
    if text is None:
        text = (BLOCKING if verdict == "FAIL" else "") + "No findings.\n```\nquoted fence\n```\n"
    p = tmp / "review.txt"
    p.write_text(f"VERDICT: {verdict} {sha}\nReviewed: {sha}\n{blocking}\n\n{text}")
    return str(p)


def test_verdict_pass_posts_a_review_record(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "fresh-reviewer",
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    lines = c["body"].split("\n")
    assert lines[0] == "🤖 Review: pass (standard tier)"
    assert lines[1] == f"{REVIEW} sha={head} state=success tier=standard reviewed={head} -->"
    assert "fresh-reviewer" in c["body"] and "No findings." in c["body"] and "````text\n" in c["body"]


def test_verdict_fail_records_failure(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "sensitive", "--result", "fail", "--reviewers", "a, b",
                 "--reviewed", head, "--file", review_file(tmp_path, head, "FAIL", BLOCKING))
    assert done.returncode == 0, done.stderr
    assert w.comments()[0]["body"].startswith(
        f"🤖 Review: fail (sensitive tier)\n{REVIEW} sha={head} state=failure tier=sensitive")


@pytest.mark.parametrize("verdict, state", [("PASS", "success"), ("FAIL", "failure")])
def test_verdict_takes_its_result_from_the_verifiers_verdict_line(w: World, tmp_path: Path, verdict: str,
                                                                   state: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head, verdict))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state={state} tier=standard" in w.comments()[0]["body"]


@pytest.mark.parametrize("result, verdict", [("pass", "FAIL"), ("fail", "PASS")])
def test_verdict_refuses_a_result_the_verifier_did_not_give(w: World, tmp_path: Path, result: str,
                                                            verdict: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", result, "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, head, verdict))
    assert done.returncode == 2 and "contradicts the verifier" in done.stderr
    assert w.writes() == []


def test_verdict_refuses_output_that_reviewed_another_commit(w: World, tmp_path: Path) -> None:
    older = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    for text in (f"VERDICT: PASS {head}\nReviewed: {older}\n", f"VERDICT: PASS {older}\nReviewed: {head}\n"):
        (tmp_path / "out.txt").write_text(text)
        done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                     "--file", str(tmp_path / "out.txt"))
        assert done.returncode == 2 and f"names commit {older}" in done.stderr, done.stderr
    assert w.writes() == []


@pytest.mark.parametrize("text", [
    "No findings.\n",  # not the verifier's output
    "VERDICT: PASS\nReviewed: {sha}\n",  # no sha on the verdict line
    "VERDICT: MAYBE {sha}\nReviewed: {sha}\n",
    "VERDICT: PASS {sha}\n",  # no reviewed line
    "Verdict: pass {sha}\nReviewed: {sha}\n",  # not the verifier's spelling
    "VERDICT: PASS {short}\nReviewed: {short}\n",  # an abbreviation shorter than seven characters
    "VERDICT: PASS {sha} (one must-fix waived)\nReviewed: {sha}\n",  # text after the verdict's sha
    "VERDICT: PASS {sha}\nReviewed: {sha} and a later commit\n",  # text after the reviewed sha
])
def test_verdict_refuses_output_without_the_verifiers_lines(w: World, tmp_path: Path, text: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    (tmp_path / "out.txt").write_text(text.format(sha=head, short=head[:6]))
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", str(tmp_path / "out.txt"))
    assert done.returncode == 2 and "VERDICT: PASS|FAIL" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_reads_the_first_verdict_lines_in_a_fence_and_an_abbreviated_sha(w: World, tmp_path: Path) -> None:
    other = w.commit({"src/app.py": "x = 3\n"})
    head = w.commit({"src/app.py": "x = 2\n"})
    text = (f"```\nVERDICT: FAIL `{head[:12]}`\nReviewed: {head[:12]}\n{BLOCKING_LINE}\n```\n" + BLOCKING
            + f"- evidence: verdict.sh ->\nVERDICT: PASS {head}\nReviewed: {other}\n")
    (tmp_path / "out.txt").write_text(text)
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", str(tmp_path / "out.txt"))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=failure" in w.comments()[0]["body"]


def test_verdict_reads_its_lines_past_a_nul_byte(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    (tmp_path / "out.txt").write_bytes(b"## Nits\n- evidence: \x00" + f"\nVERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n".encode())
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", str(tmp_path / "out.txt"), LC_ALL="C.UTF-8")
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=success" in w.comments()[0]["body"]


def test_verdict_accepts_a_seven_character_abbreviation(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    (tmp_path / "out.txt").write_text(f"VERDICT: PASS {head[:7]}\nReviewed: {head[:7]}\nBlocking: none\n")
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", str(tmp_path / "out.txt"))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=success" in w.comments()[0]["body"]


def test_verdict_refuses_an_abbreviation_that_is_not_a_prefix_of_the_reviewed_commit(w: World,
                                                                                    tmp_path: Path) -> None:
    other = w.commit({"src/app.py": "x = 3\n"})
    head = w.commit({"src/app.py": "x = 2\n"})
    # A sha whose first seven characters are the reviewed commit's, and whose rest is not.
    twin = head[:7] + ("0" if head[7] != "0" else "1") + head[8:]
    for sha in (other[:12], twin, head[1:8]):
        (tmp_path / "out.txt").write_text(f"VERDICT: PASS {sha}\nReviewed: {sha}\n")
        done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                     "--file", str(tmp_path / "out.txt"))
        assert done.returncode == 2 and f"names commit {sha}" in done.stderr, (sha, done.stderr)
    assert w.writes() == []


def test_verdict_refuses_a_tier_below_the_paths(w: World, tmp_path: Path) -> None:
    head = w.commit({".githooks/pre-commit": "x\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 2 and "make it sensitive" in done.stderr
    assert w.comments() == []
    done = w.run("verdict.sh", "12", "--tier", "routine")
    assert done.returncode == 2 and w.comments() == []


def test_verdict_routine_on_routine_paths_needs_no_reviewer(w: World) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    done = w.run("verdict.sh", "12", "--tier", "routine")
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert body.startswith(f"🤖 Review: pass (routine tier)\n{REVIEW} sha={head} state=success "
                           f"tier=routine reviewed={head} -->")
    assert "needs gates only" in body and "<details>" not in body


def test_verdict_allows_a_higher_tier(w: World, tmp_path: Path) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "sensitive", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 0, done.stderr


def test_verdict_refuses_a_head_with_an_unreviewed_commit(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"src/app.py": "x = 3\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr
    assert w.comments() == []


def test_verdict_accepts_a_clean_merge_of_the_base(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    head = w.git(w.repo, "rev-parse", "HEAD")
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert f"sha={head} state=success tier=standard reviewed={reviewed} -->" in body
    assert "clean merges of main" in body


def test_verdict_refuses_a_merge_that_adds_changes(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-commit", "origin/main")
    (w.repo / "src/app.py").write_text("x = 'slipped in'\n")
    w.git(w.repo, "add", "-A")
    w.git(w.repo, "commit", "-qm", "merge main")
    w.push()
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_standard_needs_output_and_the_reviewed_commit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    assert w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head).returncode == 2
    assert w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--file", review_file(tmp_path, head)).returncode == 2
    assert w.writes() == []


def test_verdict_clips_output_to_the_comment_limit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, head, "PASS", "é" * 70000 + "\nEND\n"))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert len(body) <= 65536 and "Clipped to fit GitHub's comment size" in body and "END" not in body
    assert body.rstrip().endswith("</details>")


def test_verdict_read_back_mismatch_fails(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, head), STUB_MANGLE="1")
    assert done.returncode == 1 and "does not hold the body that was sent" in done.stderr


def test_verdict_dry_run_posts_nothing(w: World) -> None:
    w.commit({"docs/a.md": "x\n"})
    done = w.run("verdict.sh", "12", "--tier", "routine", "--dry-run")
    assert done.returncode == 0, done.stderr
    assert w.writes() == []
    assert "dry-run: gh api -X POST repos/example-owner/example-repo/issues/12/comments" in done.stderr


def base_has(w: World, files: dict[str, str]) -> None:
    """Puts `files` on main and rebases the feature branch onto it."""
    for name, text in files.items():
        p = w.seed / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "base")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "rebase", "-q", "origin/main")


@pytest.mark.parametrize("path", ["skills/x/SKILL.md", "GEMINI.md", "claude.md", "docs/Agents.md", ".mcp.json",
                                  "pkg/.claude/settings.json", "sub/.githooks/pre-push", ".husky/pre-commit",
                                  ".github/actions/setup/action.yml", ".github/CODEOWNERS", "CLAUDE.local.md"])
def test_tier_floor_covers_other_agent_files(w: World, path: str) -> None:
    w.commit({path: "x\n"})
    assert tier(w)[1] == ["sensitive", path]


def test_tier_follows_imports_from_the_base_instruction_files(w: World) -> None:
    base_has(w, {"CLAUDE.md": "Rules: @docs/agent-rules.md and `@not/imported.md`\n",
              "docs/agent-rules.md": "More: @../shared/style.md\n@./deep.md\n",
              "shared/style.md": "style\n", "docs/deep.md": "deep\n", "not/imported.md": "x\n",
              "docs/other.md": "plain\n"})
    for path, importer in (("docs/agent-rules.md", "CLAUDE.md"), ("shared/style.md", "docs/agent-rules.md"),
                           ("docs/deep.md", "docs/agent-rules.md")):
        w.git(w.repo, "reset", "-q", "--hard", "origin/main")
        w.commit({path: "changed\n"})
        assert tier(w)[1] == ["sensitive", f"{path} (imported by {importer})"], path
    w.git(w.repo, "reset", "-q", "--hard", "origin/main")
    w.commit({"not/imported.md": "changed\n", "docs/other.md": "changed\n"})
    assert tier(w)[1][0] == "routine"


def test_tier_reads_imports_from_the_base_not_the_change(w: World) -> None:
    base_has(w, {"AGENTS.md": "see @policy.md\n", "policy.md": "r\n"})
    # The change drops the import and edits the imported file: the base still imports it.
    w.commit({"AGENTS.md": "nothing\n", "policy.md": "weakened\n"})
    assert "policy.md (imported by AGENTS.md)" in tier(w)[1]


def test_verdict_refuses_a_merge_of_a_branch_that_is_not_the_default(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.git(w.repo, "switch", "-q", "-c", "side", "origin/main")
    (w.repo / "side.txt").write_text("side\n")
    w.git(w.repo, "add", ".")
    w.git(w.repo, "commit", "-qm", "side")
    w.git(w.repo, "switch", "-q", "feature")
    w.git(w.repo, "merge", "-q", "--no-edit", "side")
    w.push()
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "not on main" in done.stderr
    assert w.comments() == []


def test_verdict_refuses_an_octopus_merge(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "switch", "-q", "-c", "side", "origin/main~1")
    (w.repo / "side.txt").write_text("side\n")
    w.git(w.repo, "add", ".")
    w.git(w.repo, "commit", "-qm", "side")
    w.git(w.repo, "switch", "-q", "feature")
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main", "side")
    w.push()
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_refuses_more_than_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(21):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_accepts_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(20):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 0, done.stderr


def test_read_back_accepts_only_the_relay_footer(tmp_path: Path) -> None:
    """A cloud proxy appends its attribution footer to a relayed comment: that, and nothing else, may follow."""
    import json as _json
    import subprocess as _sp
    import sys as _sys

    record = Path(__file__).resolve().parents[1] / "record.py"
    sent = tmp_path / "sent.md"
    sent.write_text("first line\n<!-- marker -->\n\nbody\n", encoding="utf-8")
    footer = "\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_"

    def same(stored: str) -> int:
        back = tmp_path / "back.json"
        back.write_text(_json.dumps({"body": stored}), encoding="utf-8")
        return _sp.run([_sys.executable, str(record), "same", str(back), str(sent)]).returncode

    body = sent.read_text(encoding="utf-8")
    assert same(body) == 0
    assert same(body.rstrip("\n") + footer) == 0
    assert same(body.rstrip("\n") + "\n\nanything else") == 1
    assert same(body.rstrip("\n") + footer + "\nmore") == 1
    assert same("changed " + body) == 1
    assert same(body.rstrip("\n") + footer.lstrip("\n")) == 1  # glued to the body's last line


# verdict.sh: a must-fix blocks only by the harm the verifier's `Blocking:` line names


@pytest.mark.parametrize("blocking, why", [
    (None, "not a `Blocking:` line"),  # the line is missing
    ("Blocking: maybe", "neither `none` nor a JSON list"),
    ("Blocking: []", "non-empty JSON list"),
    ('Blocking: [{"harm": "an operator trusts a wrong total"}]', "has no `ids`"),
    ('Blocking: [{"ids": "COR-1"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "COR-1", "harm": "none"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "COR-1", "harm": "`n/a`"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "COR-1", "harm": "wrong"}]', "COR-1 names no harm"),  # one word
    ('Blocking: [{"ids": "COR-1", "harm": "<who acts wrongly or what breaks>"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "COR-1", "harm": "`<who acts wrongly or what breaks>`"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "COR-1", "harm": "no concrete harm"}]', "COR-1 names no harm"),  # filler only
    ('Blocking: [{"ids": "COR-1", "harm": "TBD TBD TBD"}]', "COR-1 names no harm"),
    ('Blocking: [{"ids": "ZZZ-9", "harm": "%s"}]' % HARM, "names ZZZ-9, which no `###` heading"),
    ('Blocking: [{"ids": "COR-1, CLM-2, COR-3", "harm": "%s"}]' % HARM, "names COR-3, which no"),
    ('Blocking: {"ids": "COR-1", "harm": "%s"}' % HARM, "non-empty JSON list"),  # JSON, not a list
    ('Blocking: [{"ids": "COR-1", "harm": "%s"}, {"ids": "CLM-2", "harm": ""}]' % HARM, "CLM-2 names no harm"),
])
def test_verdict_refuses_a_blocking_line_without_a_named_harm(w: World, tmp_path: Path, blocking: str | None,
                                                              why: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    path = review_file(tmp_path, head, "FAIL", BLOCKING + "### CLM-2\n- rank: must-fix\n", blocking=blocking or "")
    if blocking is None:  # drop the line: the one after `Reviewed:` is then blank
        Path(path).write_text(Path(path).read_text().replace("\n\n\n", "\n\n"))
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head, "--file", path)
    assert done.returncode == 2 and why in done.stderr, done.stderr
    assert w.writes() == []


@pytest.mark.parametrize("verdict, blocking, why", [
    ("FAIL", "Blocking: none", "lists no must-fix"),
    ("PASS", BLOCKING_LINE, "lists 1 must-fix"),
])
def test_verdict_refuses_a_blocking_line_that_contradicts_the_verdict(w: World, tmp_path: Path, verdict: str,
                                                                      blocking: str, why: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head, verdict, BLOCKING, blocking=blocking))
    assert done.returncode == 2 and why in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_takes_a_listed_id_only_from_a_heading_outside_a_fence(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    for text in ("Settled in the brief: - COR-1: must-fix, fixed\n## Must-fix\n### COR-10\n- rank: must-fix\n",
                 "## Must-fix\n### CLM-2 (re-raises COR-1)\n- evidence: ->\n```\n### COR-1\n```\n",
                 "## Must-fix\n### ###\n### PRE-COR-1, COR-1-2\n"):
        done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                     "--file", review_file(tmp_path, head, "FAIL", text, blocking=BLOCKING_LINE))
        assert done.returncode == 2 and "names COR-1, which no" in done.stderr, done.stderr


@pytest.mark.parametrize("blocking", [
    'Blocking: [{"ids": "LEAK-1", "harm": "leaks secrets"}]',  # two words name a harm
    'Blocking: [{"ids": "LEAK-1", "harm": "<details> clipping hides a leaked token from the owner"}]',
    'Blocking: [{"ids": "LEAK-1", "harm": "`<details>` clipping hides a token from `<owner>`"}]',  # not the slot
    'Blocking: `[{"ids": "LEAK-1", "harm": "leaks secrets"}]`',  # in backticks, as the sha lines may be
])
def test_verdict_accepts_a_named_harm_in_its_usual_shapes(w: World, tmp_path: Path, blocking: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL", "## Must-fix\n### LEAK-1\n- rank: must-fix\n",
                                       blocking=blocking))
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("decoy", ["quoted\x0c", "quoted\r", "\xa0", "\x1c", "\u2003"])
def test_verdict_skips_a_reviewed_line_after_a_non_blank_character(w: World, tmp_path: Path, decoy: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "out.txt"  # grep reads none of these as a line break or a leading blank: line 2 is no header
    p.write_text(f"VERDICT: PASS {head}\n{decoy}Reviewed: {head}\nBlocking: none\n"
                 f"Reviewed: {head}\n{BLOCKING_LINE}\n\n{BLOCKING}")
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head, "--file", str(p))
    assert done.returncode == 2 and "says PASS" in done.stderr, done.stderr


def test_verdict_refuses_when_the_reader_prints_no_count(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    bad = tmp_path / "talking-python"
    bad.mkdir()
    (bad / "python3").write_text("#!/bin/sh\necho many\n")
    (bad / "python3").chmod(0o755)
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL"), PATH=f"{bad}:{w.env['PATH']}")
    assert done.returncode == 2 and "printed no count" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_reads_only_the_blocking_line_not_the_prose(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    prose = ("## Must-fix\n### COR-1\n- rank: must-fix\n- harm: %s\n- evidence: ->\n```\nBlocking: none\n"
             "### CLM-9\n- rank: must-fix\n```\n## Nits\n### CLM-2\n- rank: `must-fix`\n### CLM-3, GRD-1\n" % HARM)
    two = 'Blocking: [{"ids": "COR-1", "harm": "%s"}, {"ids": "CLM-3, GRD-1", "harm": "a lead merges a guard that stops nothing"}]' % HARM
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "sensitive", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL", prose, blocking=two))
    assert done.returncode == 0, done.stderr
    assert f"state=failure tier=sensitive reviewed={head}" in w.comments()[0]["body"]


def test_verdict_refuses_when_it_cannot_read_the_blocking_line(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    bad = tmp_path / "failing-python"
    bad.mkdir()
    (bad / "python3").write_text("#!/bin/sh\nexit 1\n")
    (bad / "python3").chmod(0o755)
    for verdict in ("PASS", "FAIL"):
        done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                     "--file", review_file(tmp_path, head, verdict), PATH=f"{bad}:{w.env['PATH']}")
        assert done.returncode == 2 and "refused" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_reads_the_reviewed_line_grep_reads_whatever_the_locale(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "out.txt"  # in a UTF-8 locale grep would take the em-space line as the header
    p.write_text(f"VERDICT: PASS {head}\n\u2003Reviewed: {head}\n{BLOCKING_LINE}\n"
                 f"Reviewed: {'f' * 40}\nBlocking: none\n\n{BLOCKING}")
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers", "x", "--reviewed", head, "--file", str(p),
                 LC_ALL="C.UTF-8")
    assert done.returncode == 2 and "names commit ffff" in done.stderr, done.stderr


@pytest.mark.parametrize("drop, message", [
    ("--reviewers", "--reviewers names who reviewed"),
    ("--file", "--file is the reviewers' raw output"),
    ("--reviewed", "--reviewed is the full sha"),
])
def test_verdict_above_routine_refuses_each_missing_input_by_its_own_guard(
        w: World, tmp_path: Path, drop: str, message: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    args = {"--reviewers": "x", "--reviewed": head, "--file": review_file(tmp_path, head)}
    args[drop] = {"--reviewers": "", "--file": str(empty), "--reviewed": head[:7]}[drop]
    flat = [part for kv in args.items() for part in kv]
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", *flat)
    assert done.returncode == 2 and message in done.stderr, done.stderr
    assert w.writes() == []


# plan.py and the round line


def plan(w: World, *args: str) -> tuple[int, dict, str]:
    done = subprocess.run([sys.executable, str(SCRIPTS / "plan.py"), "--base", "origin/main", *args, "--json"],
                          cwd=w.repo, env=w.env, capture_output=True, text=True, timeout=60)
    return done.returncode, (json.loads(done.stdout) if done.returncode == 0 else {}), done.stderr


def prior(tmp: Path, sha: str, ids: list[str]) -> str:
    """A FAIL verifier output whose `Blocking:` line lists one must-fix per id."""
    items = [{"ids": i, "harm": HARM} for i in ids]
    blocks = "".join(f"### {i}\n- rank: must-fix\n- harm: {HARM}\n" for i in ids)
    p = tmp / "prior.txt"
    p.write_text(f"VERDICT: FAIL {sha}\nReviewed: {sha}\nBlocking: {json.dumps(items)}\n\n## Must-fix\n{blocks}")
    return str(p)


SENSITIVE_MD = "## Sensitive\n- `guard/**`; lenses: control-prober\n- `data/**`; lenses: leak-hunter\n"


def test_plan_first_review_runs_the_tiers_set_plus_review_md_lenses(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["then"] == ["correctness-reviewer"] and plan(w)[1]["first"] == []
    base_has(w, {"REVIEW.md": SENSITIVE_MD})
    w.commit({"guard/check.py": "ok = True\n"})
    code, out, err = plan(w)
    assert code == 0, err
    assert out["tier"] == "sensitive" and out["mode"] == "focused"
    assert out["first"] == ["correctness-reviewer"]
    assert out["then"] == ["claims-auditor", "guardrail-reviewer", "control-prober"]
    assert out["verifier"] == "finding-verifier"


def test_plan_routine_runs_nobody(w: World) -> None:
    w.commit({"docs/guide.md": "hi\n"})
    out = plan(w)[1]
    assert out["first"] == out["then"] == [] and out["verifier"] == ""


def test_plan_add_only_adds_and_names_a_lens(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w, "--add", "leak-hunter")[1]["then"] == ["leak-hunter"]
    code, _, err = plan(w, "--add", "style-reviewer")
    assert code != 0 and "names no lens" in err


def test_plan_full_and_light_run_one_phase(w: World) -> None:
    base_has(w, {"REVIEW.md": SENSITIVE_MD})
    w.commit({"guard/check.py": "ok = True\n"})
    out = plan(w, "--mode", "full")[1]
    assert out["first"] == [] and out["then"][0] == "correctness-reviewer" and len(out["then"]) == 4
    code, _, err = plan(w, "--mode", "light")
    assert code != 0 and "light mode cannot run a sensitive change's first review" in err


def test_plan_fix_round_reruns_only_the_lenses_it_answers(w: World, tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": SENSITIVE_MD})
    reviewed = w.commit({"guard/check.py": "ok = True\n", "data/load.py": "rows = []\n"})
    w.commit({"guard/check.py": "ok = False\n"})
    code, out, err = plan(w, "--since", reviewed, "--prior", prior(tmp_path, reviewed, ["CTL-1"]))
    assert code == 0, err
    # control-prober answers its finding and REVIEW.md names it for the fixed path; correctness reads the code;
    # claims, guardrail and leak-hunter, whose paths and findings the fix leaves alone, do not rerun.
    assert out["first"] == ["correctness-reviewer"] and out["then"] == ["control-prober"]


def test_plan_fix_round_to_documentation_runs_claims(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n", "docs/app.md": "x is two\n"})
    w.commit({"docs/app.md": "x is 2\n"})
    out = plan(w, "--since", reviewed, "--prior", prior(tmp_path, reviewed, ["CLM-1"]))[1]
    assert out["first"] == [] and out["then"] == ["claims-auditor"]


def test_plan_fix_round_with_an_unknown_prefix_or_in_full_mode_runs_the_whole_set(w: World, tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": SENSITIVE_MD})
    reviewed = w.commit({"guard/check.py": "ok = True\n"})
    w.commit({"guard/check.py": "ok = False\n"})
    whole = ["claims-auditor", "guardrail-reviewer", "control-prober"]
    assert plan(w, "--since", reviewed, "--prior", prior(tmp_path, reviewed, ["REPO-1"]))[1]["then"] == whole
    assert plan(w, "--mode", "full", "--since", reviewed,
                "--prior", prior(tmp_path, reviewed, ["CTL-1"]))[1]["then"] == ["correctness-reviewer", *whole]


def test_plan_fix_round_refuses_a_prior_it_cannot_read_or_a_lone_since(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"src/app.py": "x = 3\n"})
    bad = tmp_path / "bad.txt"
    bad.write_text("no verdict here\n")
    code, _, err = plan(w, "--since", reviewed, "--prior", str(bad))
    assert code != 0 and "--prior is not a verifier output" in err
    code, _, err = plan(w, "--since", reviewed)
    assert code != 0 and "both --since" in err


def test_tier_since_reads_only_the_fix(w: World) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"docs/app.md": "x is two\n"})
    done = w.run("tier.sh", "--since", reviewed)
    assert done.stdout.splitlines() == ["routine", "docs/app.md"], done.stderr


def test_tier_since_refuses_a_commit_off_the_branch(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "moved\n"})
    done = w.run("tier.sh", "--since", w.git(w.seed, "rev-parse", "HEAD"))
    assert done.returncode != 0 and "is not an ancestor" in done.stderr


def test_verdict_records_how_the_round_ran_and_the_merge_guard_still_reads_it(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", *ROUND, "--tier", "standard", "--reviewers",
                 "correctness-reviewer, finding-verifier", "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    lines = c["body"].split("\n")
    assert lines[2] == ("<!-- loadout" + ":round mode=focused model=opus effort=medium "
                        "lenses=correctness-reviewer,finding-verifier -->")
    assert "- Round: focused mode, opus at medium effort" in lines
    spec = importlib.util.spec_from_file_location("merge_guard", SCRIPTS.parents[2] / "cloud/hooks/merge-guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    why, fields = guard.record_problem("review", {**c, "updated_at": "t", "created_at": "t"}, head)
    assert why == "" and fields["state"] == "success"


@pytest.mark.parametrize(("drop", "message"), [
    ("--mode", "--mode is light, focused or full"),
    ("--model", "--model is the reviewers' model"),
    ("--effort", "--effort is the reviewers' effort"),
])
def test_verdict_above_routine_needs_how_the_round_ran(w: World, tmp_path: Path, drop: str, message: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    args = dict(zip(ROUND[::2], ROUND[1::2]))
    args[drop] = "Bad Value"
    flat = [part for kv in args.items() for part in kv]
    done = w.run("verdict.sh", "12", *flat, "--tier", "standard", "--reviewers", "x", "--reviewed", head,
                 "--file", review_file(tmp_path, head))
    assert done.returncode == 2 and message in done.stderr, done.stderr
    assert w.writes() == []


def test_record_refuses_a_round_pair_out_of_shape() -> None:
    done = subprocess.run([sys.executable, str(SCRIPTS / "record.py"), "build", "--kind", "review", "--sha", "a" * 40,
                           "--state", "success", "--title", "t", "--round", "mode=foc used -->"],
                          capture_output=True, text=True)
    assert done.returncode != 0 and "--round pair" in done.stderr

"""The review skill's scripts (gate_stamp.sh, verdict.sh, tier.sh, record.py) against a stub `gh` (stub_gh.py)
and throwaway git repos with a local bare remote.

Nothing reaches GitHub: the stub answers reads from files and records every write.
Run: uvx --from pytest==8.4.2 pytest -q skills/review/scripts/tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
STUB = Path(__file__).resolve().parent / "stub_gh.py"
NAMES = ("lib.sh", "gate_stamp.sh", "verdict.sh", "tier.sh")
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
                              capture_output=True, text=True, timeout=60)

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
    return re.sub(r"<[^<>]+>", "a reason, `in backticks`", block)


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


@pytest.mark.parametrize("line, lenses", [
    ("- `src/**` — runs `tier.sh` and `docs/**`; lenses: one", "one"),  # backticks in a reason are no globs
    ("- `src/**` — keeps the lenses honest; lenses: one, two", "one, two"),  # the word in a reason is text
    ("- `src/**` — lenses: one", ""),  # no `;`: a reason, not a lenses clause
    ("- `src/**`, `lib/**`", ""),  # the bare form
])
def test_tier_a_reason_is_never_read_as_a_glob_or_a_lens(w: World, line: str, lenses: str) -> None:
    base_has(w, {"REVIEW.md": f"## Sensitive\n{line}\n"})
    w.commit({"src/app.py": "x = 2\n", "docs/a.py": "x\n", "tier.sh": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert out == ["sensitive", f"src/app.py (lenses: {lenses})" if lenses else "src/app.py"], out


@pytest.mark.parametrize("line", [
    "- `src/**` guards things",  # text with no em dash
    "- `src/**` - guards things",  # a hyphen is not the reason's dash
    "- `src/**` — guards; things",  # a `;` in a reason
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


def review_file(tmp: Path, text: str = "No findings.\n```\nquoted fence\n```\n") -> str:
    p = tmp / "review.txt"
    p.write_text(text)
    return str(p)


def test_verdict_pass_posts_a_review_record(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "fresh-reviewer",
                 "--reviewed", head, "--file", review_file(tmp_path))
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    lines = c["body"].split("\n")
    assert lines[0] == "🤖 Review: pass (standard tier)"
    assert lines[1] == f"{REVIEW} sha={head} state=success tier=standard reviewed={head} -->"
    assert "fresh-reviewer" in c["body"] and "No findings." in c["body"] and "````text\n" in c["body"]


def test_verdict_fail_records_failure(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", "--tier", "sensitive", "--result", "fail", "--reviewers", "a, b",
                 "--reviewed", head, "--file", review_file(tmp_path, "BLOCKER\n"))
    assert done.returncode == 0, done.stderr
    assert w.comments()[0]["body"].startswith(
        f"🤖 Review: fail (sensitive tier)\n{REVIEW} sha={head} state=failure tier=sensitive")


def test_verdict_refuses_a_tier_below_the_paths(w: World, tmp_path: Path) -> None:
    head = w.commit({".githooks/pre-commit": "x\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path))
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
    done = w.run("verdict.sh", "12", "--tier", "sensitive", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path))
    assert done.returncode == 0, done.stderr


def test_verdict_refuses_a_head_with_an_unreviewed_commit(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"src/app.py": "x = 3\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr
    assert w.comments() == []


def test_verdict_accepts_a_clean_merge_of_the_base(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    head = w.git(w.repo, "rev-parse", "HEAD")
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
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
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_standard_needs_output_and_the_reviewed_commit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    assert w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head).returncode == 2
    assert w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--file", review_file(tmp_path)).returncode == 2
    assert w.writes() == []


def test_verdict_clips_output_to_the_comment_limit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path, "é" * 70000 + "\nEND\n"))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert len(body) <= 65536 and "Clipped to fit GitHub's comment size" in body and "END" not in body
    assert body.rstrip().endswith("</details>")


def test_verdict_read_back_mismatch_fails(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", head, "--file", review_file(tmp_path), STUB_MANGLE="1")
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
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
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
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_refuses_more_than_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(21):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_accepts_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(20):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.run("verdict.sh", "12", "--tier", "standard", "--result", "pass", "--reviewers", "x",
                 "--reviewed", reviewed, "--file", review_file(tmp_path))
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

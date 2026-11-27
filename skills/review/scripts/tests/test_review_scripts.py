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
# The plan (plan.py) of a standard change: one lens and the verifier.
PLANNED = "correctness-reviewer, finding-verifier"
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
    for k in ("DRY_RUN", "STUB_FAIL", "STUB_MANGLE", "STUB_REMOTE"):
        e.pop(k, None)
    return e


class World:
    """A bare remote with `main`, and a clone on branch `feature` with PR 12 pointing at its pushed head."""

    def __init__(self, tmp_path: Path, env: dict[str, str]) -> None:
        self.env, self.fx = env, Path(env["STUB_DIR"])
        self.remote = tmp_path / "remote.git"
        self.git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.remote))
        env["STUB_REMOTE"] = str(self.remote)  # what the stub's branches endpoint answers from
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
        (self.fx / "pr.json").write_text(json.dumps({"number": 12, "head": {"sha": head},
                                                     "base": {"ref": "main", "repo": {"default_branch": "main"}}}))

    def main_moves(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            (self.seed / name).write_text(text)
        self.git(self.seed, "commit", "-qam", "main moves")
        self.git(self.seed, "push", "-q", str(self.remote), "main")
        self.git(self.repo, "fetch", "-q", "origin")

    def run(self, script: str, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPTS / script), *args], cwd=self.repo, env={**self.env, **extra},
                              capture_output=True, text=True, errors="replace", timeout=60)

    def verdict(self, *args: str, cost: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
        """verdict.sh with `args`; above routine, `cost` adds a first round's shape for every --reviewers name."""
        a = list(args)
        if cost and "--tier" in a and a[a.index("--tier") + 1] != "routine":
            a += round_args(a[a.index("--reviewers") + 1] if "--reviewers" in a else "")
        return self.run("verdict.sh", *a, **extra)

    def comments(self) -> list[dict]:
        p = self.fx / "comments.json"
        return json.loads(p.read_text()) if p.exists() else []

    def writes(self) -> list[dict]:
        p = self.fx / "calls.jsonl"
        calls = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
        return [c for c in calls if c["method"] != "GET"]


def round_args(reviewers: str, cycle: int = 1, dupes: int = 0, nits: int = 0) -> list[str]:
    """verdict.sh's round arguments: one --lens per name in `reviewers`, each on Opus at high effort."""
    out = ["--cycle", str(cycle), "--dupes", str(dupes), "--nits", str(nits)]
    for n in (x for x in re.split(r"[,\s]+", reviewers) if x):
        out += ["--lens", f"{n} model=opus effort=high tokens=1000 seconds=10 findings=0"]
    return out


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


# The oldest Python the review path's scripts must parse under: 3.11, a host `python3` they have run on.
OLDEST_PYTHON = "3.11"
REPO_ROOT = SCRIPTS.parents[2]


def review_python_files() -> list[Path]:
    """Every Python file the repo tracks, which holds all the review path runs: `*.py` files and scripts whose first
    line names python (the pre-commit hook's `bin/check-refs`, `bin/check-review-version` and the like)."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    found = []
    for name in filter(None, tracked):
        f = REPO_ROOT / name
        if not f.is_file():
            continue
        first = f.read_bytes()[:80].split(b"\n")[0]
        if f.suffix == ".py" or (not f.suffix and first.startswith(b"#!") and b"python" in first):
            found.append(f)
    return sorted(found)


def test_review_python_files_listed() -> None:
    names = {str(f.relative_to(REPO_ROOT)) for f in review_python_files()}
    hook = (REPO_ROOT / ".githooks/pre-commit").read_text()
    assert {"skills/review/scripts/plan.py", "cloud/hooks/merge-guard.py", "bin/check-review-version",
            "bin/check-refs", "cloud/githooks/check-process-ids.py", "skills/report-kit/tests/build_fixture.py"} <= names
    for run in ("bin/check-refs", "bin/check-review-version", "cloud/githooks/check-process-ids.py"):
        assert run in hook and run in names, run  # every Python the pre-commit hook runs is parsed below


def test_review_scripts_parse_on_oldest_python() -> None:
    """Each file compiles under the oldest supported Python (nothing is written: compile() only parses); a host
    without uvx fails here rather than skipping, so a green run always means the files were parsed."""
    assert UVX, "uvx is required to parse the repo's Python under the oldest supported version; install uv"
    code = ("import sys\n"
            "bad = []\n"
            "for f in sys.argv[1:]:\n"
            "    try:\n"
            "        compile(open(f, encoding='utf-8').read(), f, 'exec')\n"
            "    except SyntaxError as e:\n"
            "        bad.append(f'{f}:{e.lineno}: {e.msg}')\n"
            "print(sys.version_info[:2])\n"
            "print('\\n'.join(bad))\n"
            "sys.exit(1 if bad else 0)\n")
    done = subprocess.run([UVX, "-q", "-p", OLDEST_PYTHON, "python", "-I", "-c", code]
                          + [str(f) for f in review_python_files()],
                          capture_output=True, text=True, timeout=240, cwd=SCRIPTS)
    assert done.stdout.startswith(f"({OLDEST_PYTHON.replace('.', ', ')})"), done.stdout + done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_parse_test_fails_rather_than_skips_without_uvx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(globals(), "UVX", None)
    with pytest.raises(AssertionError, match="uvx is required"):
        test_review_scripts_parse_on_oldest_python()


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
    """The `REVIEW.md` sample in templates.md, its placeholders filled: globs a/** to d/**, lenses one, two."""
    text = (SCRIPTS.parent / "templates.md").read_text()
    block = text.split("## REVIEW.md", 1)[1].split("```markdown\n", 1)[1].split("```", 1)[0]
    for glob in ("a/**", "b/**", "c/**", "d/**"):
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
    assert out == ["sensitive", "cloud/gcp/guard.py (lenses: control-prober)"]


def test_tier_takes_the_debrief_skill_as_sensitive_by_this_repos_review_md(w: World) -> None:
    base_has(w, {"REVIEW.md": (SCRIPTS.parents[2] / "REVIEW.md").read_text()})
    w.commit({"skills/debrief/landings.md": "x\n"})
    code, out, err = tier(w)
    assert code == 0 and err == "", err
    assert out == ["sensitive", "skills/debrief/landings.md (lenses: claims-auditor)"]


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


DISMISSED = "Dismissals: re-ran 0, promoted 0"  # every verifier output's header carries one


def review_file(tmp: Path, sha: str, verdict: str = "PASS", text: str | None = None,
                blocking: str | None = None) -> str:
    """A verifier's output (agents/finding-verifier.md § Output): its verdict, reviewed and blocking lines, then
    `text` (by default no findings for a PASS, one must-fix that names its harm for a FAIL)."""
    if blocking is None:
        blocking = BLOCKING_LINE if verdict == "FAIL" else "Blocking: none"
    if text is None:
        text = (BLOCKING if verdict == "FAIL" else "") + "No findings.\n```\nquoted fence\n```\n"
    p = tmp / "review.txt"
    p.write_text(f"VERDICT: {verdict} {sha}\nReviewed: {sha}\n{blocking}\n{DISMISSED}\n\n{text}")
    return str(p)


@pytest.mark.parametrize("quoted", ["a\u200bb", "x\u200c\u200d\u2060\ufeffy", "rtl \u202e\u2066flip\u2069\u202c",
                                    "mark \u200e\u200f\u061c", "(?<![\\w-])", "see ![a](b)", "< ![x]", "<!-- loadout:review -->",
                                    "soft\u00adhy\u180e\u2061\ufff9", "sep\u2028par\u2029nel\x85", "vt\x0bff\x0c",
                                    "cr\r\nlf\rx", "nb\xa0sp\u3000\u2009\x1f", "ctl \x01\x1b\x80\x9f", "kept \x08\x7f\u034f"])
def test_verdict_posts_an_output_holding_what_github_drops_and_reads_it_back(w: World, tmp_path: Path,
                                                                            quoted: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = review_file(tmp_path, head, text=f"No findings.\n- evidence: `{quoted}`\n```\n{quoted}\n```\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", out)
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    assert c["body"].split("\n")[1].startswith(f"{REVIEW} sha={head} state=success")
    below = "\n".join(c["body"].split("\n")[3:])  # under the title, marker and round line: the quoted output
    assert not re.search("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\u061c\u00ad\u180e\ufff9-\ufffb"
                         "\r\x0b\x0c\x85\x1c-\x1f\u2028\u2029\xa0\u3000\u2000-\u200a\x01-\x07\x0e-\x1b\x80-\x9f]|!\\[",
                         below), below


def test_stored_is_what_the_stub_github_keeps_and_is_idempotent() -> None:
    sys_path = str(SCRIPTS)
    import importlib.util
    spec = importlib.util.spec_from_file_location("record_under_test", SCRIPTS / "record.py")
    rec = importlib.util.module_from_spec(spec)
    assert spec.loader and sys_path
    spec.loader.exec_module(rec)
    for t in ["(?<![a])", "a\u200bb\u202e", "!![[", "x !\u200b[y]", "<!--x-->", "!\u00ad[", "a\r\n\rb\x85", "\x01\x9e!["]:
        once = rec.stored(t)
        assert rec.stored(once) == once and "![" not in once and "\u200b" not in once and "\u202e" not in once
    assert rec.stored("<!--x--> a!b") == "<!--x--> a!b"  # GitHub keeps these as sent


def test_verdict_pass_posts_a_review_record(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    lines = c["body"].split("\n")
    assert lines[0] == "🤖 Review: pass (standard tier)"
    assert lines[1] == f"{REVIEW} sha={head} state=success tier=standard reviewed={head} depth=light -->"
    assert "correctness-reviewer" in c["body"] and "No findings." in c["body"] and "````text\n" in c["body"]


def test_verdict_fail_records_failure(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "sensitive", "--result", "fail", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head, "FAIL", BLOCKING))
    assert done.returncode == 0, done.stderr
    assert w.comments()[0]["body"].startswith(
        f"🤖 Review: fail (sensitive tier)\n{REVIEW} sha={head} state=failure tier=sensitive")


@pytest.mark.parametrize("verdict, state", [("PASS", "success"), ("FAIL", "failure")])
def test_verdict_takes_its_result_from_the_verifiers_verdict_line(w: World, tmp_path: Path, verdict: str,
                                                                   state: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head, verdict))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state={state} tier=standard" in w.comments()[0]["body"]


@pytest.mark.parametrize("result, verdict", [("pass", "FAIL"), ("fail", "PASS")])
def test_verdict_refuses_a_result_the_verifier_did_not_give(w: World, tmp_path: Path, result: str,
                                                            verdict: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--result", result, "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head, verdict))
    assert done.returncode == 2 and "contradicts the verifier" in done.stderr
    assert w.writes() == []


def test_verdict_refuses_output_that_reviewed_another_commit(w: World, tmp_path: Path) -> None:
    older = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    for text in (f"VERDICT: PASS {head}\nReviewed: {older}\n", f"VERDICT: PASS {older}\nReviewed: {head}\n"):
        (tmp_path / "out.txt").write_text(text)
        done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
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
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", str(tmp_path / "out.txt"))
    assert done.returncode == 2 and "VERDICT: PASS|FAIL" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_takes_an_abbreviated_sha_in_backticks(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    text = f"VERDICT: FAIL `{head[:12]}`\nReviewed: {head[:12]}\n{BLOCKING_LINE}\n{DISMISSED}\n\n{BLOCKING}"
    (tmp_path / "out.txt").write_text(text)
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", str(tmp_path / "out.txt"))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=failure" in w.comments()[0]["body"] and "mustfix=1" in w.comments()[0]["body"]


def test_verdict_reads_its_lines_past_a_nul_byte(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    top = f"VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{DISMISSED}\n\n## Nits\n- evidence: \x00"
    out = tmp_path / "out.txt"
    out.write_bytes(top.encode() + b"\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out),
                     LC_ALL="C.UTF-8")
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=success" in w.comments()[0]["body"]
    # A decoy after the NUL byte is read too, and refused: the whole stored text is checked.
    out.write_bytes(top.encode() + f"\nReviewed: {head}\n{BLOCKING_LINE}\n\n{BLOCKING}".encode())
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out),
                     LC_ALL="C.UTF-8")
    assert done.returncode == 2 and "more than one `Reviewed:`" in done.stderr and len(w.comments()) == 1, done.stderr


def test_verdict_accepts_a_seven_character_abbreviation(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    (tmp_path / "out.txt").write_text(f"VERDICT: PASS {head[:7]}\nReviewed: {head[:7]}\nBlocking: none\n{DISMISSED}\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
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
        done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", str(tmp_path / "out.txt"))
        assert done.returncode == 2 and f"names commit {sha}" in done.stderr, (sha, done.stderr)
    assert w.writes() == []


def test_verdict_refuses_a_tier_below_the_paths(w: World, tmp_path: Path) -> None:
    head = w.commit({".githooks/pre-commit": "x\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 2 and "make it sensitive" in done.stderr
    assert w.comments() == []
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 2 and w.comments() == []


def test_verdict_routine_on_routine_paths_needs_no_reviewer(w: World) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert body.startswith(f"🤖 Review: pass (routine tier)\n{REVIEW} sha={head} state=success "
                           f"tier=routine reviewed={head} depth=none -->")
    assert "needs gates only" in body and "<details>" not in body


def test_verdict_routine_carries_the_verdict_of_a_given_verifier_output(w: World, tmp_path: Path) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine", "--reviewed", head, "--file", review_file(tmp_path, head, "FAIL"))
    assert done.returncode == 0, done.stderr
    assert w.comments()[0]["body"].startswith(f"🤖 Review: fail (routine tier)\n{REVIEW} sha={head} state=failure ")


def routine_output(tmp: Path, text: str) -> str:
    p = tmp / "o.txt"
    p.write_text(text)
    return str(p)


@pytest.mark.parametrize("args, why", [
    (["--result", "pass", "--reviewed", "{head}"], "contradicts the verifier's VERDICT line"),
    (["--reviewed", "c" * 40], "but --reviewed is"),
    ([], "--reviewed is the full sha of the commit the verifier read"),  # the output's commit is never assumed
])
def test_verdict_routine_refuses_what_contradicts_a_given_verifier_output(w: World, tmp_path: Path, args: list[str],
                                                                         why: str) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    args = [x.format(head=head) for x in args]
    done = w.verdict("12", "--tier", "routine", *args, "--file", review_file(tmp_path, head, "FAIL"))
    assert done.returncode == 2 and why in done.stderr and w.comments() == [], done.stderr


@pytest.mark.parametrize("text, why", [
    ("", "must not be empty"),  # an output that came back empty is not "no file given"
    ("looked fine to me\n", "not finding-verifier's output"),
    ("VERDICT: PASS {h}\nReviewed: {e}\nBlocking: none\n{d}\n\nNo findings.\n", "names commit"),  # its Reviewed: line
    ("VERDICT: PASS {h}\nReviewed: {h}\n{b}\n{d}\n\n## Must-fix\n### COR-1\n", "lists 1 must-fix"),  # a PASS over a must-fix
    ("VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\n\nNo findings.\n", "no `Dismissals:"),  # its Dismissals line lost
    ("VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nDismissals: re-ran 0, promoted 3\n\nNo findings.\n", "promotes 3 of 0"),
])
def test_verdict_routine_applies_every_tier_s_output_checks_to_a_given_file(w: World, tmp_path: Path, text: str,
                                                                           why: str) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    out = routine_output(tmp_path, text.format(h=head, e="e" * 40, d=DISMISSED, b=BLOCKING_LINE))
    done = w.verdict("12", "--tier", "routine", "--reviewed", head, "--file", out)
    assert done.returncode == 2 and why in done.stderr and w.comments() == [], done.stderr


def test_verdict_allows_a_higher_tier(w: World, tmp_path: Path) -> None:
    head = w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "sensitive", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head))
    assert done.returncode == 0, done.stderr


def test_verdict_refuses_a_head_with_an_unreviewed_commit(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"src/app.py": "x = 3\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr
    assert w.comments() == []


def test_verdict_accepts_a_clean_merge_of_the_base(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    head = w.git(w.repo, "rev-parse", "HEAD")
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert f"sha={head} state=success tier=standard reviewed={reviewed} depth=light -->" in body
    assert "clean merges of main" in body


def test_verdict_refuses_a_merge_that_adds_changes(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-commit", "origin/main")
    (w.repo / "src/app.py").write_text("x = 'slipped in'\n")
    w.git(w.repo, "add", "-A")
    w.git(w.repo, "commit", "-qm", "merge main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_standard_needs_output_and_the_reviewed_commit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    assert w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head).returncode == 2
    assert w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--file", review_file(tmp_path, head)).returncode == 2
    assert w.writes() == []


def test_verdict_clips_output_to_the_comment_limit(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head, "PASS", "é" * 70000 + "\nEND\n"))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert len(body) <= 65536 and "Clipped to fit GitHub's comment size" in body and "END" not in body
    assert body.rstrip().endswith("</details>")


def test_verdict_read_back_mismatch_fails(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", head, "--file", review_file(tmp_path, head), STUB_MANGLE="1")
    assert done.returncode == 1 and "does not hold the body that was sent" in done.stderr


def test_verdict_dry_run_posts_nothing(w: World) -> None:
    w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine", "--dry-run")
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
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
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
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_refuses_more_than_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(21):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
                 "--reviewed", reviewed, "--file", review_file(tmp_path, reviewed))
    assert done.returncode == 2 and "nobody reviewed" in done.stderr


def test_verdict_accepts_twenty_merges(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    for i in range(20):
        w.main_moves({"README.md": f"main moved {i}\n"})
        w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
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
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", path)
    assert done.returncode == 2 and why in done.stderr, done.stderr
    assert w.writes() == []


@pytest.mark.parametrize("verdict, blocking, why", [
    ("FAIL", "Blocking: none", "lists no must-fix"),
    ("PASS", BLOCKING_LINE, "lists 1 must-fix"),
])
def test_verdict_refuses_a_blocking_line_that_contradicts_the_verdict(w: World, tmp_path: Path, verdict: str,
                                                                      blocking: str, why: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head, verdict, BLOCKING, blocking=blocking))
    assert done.returncode == 2 and why in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_takes_a_listed_id_only_from_a_heading_that_opens_with_it(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    for text in ("Settled in the brief: - COR-1: must-fix, fixed\n## Must-fix\n### COR-10\n- rank: must-fix\n",
                 "## Must-fix\n### CLM-2 (re-raises COR-1)\n- evidence: -> COR-1\n",
                 "## Must-fix\n### ###\n### PRE-COR-1, COR-1-2\n",
                 "## Must-fix\n## COR-1\n- rank: must-fix\n", "# COR-1\n"):  # a heading, but not a `###` one
        done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head, "FAIL", text, blocking=BLOCKING_LINE))
        assert done.returncode == 2 and "names COR-1, which no" in done.stderr, done.stderr


@pytest.mark.parametrize("text", [
    "## Must-fix\n```\n### COR-1\n```\n",  # in a top-level fence
    "## Must-fix\n- a\n  ```\n```\n### COR-1\n```\n",  # after a fence opened in a list item
    "## Must-fix\n<details>\n```\n### COR-1\n```\n</details>\n",  # in a fence inside an HTML block
    "## Must-fix\n````\n### COR-1\n",  # in a fence never closed
    "## Must-fix\n````text\n```\n### COR-1\n````\n",  # in a fence a shorter run does not close
    "## Must-fix\n~~~\n### COR-1\n~~~\n",  # in a tilde fence
])
def test_verdict_takes_a_listed_id_from_a_heading_fenced_or_not(w: World, tmp_path: Path, text: str) -> None:
    # No fence model decides the heading check, so no container can show or hide a heading to it differently from
    # GitHub: a heading quoted in a code block counts too, on a FAIL only.
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--dry-run",
                     "--file", review_file(tmp_path, head, "FAIL", text, blocking=BLOCKING_LINE))
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("blocking", [
    'Blocking: [{"ids": "LEAK-1", "harm": "leaks secrets"}]',  # two words name a harm
    'Blocking: [{"ids": "LEAK-1", "harm": "<details> clipping hides a leaked token from the owner"}]',
    'Blocking: [{"ids": "LEAK-1", "harm": "`<details>` clipping hides a token from `<owner>`"}]',  # not the slot
    'Blocking: `[{"ids": "LEAK-1", "harm": "leaks secrets"}]`',  # in backticks, as the sha lines may be
])
def test_verdict_accepts_a_named_harm_in_its_usual_shapes(w: World, tmp_path: Path, blocking: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL", "## Must-fix\n### LEAK-1\n- rank: must-fix\n",
                                       blocking=blocking))
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("decoy", ["quoted\x0c", "quoted\r", "\xa0", "\x1c", "\u2003", "quoted\u2028", "\x85"])
def test_verdict_refuses_a_reviewed_line_github_would_show_as_a_second_header(w: World, tmp_path: Path,
                                                                             decoy: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "out.txt"  # GitHub stores each of these as a line break or a blank: line 2 becomes a header
    p.write_bytes(f"VERDICT: PASS {head}\n{decoy}Reviewed: {head}\nBlocking: none\n"
                  f"Reviewed: {head}\n{BLOCKING_LINE}\n\n{BLOCKING}".encode())
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(p))
    assert done.returncode == 2 and "more than one `Reviewed:`" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_refuses_when_the_reader_prints_no_count(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    bad = tmp_path / "talking-python"
    bad.mkdir()
    (bad / "python3").write_text('#!/bin/sh\n[ "$2" = --header ] && { grep -m1 "^VERDICT:" "$3"; grep -m1 "^Reviewed:" "$3"; exit 0; }\necho many\n')
    (bad / "python3").chmod(0o755)
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL"), PATH=f"{bad}:{w.env['PATH']}")
    assert done.returncode == 2 and "printed no count" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_reads_only_the_blocking_line_not_the_prose(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    prose = ("## Must-fix\n### COR-1\n- rank: must-fix\n- harm: %s\n- evidence: ->\n```\n> Blocking: none\n"
             "### CLM-9\n- rank: must-fix\n```\n## Nits\n### CLM-2\n- rank: `must-fix`\n### CLM-3, GRD-1\n" % HARM)
    two = 'Blocking: [{"ids": "COR-1", "harm": "%s"}, {"ids": "CLM-3, GRD-1", "harm": "a lead merges a guard that stops nothing"}]' % HARM
    done = w.verdict("12", "--tier", "sensitive", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head, "FAIL", prose, blocking=two))
    assert done.returncode == 0, done.stderr
    assert f"state=failure tier=sensitive reviewed={head}" in w.comments()[0]["body"]


def test_verdict_refuses_when_it_cannot_read_the_blocking_line(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    bad = tmp_path / "failing-python"
    bad.mkdir()
    (bad / "python3").write_text('#!/bin/sh\n[ "$2" = --header ] && { grep -m1 "^VERDICT:" "$3"; grep -m1 "^Reviewed:" "$3"; exit 0; }\nexit 1\n')
    (bad / "python3").chmod(0o755)
    for verdict in ("PASS", "FAIL"):
        done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head, verdict), PATH=f"{bad}:{w.env['PATH']}")
        assert done.returncode == 2 and "refused" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_reads_the_reviewed_line_grep_reads_whatever_the_locale(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "out.txt"  # stored, the em-space is a blank, so both lines are headers whatever the locale
    p.write_text(f"VERDICT: PASS {head}\n\u2003Reviewed: {head}\n{BLOCKING_LINE}\n"
                 f"Reviewed: {'f' * 40}\nBlocking: none\n\n{BLOCKING}")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(p),
                 LC_ALL="C.UTF-8")
    assert done.returncode == 2 and "more than one" in done.stderr, done.stderr


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
    done = w.verdict("12", "--tier", "standard", *flat)
    assert done.returncode == 2 and message in done.stderr, done.stderr
    assert w.writes() == []


# The round line: the review path's version, the collection commit, and the round's cost and shape


ROUND = "<!-- loadout" + ":round "
KIT = r"(?:[0-9a-f]{40}(?:-dirty)?|none)"
sys_path_record = SCRIPTS / "record.py"


def skill_version() -> str:
    return subprocess.run(["python3", str(sys_path_record), "version"], capture_output=True, text=True,
                          check=True).stdout.strip()


def round_fields(body: str) -> list[tuple[str, str]]:
    line = body.split("\n")[2]
    assert line.startswith(ROUND) and line.endswith(" -->"), line
    return [tuple(kv.split("=", 1)) for kv in line[len(ROUND):-4].split()]  # type: ignore[misc]


def test_the_version_is_semver_in_the_skills_frontmatter() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", skill_version())
    front = (SCRIPTS.parent / "SKILL.md").read_text().split("---")[1]
    assert f"metadata:\n  version: {skill_version()}\n" in front


def test_verdict_puts_the_rounds_cost_and_shape_on_line_three(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", "correctness-reviewer, finding-verifier",
                     "--reviewed", head, "--file", review_file(tmp_path, head, "FAIL"), "--cycle", "2",
                     "--dupes", "3", "--nits", "4",
                     "--lens", "finding-verifier model=opus effort=high tokens=900 seconds=40 findings=2",
                     "--lens", "correctness-reviewer model=claude-opus-5-5 effort=medium tokens=41234 seconds=312 "
                               "findings=5", cost=False)
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    lines = body.split("\n")
    assert lines[1] == f"{REVIEW} sha={head} state=failure tier=standard reviewed={head} depth=light -->"
    f = round_fields(body)
    assert f[0] == ("v", skill_version()) and f[1][0] == "kit" and re.fullmatch(KIT, f[1][1])
    assert f[2:] == [("cycle", "2"), ("lenses", "correctness-reviewer,finding-verifier"), ("dupes", "3"),
                     ("mustfix", "1"), ("nits", "4"), ("dismissals", "0"), ("promoted", "0"),
                     ("lens", "correctness-reviewer:claude-opus-5-5:medium:41234:312:5"),
                     ("lens", "finding-verifier:opus:high:900:40:2"), ("depth", "light"), ("floor", "light"),
                     ("planned", "correctness-reviewer,finding-verifier")]
    assert "| correctness-reviewer | claude-opus-5-5 | medium | 41234 | 312 | 5 |" in body
    assert "| Total (summed) | | | 42134 | 352 | 7 |" in body
    assert "- Round: cycle 2; must-fix 1, nits 4, duplicates merged 3" in body


def test_verdict_takes_no_must_fix_count_from_the_lead(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head), "--mustfix", "0")
    assert done.returncode == 2 and w.writes() == []


GOOD_LENS = "x model=opus effort=high tokens=10 seconds=1 findings=0"


@pytest.mark.parametrize("args, why", [
    (["--cycle", "0", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS], "--cycle is a whole number from 1"),
    (["--cycle", "one", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS], "--cycle"),
    (["--dupes", "0", "--nits", "0", "--lens", GOOD_LENS], "--cycle"),
    (["--cycle", "1", "--dupes", "-1", "--nits", "0", "--lens", GOOD_LENS], "--dupes"),
    (["--cycle", "1", "--dupes", "0", "--nits", "1.5", "--lens", GOOD_LENS], "--nits"),
    (["--cycle", "1", "--dupes", "0", "--nits", "01", "--lens", GOOD_LENS], "--nits"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0"], "are not the --reviewers"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("high", "huge")], "effort="),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("=10", "=1e3")], "tokens="),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("=1 ", "=3.2 ")], "seconds="),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("=0", "=-1")], "findings="),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("opus", "op:us")], "model="),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace(" findings=0", "")], "once"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS + " findings=1"], "once"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS + " cost=9"], "once"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS, "--lens", GOOD_LENS], "twice"),
    (["--cycle", "1", "--dupes", "0", "--nits", "0", "--lens", GOOD_LENS.replace("x ", "y ")], "not the --reviewers"),
])
def test_verdict_refuses_a_malformed_or_missing_round_value(w: World, tmp_path: Path, args: list[str],
                                                            why: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head), *args, cost=False)
    assert done.returncode == 2 and why in done.stderr, done.stderr
    assert w.writes() == [] and not [c for c in calls(w) if c["method"] == "GET"]  # refused before any read


def calls(w: World) -> list[dict]:
    p = w.fx / "calls.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_verdict_refuses_a_reviewer_named_twice(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", "x, x", "--reviewed", head,
                     "--file", review_file(tmp_path, head), "--cycle", "1", "--dupes", "0", "--nits", "0",
                     "--lens", GOOD_LENS, cost=False)
    assert done.returncode == 2 and "names an agent twice" in done.stderr


@pytest.mark.parametrize("line, pairs", [
    ("Dismissals: re-ran 2, promoted 1", [("dismissals", "2"), ("promoted", "1")]),
    ("  Dismissals: re-ran 0, promoted 0  ", [("dismissals", "0"), ("promoted", "0")]),
    ("Dismissals: re-ran 3, promoted 3", [("dismissals", "3"), ("promoted", "3")]),
    # a settled record's line, quoted ahead of the verifier's own, is not read as a second one
    ("> Dismissals: re-ran 5, promoted 2\nDismissals: re-ran 1, promoted 0", [("dismissals", "1"), ("promoted", "0")]),
])
def test_verdict_adds_the_verifiers_dismissals(w: World, tmp_path: Path, line: str, pairs: list) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{line}\n\nNo findings.\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 0, done.stderr
    f = round_fields(w.comments()[0]["body"])
    assert [kv for kv in f if kv[0] in ("dismissals", "promoted")] == pairs


@pytest.mark.parametrize("header, why", [
    ("", "has no `Dismissals:"),  # none in the header
    ("Dismissals: re-ran 0, promoted 7\n", "cannot exceed re-ran"),  # more promoted than re-ran
    ("Dismissals: re-ran 9, promoted 9\nDismissals: re-ran 0, promoted 0\n", "holds 2 Dismissals lines"),
    ("Dismissals: re-ran 1, promoted 0\nDismissals: re-ran 1, promoted 0\n", "holds 2 Dismissals lines"),  # same twice
    ("```\nDismissals: re-ran 1, promoted 0\n```\n", "has no `Dismissals:"),  # only in a fence
])
def test_verdict_refuses_a_missing_repeated_or_impossible_dismissals_line(w: World, tmp_path: Path, header: str,
                                                                         why: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{header}\n## Nits\n"
                   "- evidence: Dismissals: re-ran 1, promoted 0\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 2 and why in done.stderr and w.writes() == [], done.stderr


@pytest.mark.parametrize("line", ["Dismissals: re-ran two, promoted 1", "Dismissals: none", "Dismissals: re-ran 2"])
def test_verdict_refuses_a_malformed_dismissals_line(w: World, tmp_path: Path, line: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"  # the malformed line is the header's only one, so its own refusal must fire
    out.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{line}\n\nNo findings.\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 2 and "Dismissals line is not `Dismissals: re-ran" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_routine_carries_the_version_kit_and_depth_only(w: World) -> None:
    w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 0, done.stderr
    f = round_fields(w.comments()[0]["body"])
    assert [k for k, _ in f] == ["v", "kit", "depth", "floor", "planned"] and f[0][1] == skill_version()
    assert f[2:] == [("depth", "none"), ("floor", "none"), ("planned", "none")]


def as_the_collection(w: World) -> None:
    """Make `main` a clone of this collection as far as the version check reads it."""
    files = {"bin/check-review-version": (REPO_ROOT / "bin/check-review-version").read_text(),
             "skills/review/scripts/record.py": (SCRIPTS / "record.py").read_text(),
             "skills/review/SKILL.md": "---\nname: review\nmetadata:\n  version: 1.0.0\n---\n"}
    for name, text in files.items():
        (w.seed / name).parent.mkdir(parents=True, exist_ok=True)
        (w.seed / name).write_text(text)
    w.git(w.seed, "add", "-A")
    w.git(w.seed, "commit", "-qm", "the collection")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "merge", "-q", "origin/main")


def test_verdict_refuses_an_unbumped_review_path_change_in_the_collection(w: World) -> None:
    as_the_collection(w)
    w.commit({"skills/review/notes.md": "x\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 2 and "version check refuses" in done.stderr and w.writes() == [], done.stderr


@pytest.mark.parametrize("checker", [None, "#!/usr/bin/env python3\nraise SystemExit(0)\n"])
def test_verdict_runs_the_default_branch_s_version_check_whatever_the_head_does_to_it(w: World, tmp_path: Path,
                                                                                    checker: str | None) -> None:
    as_the_collection(w)
    w.commit({"skills/review/notes.md": "x\n"})  # unbumped, and the head deletes or disarms the checker
    if checker is None:
        w.git(w.repo, "rm", "-q", "bin/check-review-version")
        w.git(w.repo, "commit", "-qm", "drop the checker")
        w.push()
    else:
        w.commit({"bin/check-review-version": checker})
    head = w.git(w.repo, "rev-parse", "HEAD")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head))
    assert done.returncode == 2 and "version check refuses" in done.stderr and w.writes() == [], done.stderr


def test_verdict_in_the_collection_passes_a_change_off_the_review_path(w: World) -> None:
    as_the_collection(w)
    w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 0, done.stderr


def test_verdict_routine_takes_no_round_arguments(w: World) -> None:
    w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine", "--lens", GOOD_LENS)
    assert done.returncode == 2 and "takes no --cycle" in done.stderr and w.writes() == []


def test_gate_stamp_puts_the_version_kit_and_wall_time_on_line_three(w: World) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--", "bash", "-c", "sleep 1.2; echo ok")
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert body.split("\n")[1] == f"{GATES} sha={head} state=success -->"
    f = round_fields(body)
    assert [k for k, _ in f] == ["v", "kit", "seconds"] and f[0][1] == skill_version()
    assert re.fullmatch(KIT, f[1][1]) and 1 <= int(f[2][1]) <= 3 and f"- Took: {f[2][1]} s" in body


def test_gate_stamp_dry_run_shows_the_round_line(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.run("gate_stamp.sh", "--dry-run", "--", "true")
    assert done.returncode == 0 and ROUND + f"v={skill_version()} kit=" in done.stderr


# record.py on its own


def build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(sys_path_record), "build", "--kind", "gates", "--sha", "a" * 40,
                           "--state", "success", "--title", "t", *args], capture_output=True, text=True)


@pytest.mark.parametrize("pair, why", [
    ("v=9.9.9", "scripts' own"), ("kit=abc", "scripts' own"), ("Seconds=1", "lowercase key"),
    ("seconds=1 2", "a value of letters"), ("seconds=", "a value of letters"), ("seconds", "<key>=<value>"),
    ("note=a-->b", "a value of letters"),
])
def test_record_refuses_a_round_pair_out_of_shape(pair: str, why: str) -> None:
    done = build("--round", pair)
    assert done.returncode != 0 and why in done.stderr, done.stderr


def test_record_lets_only_lens_repeat() -> None:
    assert build("--round", "lens=a:opus:high:1:1:0", "--round", "lens=b:opus:high:1:1:0").returncode == 0
    done = build("--round", "seconds=1", "--round", "seconds=2")
    assert done.returncode != 0 and "appears twice: seconds" in done.stderr


def _record_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("review_record", sys_path_record)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("text, want", [
    ("---\nname: r\nmetadata:\n  version: 1.2.3\n---\nbody\n", "1.2.3"),
    ("---\nmetadata:\n  upstream: x\n  version: 10.0.0\nname: r\n---\n", "10.0.0"),
    ("---\nname: r\n---\nmetadata:\n  version: 1.2.3\n", None),  # outside the frontmatter
    ("---\nname: r\nversion: 1.2.3\n---\n", None),  # not under metadata
    ("---\nname: r\nother:\n  version: 1.2.3\n---\n", None),
    ("---\nmetadata:\n  version: 1.2\n---\n", None),
    ("---\nmetadata:\n  version: v1.2.3\n---\n", None),
    ("---\nmetadata:\n  version: 01.2.3\n---\n", None),
    ("---\nmetadata:\n  version: 1.2.3\n  version: 1.2.4\n---\n", None),
    ("---\nmetadata:\n  version: 1.2.3\n", None),  # never closed
    ("name: r\nmetadata:\n  version: 1.2.3\n", None),
    ("name: r\nmetadata:\n  version: 9.0.0\n---\n", None),  # a closing fence with no opening one
    ("---\nmetadata:\n  notes:\n    version: 9.0.0\n---\n", None),  # nested below metadata's own keys
    ("---\nmetadata:\n  upstream: x\n  notes:\n    version: 9.0.0\n  version: 1.0.1\n---\n", "1.0.1"),
    ("---\nmetadata:\n    version: 2.0.0\n---\n", "2.0.0"),  # any indentation, so long as it is the first
])
def test_skill_version_reads_only_the_frontmatters_metadata_version(text: str, want: str | None) -> None:
    rec = _record_module()
    if want is None:
        with pytest.raises(ValueError):
            rec.skill_version(text)
    else:
        assert rec.skill_version(text) == want


def test_kit_names_the_collection_clone_and_whether_its_review_files_changed(tmp_path: Path,
                                                                             env: dict[str, str]) -> None:
    rec = _record_module()
    assert rec.kit(tmp_path) == "none"  # not a checkout
    clone = tmp_path / "collection"
    scripts = clone / "skills/review/scripts"
    scripts.mkdir(parents=True)
    for rel in ("skills/review/scripts/a.sh", "agents/lens.md", "cloud/hooks/guard.py", "README.md"):
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text("x\n")
    git = lambda *a: subprocess.run(["git", *a], cwd=clone, env=env, check=True, capture_output=True,  # noqa: E731
                                    text=True).stdout.strip()
    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-qm", "c")
    head = git("rev-parse", "HEAD")
    assert rec.kit(scripts) == head
    (clone / "README.md").write_text("changed\n")
    (clone / "agents/new.md").write_text("untracked\n")
    assert rec.kit(scripts) == head  # outside the watched paths, or untracked
    for rel in ("agents/lens.md", "cloud/hooks/guard.py", "skills/review/scripts/a.sh"):
        (clone / rel).write_text("changed\n")
        assert rec.kit(scripts) == head + "-dirty", rel
        git("checkout", "--", rel)
    other = tmp_path / "project"
    copied = other / ".claude/skills/review/scripts"
    copied.mkdir(parents=True)
    (copied / "a.sh").write_text("x\n")
    subprocess.run(["git", "init", "-q"], cwd=other, check=True)
    subprocess.run(["git", "add", "."], cwd=other, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=other, env=env, check=True, capture_output=True)
    assert rec.kit(copied) == "none"  # a copy inside the repo under review is not the collection


# Old bash: before 4.4, `set -u` makes an empty "${a[@]}" an unbound variable (macOS ships bash 3.2).

ARRAY_EXPANSION = re.compile(r'"\$\{(\w+)\[@\]\}"')


def test_every_array_expansion_survives_an_empty_array_on_old_bash() -> None:
    bare = []
    for name in NAMES:
        text = (SCRIPTS / name).read_text()
        for m in ARRAY_EXPANSION.finditer(text):
            guard = "${" + m.group(1) + "[@]+"
            if text[max(0, m.start() - len(guard)):m.start()] != guard:
                line = text.count("\n", 0, m.start()) + 1
                bare.append(f"{name}:{line}: {m.group(0)} (write ${{{m.group(1)}[@]+{m.group(0)}}})")
    assert not bare, "\n".join(bare)


BASH32_IMAGE = "mirror.gcr.io/library/bash:3.2"


@pytest.fixture(scope="module")
def bash32(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory whose `bash` is bash 3.2: $BASH32 when set, else copied out of a local bash:3.2 image (never
    pulled); skipped when neither is there."""
    d = tmp_path_factory.mktemp("bash32")
    if os.environ.get("BASH32"):
        (d / "bash").write_text(f'#!/bin/sh\nexec {os.environ["BASH32"]} "$@"\n')
    else:
        docker = shutil.which("docker")
        if not docker or subprocess.run([docker, "image", "inspect", BASH32_IMAGE], capture_output=True).returncode:
            pytest.skip(f"no bash 3.2: set BASH32, or `docker pull {BASH32_IMAGE}`")
        cid = subprocess.run([docker, "create", BASH32_IMAGE], capture_output=True, text=True,
                             check=True).stdout.strip()
        try:
            for src in ("/usr/local/bin/bash", "/lib/ld-musl-x86_64.so.1", "/usr/lib/libncursesw.so.6"):
                subprocess.run([docker, "cp", "-L", f"{cid}:{src}", str(d / ("bash.bin" if src.endswith("bash")
                                                                               else Path(src).name))], check=True)
        finally:
            subprocess.run([docker, "rm", cid], capture_output=True)
        (d / "bash").write_text(f'#!/bin/sh\nexec {d}/ld-musl-x86_64.so.1 --library-path {d} {d}/bash.bin "$@"\n')
    (d / "bash").chmod(0o755)
    got = subprocess.run([str(d / "bash"), "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"],
                         capture_output=True, text=True)
    if got.returncode or not got.stdout.startswith("3."):
        pytest.skip(f"the bash 3.2 found does not run here: {got.stderr.strip() or got.stdout.strip()}")
    return d


def test_the_scripts_run_on_bash_3_2(w: World, tmp_path: Path, bash32: Path) -> None:
    old = {"PATH": f"{bash32}:{w.env['PATH']}"}  # the scripts and the scripts they call all run on bash 3.2
    w.commit({"docs/a.md": "x\n"})
    for args in (["--tier", "routine"], ["--tier", "routine", "--dry-run"]):
        done = w.run("verdict.sh", "12", *args, **old)
        assert done.returncode == 0 and "unbound" not in done.stderr, done.stderr
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.run("verdict.sh", "12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head), "--cycle", "1", "--dupes", "0", "--nits", "0", **old)
    assert done.returncode == 2 and "are not the --reviewers" in done.stderr, done.stderr  # no --lens at all
    done = w.run("verdict.sh", "12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                 "--file", review_file(tmp_path, head), *round_args(PLANNED), **old)
    assert done.returncode == 0, done.stderr
    assert w.comments()[-1]["body"].split("\n")[2].startswith(ROUND + "v=")
    done = w.run("gate_stamp.sh", "--", "true", **old)
    assert done.returncode == 0 and "unbound" not in done.stderr, done.stderr


def test_record_review_round_without_reviewers_exits_2_with_the_reason() -> None:
    done = subprocess.run(["python3", str(sys_path_record), "review-round"], capture_output=True, text=True)
    assert done.returncode == 2 and "--reviewers is agent names" in done.stderr, done.stderr


@pytest.mark.parametrize("text", [
    "Lens heads:\n- correctness: x\nDismissals: none\n",  # after the header
    "## Must-fix\n### COR-1\n- evidence: the output said\nDismissals: re-ran two\n",  # quoted in a finding
    "```\nDismissals: none\n```\n## Must-fix\n",  # in a fence
])
def test_verdict_reads_dismissals_only_from_the_verifiers_header(w: World, tmp_path: Path, text: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head, text=text))
    assert done.returncode == 0, done.stderr
    f = dict(kv for kv in round_fields(w.comments()[0]["body"]) if kv[0] != "lens")
    assert (f.get("dismissals"), f.get("promoted")) == ("0", "0")  # the header's own line, not the quoted ones


def merged_head(w: World, tmp: Path | None = None) -> tuple[str, str]:
    """A reviewed commit (its round recorded when `tmp` is given), then a clean merge of main on top."""
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    if tmp is not None:
        done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", reviewed,
                         "--file", review_file(tmp, reviewed))
        assert done.returncode == 0, done.stderr
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    return reviewed, w.git(w.repo, "rev-parse", "HEAD")


def test_verdict_repost_after_a_clean_merge_records_no_usage(w: World, tmp_path: Path) -> None:
    reviewed, head = merged_head(w, tmp_path)
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", reviewed,
                     "--file", review_file(tmp_path, reviewed), "--repost", cost=False)
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1] == (f"{REVIEW} sha={head} state=success tier=standard reviewed={reviewed} "
                                   "depth=light -->")
    assert round_fields(body)[2:] == [("repost", "1"), ("lenses", "correctness-reviewer,finding-verifier"),
                                      ("mustfix", "0"), ("depth", "light"), ("floor", "light"),
                                      ("planned", "correctness-reviewer,finding-verifier")]
    assert "no reviewer ran" in body and "| Agent |" not in body


@pytest.mark.parametrize("extra, why", [
    (["--lens", GOOD_LENS], "takes no --cycle"), (["--cycle", "2"], "takes no --cycle"),
])
def test_verdict_repost_takes_no_usage(w: World, tmp_path: Path, extra: list[str], why: str) -> None:
    reviewed, _ = merged_head(w)
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", reviewed,
                     "--file", review_file(tmp_path, reviewed), "--repost", *extra, cost=False)
    assert done.returncode == 2 and why in done.stderr and w.writes() == []


def test_verdict_repost_is_refused_on_the_reviewed_commit_itself(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    assert w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head)).returncode == 0
    before = len(w.writes())
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head), "--repost", cost=False)
    assert done.returncode == 2 and "only by clean merges" in done.stderr and len(w.writes()) == before


def test_verdict_routine_takes_no_repost(w: World) -> None:
    w.commit({"docs/a.md": "x\n"})
    done = w.verdict("12", "--tier", "routine", "--repost")
    assert done.returncode == 2 and "--repost" in done.stderr and w.writes() == []


PATCHED = "- class: patched, not fixed (COR-1)\n"


def test_verdict_notices_a_finding_the_verifier_marks_patched_not_fixed(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    text = BLOCKING.replace("### COR-1", "### COR-2").replace("- harm:", PATCHED + "- harm:")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head, "FAIL", text, blocking=BLOCKING_LINE.replace("COR-1", "COR-2")))
    assert done.returncode == 0, done.stderr  # a notice, not a refusal: the record is posted
    assert "notice: the verifier marks COR-2 patched, not fixed" in done.stderr and "settled COR-1" in done.stderr
    assert "rethink" in done.stderr and len(w.comments()) == 1


@pytest.mark.parametrize("text", [
    BLOCKING,  # no marker
    BLOCKING + "```\n### COR-9\n" + PATCHED + "```\n",  # a marker inside a code fence is quoted, not the verifier's
    BLOCKING + "- class: patched (COR-1)\n",  # not the fixed shape
    BLOCKING + "- class: patched, not fixed (none)\n",  # a filler, not a finding id
    BLOCKING + "- class: patched, not fixed (-)\n",  # a filler, not a finding id
])
def test_verdict_prints_no_notice_without_the_marker(w: World, tmp_path: Path, text: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head, "FAIL", text))
    assert done.returncode == 0, done.stderr
    assert "notice:" not in done.stderr


@pytest.mark.parametrize("second", [
    "Reviewed: {head}\n" + BLOCKING_LINE,  # a decoy pair ahead of a must-fix: the first pair would pass it
    BLOCKING_LINE,
    "VERDICT: FAIL {head}",
])
def test_verdict_refuses_an_output_with_a_second_header_line(w: World, tmp_path: Path, second: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{DISMISSED}\n\n"
                   f"{second.replace('{head}', head)}\n\n{BLOCKING}")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 2 and "more than one" in done.stderr and w.writes() == [], done.stderr


# A decoy trio that would pass the record, and the verifier's real FAIL header with its must-fix.
DECOY = "VERDICT: PASS {head}\nReviewed: {head}\nBlocking: none"
REAL = "VERDICT: FAIL {head}\nReviewed: {head}\n%s\n%s" % (BLOCKING_LINE, DISMISSED)


@pytest.mark.parametrize("text", [
    f"```\n{DECOY}\n```\n\n{REAL}\n\n{BLOCKING}",  # above the header, in a fence
    f"```text\n{DECOY}\n```\n\n{REAL}\n\n{BLOCKING}",  # in a fence with an info string
    f"````\n```\n{DECOY}\n```\n````\n\n{REAL}\n\n{BLOCKING}",  # in a 4-backtick fence a 3-backtick line does not close
    f"````\nnote\n```\n{DECOY}\n````\n{REAL}\n\n{BLOCKING}",  # the same, read as closed by a reader that would
    f"~~~\n{DECOY}\n~~~\n{REAL}\n\n{BLOCKING}",  # a tilde fence
    f"intro\n\n{DECOY}\n\n{REAL}\n\n{BLOCKING}",  # under a first line that is not the header
    f"Summary: one must-fix.\n\n{REAL}\n\n{BLOCKING}",  # the only header, under a first line that is not it
    f"    {DECOY.replace(chr(10), chr(10) + '    ')}\n\n{REAL}\n\n{BLOCKING}",  # an indented code block
    f"{REAL}\n\n{BLOCKING}\n{DECOY}\n",  # below the header, unfenced
    f"{REAL}\n\n{BLOCKING}\n```\n{DECOY}\n```\n",  # below the header, in a fence
    f"{REAL}\n\n{BLOCKING}\n```text\n{DECOY}\n```\n",
    f"{REAL}\n\n{BLOCKING}\n````\n```\n{DECOY}\n```\n````\n",  # below, in a 4-backtick fence closed by 3
    f"{REAL}\n\n{BLOCKING}\n- evidence:\n  {DECOY.replace(chr(10), chr(10) + '  ')}\n",  # below, indented in a list
    f"{REAL}\n\n{BLOCKING}\n\t{DECOY.replace(chr(10), chr(10) + chr(9))}\n",  # below, indented by a tab
    f"{REAL}\n\n{BLOCKING}\n```\n   Blocking: none\n```\n",  # one line of it
])
def test_verdict_refuses_a_header_line_anywhere_but_the_top(w: World, tmp_path: Path, text: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(text.replace("{head}", head))
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 2 and ("outside its header" in done.stderr or "more than one" in done.stderr), done.stderr
    assert w.writes() == [], done.stderr


@pytest.mark.parametrize("quoted", [
    "> Reviewed: {head}\n> %s" % BLOCKING_LINE,  # quoted after `> `, as the verifier writes it
    "```\n> VERDICT: PASS {head}\n> Reviewed: {head}\n> Blocking: none\n```",  # the same inside a fence
    "- evidence:\n  > Reviewed: {head}\n  > Blocking: none",  # indented in a list
    "the output says Reviewed: {head} and Blocking: none mid-line",  # not at a line start
])
def test_verdict_takes_a_header_line_quoted_after_a_marker(w: World, tmp_path: Path, quoted: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(f"\n\nVERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n{DISMISSED}\n\n"
                   f"{quoted.replace('{head}', head)}\n")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 0, done.stderr
    assert f"{REVIEW} sha={head} state=success" in w.comments()[0]["body"]


def test_every_reader_reads_a_header_word_as_github_stores_it(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"  # a zero-width character GitHub drops, inside each header word
    out.write_text(f"VERD\u200bICT: FAIL {head}\nRevie\u200bwed: {head}\nBlock\u200bing: {BLOCKING_LINE[10:]}\n"
                   f"Dismiss\u200bals: re-ran 2, promoted 1\n\n{BLOCKING}")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    assert done.returncode == 0, done.stderr
    body = w.comments()[0]["body"]
    assert f"state=failure tier=standard reviewed={head}" in body and "mustfix=1" in body
    assert [kv for kv in round_fields(body) if kv[0] in ("dismissals", "promoted")] == [("dismissals", "2"),
                                                                                        ("promoted", "1")]


@pytest.mark.parametrize("lines, inside", [
    (["```", "x", "```"], [True, True, True]),
    (["````text", "```", "x", "````", "y"], [True, True, True, True, False]),  # a shorter run does not close
    (["```", "```python", "x", "```", "y"], [True, True, True, True, False]),  # an info string does not close
    (["~~~", "```", "x", "~~~", "y"], [True, True, True, True, False]),  # the other character does not close
    (["```", "x", "`````", "y"], [True, True, True, False]),  # a longer run closes
    (["    ```", "x"], [False, False]),  # indented four spaces: code, not a fence
    (["``` a`b", "x"], [False, False]),  # a backtick in a backtick fence's info string: no fence
])
def test_fenced_reads_a_fence_as_github_does(lines: list[str], inside: list[bool]) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("record_fence", SCRIPTS / "record.py")
    rec = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(rec)
    assert rec.fenced(lines) == inside


@pytest.mark.parametrize("body, kept", [
    ("a ![x] b", "a [x] b"),  # a `]` in the same paragraph: GitHub drops the `!`
    ("a !![x]", "a [x]"),
    ("a ![b\nc] d", "a [b\nc] d"),  # the `]` on the next line, same paragraph
    ("a ![b\n\nc]", "a ![b\n\nc]"),  # the `]` only after a blank line: kept
    ("a ![b", "a ![b"),  # no `]` at all: kept
])
def test_the_stub_drops_a_bang_before_a_bracket_only_within_its_paragraph(tmp_path: Path, body: str,
                                                                          kept: str) -> None:
    (tmp_path / "comments.json").write_text("[]")
    done = subprocess.run(["python3", str(SCRIPTS / "tests" / "stub_gh.py"), "api",
                           "repos/example-owner/example-repo/issues/1/comments", "-f", f"body={body}"],
                          capture_output=True, text=True, env={**os.environ, "STUB_DIR": str(tmp_path)})
    assert done.returncode == 0, done.stderr
    assert json.loads((tmp_path / "comments.json").read_text())[0]["body"] == kept


def test_verdict_puts_the_guard_s_refusals_on_the_record_once(w: World, tmp_path: Path) -> None:
    log = tmp_path / "refusals.log"
    log.write_text("2030-01-01T00:00Z some-plugin:correctness-reviewer: a live `gcloud` call\n")
    head = w.commit({"src/app.py": "x = 2\n"})
    args = ("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED,
            "--reviewed", head, "--file", review_file(tmp_path, head))
    dry = w.verdict(*args, "--dry-run", LOADOUT_GUARD_REFUSALS=str(log))
    assert dry.returncode == 0 and log.exists(), dry.stderr  # a dry run keeps the log for the real post
    done = w.verdict(*args, LOADOUT_GUARD_REFUSALS=str(log))
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    assert "- Guard refusals of review agents' commands on this machine since its last record: 1\n" in c["body"]
    assert "  - 2030-01-01T00:00Z some-plugin:correctness-reviewer: a live `gcloud` call" in c["body"]
    assert not log.exists()  # taken: the next round's record starts from none
    again = w.verdict(*args, LOADOUT_GUARD_REFUSALS=str(log))
    assert again.returncode == 0 and "Guard refusals" not in w.comments()[-1]["body"]


def test_verdict_puts_the_refusals_back_when_its_post_fails(w: World, tmp_path: Path) -> None:
    log = tmp_path / "refusals.log"
    log.write_text("2030-01-01T00:00Z some-plugin:correctness-reviewer: a command naming `bq`\n")
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "standard", "--result", "pass", "--reviewers", PLANNED, "--reviewed", head,
                     "--file", review_file(tmp_path, head), LOADOUT_GUARD_REFUSALS=str(log), STUB_FAIL="1")
    assert done.returncode != 0
    assert "a command naming `bq`" in log.read_text() and len(list(tmp_path.glob("refusals.log.*"))) == 0

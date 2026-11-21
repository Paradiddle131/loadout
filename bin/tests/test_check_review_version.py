"""bin/check-review-version against throwaway repos: a change to the review path needs a higher version."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-review-version"
ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
SKILL = "skills/review/SKILL.md"


def skill(version: str | None) -> str:
    meta = f"metadata:\n  version: {version}\n" if version is not None else ""
    return f"---\nname: review\ndescription: x\n{meta}---\n\n# Review\n"


class Repo:
    """A bare `origin` with `main`, and a clone on branch `change`."""

    def __init__(self, tmp: Path, base_version: str | None = "1.1.0") -> None:
        self.env = {**os.environ, **ID, "HOME": str(tmp / "home")}
        remote = tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
        self.dir = tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(remote), str(self.dir)], check=True, capture_output=True)
        self.git("switch", "-q", "-c", "main")
        self.write({SKILL: skill(base_version), "skills/review/scripts/verdict.sh": "v1\n", "agents/lens.md": "a\n",
                    "cloud/hooks/merge-guard.py": "g\n", "cloud/hooks/other.py": "o\n", "README.md": "r\n"})
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("push", "-q", "origin", "main")
        self.git("remote", "set-head", "origin", "main")
        self.git("switch", "-q", "-c", "change")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.dir, env=self.env, check=True, capture_output=True,
                              text=True).stdout

    def write(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            p = self.dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    def stage(self, files: dict[str, str]) -> None:
        self.write(files)
        self.git("add", "-A")

    def check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(SCRIPT), *args], cwd=self.dir, env=self.env, capture_output=True,
                              text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


@pytest.mark.parametrize("path", ["agents/lens.md", "agents/new-lens.md", "skills/review/scripts/verdict.sh",
                                  "skills/review/templates.md", "cloud/hooks/merge-guard.py"])
def test_a_change_to_the_review_path_without_a_bump_fails(repo: Repo, path: str) -> None:
    repo.stage({path: "changed\n"})
    done = repo.check()
    assert done.returncode == 1 and "not above 1.1.0" in done.stderr and path in done.stderr, done.stderr


@pytest.mark.parametrize("version", ["1.1.1", "1.2.0", "2.0.0"])
def test_a_change_with_a_higher_version_passes(repo: Repo, version: str) -> None:
    repo.stage({"agents/lens.md": "changed\n", SKILL: skill(version)})
    done = repo.check()
    assert done.returncode == 0, done.stderr
    assert f"1.1.0 -> {version}" in done.stdout


@pytest.mark.parametrize("version", ["1.1.0", "1.0.9", "0.9.0"])
def test_an_equal_or_lower_version_fails(repo: Repo, version: str) -> None:
    repo.stage({"agents/lens.md": "changed\n", SKILL: skill(version)})
    assert repo.check().returncode == 1


@pytest.mark.parametrize("text", [
    skill("1.2"), skill("v1.2.0"), skill("1.2.0-rc1"), skill("01.2.0"), skill(None),
    "---\nname: review\n---\nmetadata:\n  version: 9.0.0\n",  # moved below the frontmatter
    "---\nname: review\nversion: 9.0.0\n---\n",  # not under metadata
    "# no frontmatter\nmetadata:\n  version: 9.0.0\n",
    skill("9.0.0").replace("  version: 9.0.0\n", "  version: 9.0.0\n  version: 9.1.0\n"),
])
def test_a_malformed_missing_or_moved_version_fails(repo: Repo, text: str) -> None:
    repo.stage({"agents/lens.md": "changed\n", SKILL: text})
    done = repo.check()
    assert done.returncode == 1 and ("metadata.version" in done.stderr or "frontmatter" in done.stderr), done.stderr


def test_a_malformed_version_fails_even_when_nothing_else_changed(repo: Repo) -> None:
    repo.stage({"README.md": "changed\n"})
    assert repo.check().returncode == 0
    repo.write({SKILL: skill("bad")})
    repo.git("add", "-A")
    assert repo.check().returncode == 1


def test_a_deleted_skill_file_fails(repo: Repo) -> None:
    repo.git("rm", "-q", SKILL)
    done = repo.check()
    assert done.returncode == 1 and "missing" in done.stderr


def test_a_rename_out_of_the_review_path_counts_its_old_path(repo: Repo) -> None:
    (repo.dir / "docs").mkdir()
    repo.git("mv", "agents/lens.md", "docs/lens.md")
    done = repo.check()
    assert done.returncode == 1 and "agents/lens.md" in done.stderr, done.stderr


def test_a_change_outside_the_review_path_needs_no_bump(repo: Repo) -> None:
    repo.stage({"README.md": "changed\n", "cloud/hooks/other.py": "changed\n", "skills/other/SKILL.md": "x\n"})
    done = repo.check()
    assert done.returncode == 0 and "unchanged" in done.stdout, done.stderr


def test_a_base_without_a_version_counts_as_one_zero_zero(tmp_path: Path) -> None:
    r = Repo(tmp_path, base_version=None)
    r.stage({"agents/lens.md": "changed\n", SKILL: skill("1.0.0")})
    assert r.check().returncode == 1
    r.stage({SKILL: skill("1.0.1")})
    done = r.check()
    assert done.returncode == 0 and "1.0.0 -> 1.0.1" in done.stdout, done.stderr


def test_head_mode_reads_the_commit_not_the_index(repo: Repo) -> None:
    repo.stage({"agents/lens.md": "changed\n"})
    repo.git("commit", "-qm", "no bump")
    repo.stage({SKILL: skill("1.2.0")})  # staged after the commit: the commit itself has no bump
    assert repo.check("--head", "HEAD").returncode == 1
    assert repo.check().returncode == 0


def test_the_bump_is_measured_from_the_merge_base_not_the_moved_default_branch(repo: Repo) -> None:
    repo.stage({"agents/lens.md": "changed\n", SKILL: skill("1.2.0")})
    repo.git("commit", "-qm", "bump")
    repo.git("switch", "-q", "main")
    repo.stage({SKILL: skill("1.3.0")})
    repo.git("commit", "-qm", "main moves on")
    repo.git("push", "-q", "origin", "main")
    repo.git("switch", "-q", "change")
    repo.git("fetch", "-q", "origin")
    assert repo.check("--head", "HEAD").returncode == 0


def test_no_default_branch_is_an_error_not_a_pass(tmp_path: Path) -> None:
    d = tmp_path / "lone"
    d.mkdir()
    env = {**os.environ, **ID}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c"], cwd=d, env=env, check=True)
    done = subprocess.run(["python3", str(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
    assert done.returncode == 2 and "NOT checked" in done.stderr

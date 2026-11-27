"""bin/check-generic.sh: runs on bash 3.2 with nothing to add, and counts no worktree of this repo as a sibling.

Run: uvx --from pytest==8.4.2 pytest -q bin/tests
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-generic.sh"
FAKE_GIT = """#!/bin/sh
case "$1 $2" in
  "remote get-url") exit 2 ;;
  "rev-parse --git-common-dir") echo .git ;;
  "ls-files ") printf 'a.md\\n' ;;
esac
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def repo(path: Path, origin: str) -> Path:
    (path / "bin").mkdir(parents=True)
    shutil.copy(SCRIPT, path / "bin/check-generic.sh")
    (path / "a.md").write_text("see /example-repo/x\n")
    git(path, "init", "-q", "-b", "main")
    git(path, "remote", "add", "origin", f"https://github.com/example-owner/{origin}.git")
    git(path, "add", ".")
    git(path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return path


def run(cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "bin/check-generic.sh"], cwd=cwd, capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
    )


def test_a_worktree_named_otherwise_does_not_count_its_main_clone(tmp_path: Path) -> None:
    main = repo(tmp_path / "example-repo", "example-repo")
    git(main, "worktree", "add", "-q", str(tmp_path / "wt-elsewhere"))
    done = run(tmp_path / "wt-elsewhere", tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_real_sibling_still_fails(tmp_path: Path) -> None:
    repo(tmp_path / "example-repo", "example-repo")
    other = repo(tmp_path / "other", "other")
    (other / "a.md").write_text("see /example-repo/x\n")
    done = run(other, tmp_path)
    assert done.returncode == 1 and "a.md:1:" in done.stdout


@pytest.mark.skipif(not shutil.which("docker"), reason="no docker for bash 3.2")
def test_it_runs_on_bash_3_2_with_no_owner_deny_file_or_sibling(tmp_path: Path) -> None:
    work = tmp_path / "w"
    (work / "bin").mkdir(parents=True)
    (work / ".git").mkdir()
    shutil.copy(SCRIPT, work / "bin/check-generic.sh")
    (work / "a.md").write_text("plain text\n")
    (tmp_path / "shim").mkdir()
    (tmp_path / "shim/git").write_text(FAKE_GIT)
    (tmp_path / "shim/git").chmod(0o755)
    done = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{tmp_path}:/t", "-w", "/t/w", "-e", "PATH=/t/shim:/usr/local/bin:/usr/bin:/bin",
         "-e", "HOME=/t", "mirror.gcr.io/library/bash:3.2", "bash", "bin/check-generic.sh"],
        capture_output=True, text=True, check=False, timeout=300,
    )
    if "Unable to find image" in done.stderr and done.returncode != 0:
        pytest.skip("bash 3.2 image not available")
    assert done.returncode == 0, done.stderr
    assert "1 files, 0 owner-specific words, none found" in done.stdout


def test_another_worktree_of_this_repo_is_no_sibling(tmp_path: Path) -> None:
    main = repo(tmp_path / "example-repo", "example-repo")
    git(main, "worktree", "add", "-q", str(tmp_path / "wt-a"))
    git(main, "worktree", "add", "-q", "-b", "b", str(tmp_path / "wt-b"))
    (tmp_path / "wt-a/a.md").write_text("see /wt-b/x\n")
    git(tmp_path / "wt-a", "add", "a.md")
    done = run(tmp_path / "wt-a", tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_clone_named_otherwise_does_not_count_a_folder_of_its_origin_name(tmp_path: Path) -> None:
    repo(tmp_path / "example-repo", "example-repo")  # an unrelated clone of the same origin name
    elsewhere = repo(tmp_path / "renamed", "example-repo")
    done = run(elsewhere, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


def test_no_files_to_check_passes(tmp_path: Path) -> None:
    (tmp_path / "r/bin").mkdir(parents=True)
    shutil.copy(SCRIPT, tmp_path / "r/bin/check-generic.sh")
    git(tmp_path / "r", "init", "-q", "-b", "main")
    done = run(tmp_path / "r", tmp_path)
    assert (done.returncode, done.stdout.strip()) == (0, "check-generic: no files to check")

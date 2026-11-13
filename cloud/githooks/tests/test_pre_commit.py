"""The other clones' pre-commit (cloud/githooks/pre-commit): its gitleaks scan of what is staged.

Run: uvx --from pytest==8.4.2 pytest -q cloud/githooks/tests
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "pre-commit"
ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def commit(tmp_path: Path, gitleaks_code: int | None) -> subprocess.CompletedProcess[str]:
    r = tmp_path / "repo"
    r.mkdir()
    env = {**os.environ, **ID, "HOME": str(tmp_path / "home")}
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if gitleaks_code is not None:
        (bin_dir / "gitleaks").write_text(f"#!/bin/sh\necho \"gitleaks $*\" >&2\nexit {gitleaks_code}\n")
        (bin_dir / "gitleaks").chmod(0o755)
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    for args in (["init", "-q"], ["remote", "add", "origin", "https://github.com/example-owner/example-repo.git"],
                 ["config", "core.hooksPath", str(HOOK.parent)]):
        subprocess.run(["git", *args], cwd=r, check=True, env=env)
    (r / "a.txt").write_text("plain text\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True, env=env)
    return subprocess.run(["git", "commit", "-qm", "x"], cwd=r, env=env, capture_output=True, text=True)


def test_a_gitleaks_finding_refuses_the_commit(tmp_path: Path) -> None:
    done = commit(tmp_path, 1)
    assert done.returncode != 0
    assert "gitleaks protect --staged" in done.stderr


def test_a_clean_scan_lets_the_commit_through(tmp_path: Path) -> None:
    assert commit(tmp_path, 0).returncode == 0


def test_without_gitleaks_the_commit_passes_and_says_so(tmp_path: Path) -> None:
    done = commit(tmp_path, None)
    assert done.returncode == 0
    assert "NOT scanned for secrets" in done.stderr

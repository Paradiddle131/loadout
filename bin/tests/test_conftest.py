"""The root conftest drops inherited repository-local git variables, so no test's git command reaches another repo."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_root_conftest_drops_repository_local_git_variables_and_keeps_identity(tmp_path: Path) -> None:
    env = {**os.environ, "GIT_DIR": str(tmp_path / "elsewhere.git"), "GIT_INDEX_FILE": str(tmp_path / "index"),
           "GIT_WORK_TREE": str(tmp_path), "GIT_AUTHOR_NAME": "kept"}
    probe = ("import os, runpy; runpy.run_path(%r); "
             "print([k for k in ('GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE') if k in os.environ], "
             "os.environ.get('GIT_AUTHOR_NAME'))" % str(ROOT / "conftest.py"))
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[] kept"


def test_a_suite_started_from_its_own_directory_loads_the_root_conftest(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign-index"
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "test_hook_runs_listed_checks.py::test_the_pre_commit_hook_runs_every_listed_check"],
                          cwd=ROOT / "bin" / "tests", capture_output=True, text=True,
                          env={**os.environ, "GIT_INDEX_FILE": str(foreign)})
    assert done.returncode == 0, done.stdout + done.stderr
    assert not foreign.exists()  # no stub was staged in another index

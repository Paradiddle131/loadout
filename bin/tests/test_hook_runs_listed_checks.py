"""The pre-commit hook runs every check AGENTS.md's `## Checks` lists: the hook is run with each check replaced by a stub
that logs its call, so a hook line that no longer runs a check (deleted, guarded off, echoed) turns this red."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".githooks/pre-commit"


def listed_checks() -> list[str]:
    """The first word of each bullet's backticked command under `## Checks`, before `Tests:`."""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = text.split("## Checks", 1)[1].split("\nTests:", 1)[0]
    return [m.group(1).split()[0] for m in re.finditer(r"^- `([^`]+)`", section, re.M)]


def test_agents_md_lists_the_checks() -> None:
    assert listed_checks() == ["bin/check-plugins.sh", "bin/check-refs", "bin/check-review-version", "gitleaks",
                               "bin/check-generic.sh", "cloud/githooks/check-process-ids.py"]


def run_hook(tmp: Path, hook_text: str) -> list[str]:
    """Run `hook_text` as the pre-commit hook of a scratch repo whose checks are logging stubs; the checks it ran."""
    repo, log, path_dir = tmp / "repo", tmp / "calls.log", tmp / "path"
    repo.mkdir(parents=True)
    path_dir.mkdir()
    env = {**os.environ, "HOME": str(tmp / "home"), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "PATH": f"{path_dir}:{os.environ['PATH']}"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env)
    for check in listed_checks():
        if check == "gitleaks":
            stub = path_dir / "gitleaks"  # found by the hook's `command -v gitleaks`
        else:
            stub = repo / check
            stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(f"#!/usr/bin/env python3\nopen({str(log)!r}, 'a').write({check!r} + '\\n')\n"
                        if check.endswith(".py") else f"#!/usr/bin/env bash\necho {check} >> '{log}'\n")
        stub.chmod(0o755)
    (repo / "notes.md").write_text("x\n")  # a staged file outside tests/, so the generic check has work
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    hook = repo / "pre-commit"
    hook.write_text(hook_text)
    done = subprocess.run(["bash", str(hook)], cwd=repo, capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    return log.read_text().split() if log.exists() else []


def test_the_pre_commit_hook_runs_every_listed_check(tmp_path: Path) -> None:
    assert shutil.which("git")
    assert sorted(run_hook(tmp_path, HOOK.read_text(encoding="utf-8"))) == sorted(listed_checks())

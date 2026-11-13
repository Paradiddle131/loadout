"""save-work.sh's secret scan and session-start.sh's GCP opt-out, in throwaway trees.

Run: uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests
"""

from __future__ import annotations

import os
import secrets
import shutil
import string
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
UVX = shutil.which("uvx")
GITLEAKS = shutil.which("gitleaks") or (str(Path.home() / ".local/bin/gitleaks")
                                        if (Path.home() / ".local/bin/gitleaks").exists() else None)
SHELLCHECK_PY_VERSION = "0.11.0.1"
ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, **ID}).stdout.strip()


def test_hook_scripts_parse() -> None:
    for name in ("save-work.sh", "session-start.sh"):
        subprocess.run(["bash", "-n", str(HOOKS / name)], check=True)


@pytest.mark.skipif(UVX is None, reason="uvx not installed")
def test_hook_scripts_shellcheck_clean() -> None:
    assert UVX
    done = subprocess.run(
        [UVX, "--from", f"shellcheck-py=={SHELLCHECK_PY_VERSION}", "shellcheck", "-S", "warning",
         str(HOOKS / "save-work.sh"), str(HOOKS / "session-start.sh")],
        capture_output=True, text=True, timeout=240,
    )
    assert done.returncode == 0, done.stdout + done.stderr


# save-work.sh


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    roots = tmp_path / "roots"
    r = roots / "work"
    r.mkdir(parents=True)
    git(r, "init", "-q", "-b", "feature")
    git(r, "remote", "add", "origin", str(remote))
    (r / "a.txt").write_text("a\n")
    git(r, "add", ".")
    git(r, "commit", "-qm", "init")
    git(r, "push", "-q", "origin", "feature")
    return r


def save(clone: Path, tmp_path: Path, gitleaks: str | None) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if gitleaks:
        (bin_dir / "gitleaks").unlink(missing_ok=True)
        (bin_dir / "gitleaks").symlink_to(gitleaks)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, **ID, "HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin",
           "SAVE_WORK_ROOTS": str(clone.parent), "CLAUDE_CODE_SESSION_ID": "sess1234"}
    return subprocess.run(["bash", str(HOOKS / "save-work.sh"), "--now"], env=env, capture_output=True,
                          text=True, timeout=120, stdin=subprocess.DEVNULL)


def wip_refs(clone: Path) -> str:
    return git(clone, "ls-remote", "origin", "refs/heads/claude/wip/*")


def fake_gitleaks(tmp_path: Path, code: int) -> str:
    p = tmp_path / f"fake-gitleaks-{code}"
    p.write_text(f"#!/bin/sh\necho 'Finding: REDACTED'\nexit {code}\n")
    p.chmod(0o755)
    return str(p)


def test_save_work_pushes_clean_work(clone: Path, tmp_path: Path) -> None:
    (clone / "a.txt").write_text("changed\n")
    done = save(clone, tmp_path, fake_gitleaks(tmp_path, 0))
    assert done.returncode == 0
    assert "claude/wip/feature-sess1234" in wip_refs(clone)


@pytest.mark.parametrize("code", [3, 1])
def test_save_work_skips_the_push_on_a_finding_or_a_failed_scan(clone: Path, tmp_path: Path,
                                                                code: int) -> None:
    (clone / "a.txt").write_text("changed\n")
    done = save(clone, tmp_path, fake_gitleaks(tmp_path, code))
    assert done.returncode == 0
    assert wip_refs(clone) == ""
    assert "SKIPPED" in done.stderr
    assert "SKIPPED" in (tmp_path / "home/.claude/save-work.log").read_text()


@pytest.mark.skipif(GITLEAKS is None, reason="gitleaks not installed")
def test_save_work_real_scan_finds_a_planted_token(clone: Path, tmp_path: Path) -> None:
    assert GITLEAKS
    # Built at run time, so no secret sits in this file; random, so it has a real token's entropy.
    token = "ghp_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(36))
    (clone / "config.txt").write_text(f"token = {token}\n")
    done = save(clone, tmp_path, GITLEAKS)
    assert wip_refs(clone) == "", done.stderr
    assert "gitleaks found a secret" in done.stderr
    assert token not in (tmp_path / "home/.claude/save-work.log").read_text()
    (clone / "config.txt").write_text("nothing here\n")
    save(clone, tmp_path, GITLEAKS)
    assert "claude/wip/feature-sess1234" in wip_refs(clone)


# session-start.sh


@pytest.fixture
def tree(tmp_path: Path) -> dict[str, Path]:
    """A collection clone with stubbed neighbours, a target clone, and a HOME naming it."""
    root = tmp_path / "loadout"
    (root / "cloud/hooks").mkdir(parents=True)
    (root / "cloud/gcp").mkdir()
    shutil.copy(HOOKS / "session-start.sh", root / "cloud/hooks/session-start.sh")
    (root / "cloud/memory.sh").write_text("exit 0\n")
    (root / "cloud/setup.sh").write_text("exit 0\n")
    (root / "cloud/plugins.txt").write_text("")
    (root / "cloud/gcp/status.sh").write_text("echo GCP-STATUS-RAN\n")
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init", "-q")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/cloud-target").write_text(str(target) + "\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text("#!/bin/sh\nexit 0\n")  # `docker info` answers: dockerd is left alone
    (bin_dir / "docker").chmod(0o755)
    return {"root": root, "target": target, "home": home, "bin": bin_dir}


def start(tree: dict[str, Path], **env: str) -> str:
    e = {k: v for k, v in os.environ.items() if k not in ("GCP_PROJECT", "CLAUDE_ENV_FILE")}
    e.update({"HOME": str(tree["home"]), "PATH": f"{tree['bin']}:/usr/bin:/bin",
              "CLAUDE_PROJECT_DIR": str(tree["target"]), **env})
    done = subprocess.run(["bash", str(tree["root"] / "cloud/hooks/session-start.sh")], env=e,
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_session_start_runs_the_gcp_status_when_a_project_is_set(tree: dict[str, Path]) -> None:
    assert "GCP-STATUS-RAN" in start(tree, GCP_PROJECT="lab")
    assert "GCP-STATUS-RAN" not in start(tree)


def test_session_start_honours_the_targets_opt_out(tree: dict[str, Path]) -> None:
    (tree["target"] / "docs/agents").mkdir(parents=True)
    (tree["target"] / "docs/agents/no-session-gcp").write_text("this repo uses a project of its own\n")
    out = start(tree, GCP_PROJECT="lab")
    assert "GCP-STATUS-RAN" not in out
    [line] = [x for x in out.splitlines() if "GCP status skipped" in x]
    assert "target declines the session's GCP project" in line
    assert "this repo uses a project of its own" in line
    assert "GCP status skipped" not in start(tree)  # no project, nothing to say


def test_session_start_repeats_an_unresolved_save_work_skip(tree: dict[str, Path]) -> None:
    log = tree["home"] / ".claude/save-work.log"
    log.write_text(
        "2000-01-01T00:00Z /home/user/a (main) -> claude/wip/main-s1 1234abcd\n"
        "2000-01-01T00:01Z SKIPPED /home/user/a (main): gitleaks found a secret in the work to push\n"
        "2000-01-01T00:02Z SKIPPED /home/user/b (dev): gitleaks found a secret in the work to push\n"
        "2000-01-01T00:03Z /home/user/b (dev) -> claude/wip/dev-s1 5678abcd\n"
    )
    [line] = [x for x in start(tree).splitlines() if "save-work did not push" in x]
    assert "SKIPPED /home/user/a (main)" in line
    with log.open("a") as f:
        f.write("2000-01-01T00:04Z /home/user/a (main) -> claude/wip/main-s1 9abcdef0\n")
    assert "save-work did not push" not in start(tree)

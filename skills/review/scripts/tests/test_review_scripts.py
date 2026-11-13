"""The review skill's recording scripts (gate_stamp.sh, verdict.sh) against a stub `gh` (stub_gh.py).

Nothing reaches GitHub: the stub answers reads from files and records every write.
Run: uvx --from pytest==8.4.2 pytest -q skills/review/scripts/tests
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
STUB = Path(__file__).resolve().parent / "stub_gh.py"
NAMES = ("lib.sh", "gate_stamp.sh", "verdict.sh")
UVX = shutil.which("uvx")
SHELLCHECK_PY_VERSION = "0.11.0.1"
HEAD = "a" * 40


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").symlink_to(STUB)
    STUB.chmod(0o755)
    fx = tmp_path / "fx"
    fx.mkdir()
    e = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_DIR": str(fx),
        "REVIEW_REPO": "example-owner/example-repo",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for k in ("DRY_RUN", "STUB_FAIL", "STUB_MANGLE"):
        e.pop(k, None)
    return e


def calls(env: dict[str, str]) -> list[dict]:
    p = Path(env["STUB_DIR"]) / "calls.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def writes(env: dict[str, str]) -> list[dict]:
    return [c for c in calls(env) if c["method"] != "GET"]


@pytest.fixture
def repo(tmp_path: Path, env: dict[str, str]) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "remote", "add", "origin", "https://github.com/example-owner/example-repo.git")
    (r / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=r, check=True, env=env)
    (Path(env["STUB_DIR"]) / "known.txt").write_text(git(r, "rev-parse", "HEAD") + "\n")
    return r


def stamp(repo: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPTS / "gate_stamp.sh"), *args], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=60)


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


def test_gate_stamp_records_success_on_the_head(repo: Path, env: dict[str, str]) -> None:
    head = git(repo, "rev-parse", "HEAD")
    done = stamp(repo, env, "--", "bash", "-c", "echo running; echo '12 passed in 0.3s'")
    assert done.returncode == 0, done.stderr
    [w] = writes(env)
    assert w["endpoint"] == f"repos/example-owner/example-repo/statuses/{head}"
    assert w["fields"]["context"] == "loadout/gates"
    assert w["fields"]["state"] == "success"
    assert "bash -c" in w["fields"]["description"] and "12 passed in 0.3s" in w["fields"]["description"]
    assert f"Gates on {head}, recorded as `loadout/gates: success`" in done.stdout
    assert "exit 0" in done.stdout and "12 passed in 0.3s" in done.stdout


def test_gate_stamp_records_failure_and_keeps_the_exit_code(repo: Path, env: dict[str, str]) -> None:
    done = stamp(repo, env, "--context", "loadout/gates", "--", "bash", "-c", "echo '1 failed'; exit 4")
    assert done.returncode == 4
    [w] = writes(env)
    assert w["fields"]["state"] == "failure"
    assert "1 failed" in w["fields"]["description"]
    assert "exit 4" in done.stdout


def test_gate_stamp_clips_the_description(repo: Path, env: dict[str, str]) -> None:
    done = stamp(repo, env, "--", "bash", "-c", "printf 'x%.0s' {1..500}; echo")
    assert done.returncode == 0
    assert len(writes(env)[0]["fields"]["description"]) <= 140


def test_gate_stamp_refuses_a_dirty_tree(repo: Path, env: dict[str, str]) -> None:
    (repo / "new.txt").write_text("untracked\n")
    done = stamp(repo, env, "--", "touch", str(repo / "ran"))
    assert done.returncode == 2
    assert "uncommitted changes" in done.stderr
    assert not (repo / "ran").exists() and writes(env) == []


def test_gate_stamp_refuses_a_modified_tracked_file(repo: Path, env: dict[str, str]) -> None:
    (repo / "a.txt").write_text("changed\n")
    assert stamp(repo, env, "--", "true").returncode == 2
    assert writes(env) == []


def test_gate_stamp_refuses_an_unpushed_head(repo: Path, env: dict[str, str]) -> None:
    (repo / "b.txt").write_text("b\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "local only"], cwd=repo, check=True, env=env)
    done = stamp(repo, env, "--", "touch", str(repo.parent / "ran"))
    assert done.returncode == 2
    assert "push the branch first" in done.stderr
    assert not (repo.parent / "ran").exists() and writes(env) == []


def test_gate_stamp_refuses_a_command_that_moves_head(repo: Path, env: dict[str, str]) -> None:
    done = stamp(repo, env, "--", "git", "commit", "-q", "--allow-empty", "-m", "sneaky")
    assert done.returncode == 2
    assert "moved HEAD" in done.stderr and writes(env) == []


def test_gate_stamp_dry_run_posts_nothing(repo: Path, env: dict[str, str]) -> None:
    done = stamp(repo, env, "--dry-run", "--", "true")
    assert done.returncode == 0
    assert writes(env) == []
    assert "dry-run: gh api -X POST repos/example-owner/example-repo/statuses/" in done.stderr
    assert "dry run: not posted" in done.stdout


def test_gate_stamp_exits_3_when_the_record_fails(repo: Path, env: dict[str, str]) -> None:
    done = stamp(repo, {**env, "STUB_FAIL": "/statuses/"}, "--", "true")
    assert done.returncode == 3
    assert "NOT recorded" in done.stdout


# verdict.sh


@pytest.fixture
def pr(env: dict[str, str]) -> Path:
    fx = Path(env["STUB_DIR"])
    (fx / "pr.json").write_text(json.dumps({"number": 12, "head": {"sha": HEAD}}))
    return fx


def verdict(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPTS / "verdict.sh"), *args], env=env, capture_output=True,
                          text=True, timeout=60, cwd=SCRIPTS)


def status_write(env: dict[str, str]) -> dict:
    [w] = [c for c in writes(env) if "/statuses/" in c["endpoint"]]
    return w


def test_verdict_pass_posts_the_raw_output_and_records_success(pr: Path, env: dict[str, str],
                                                                tmp_path: Path) -> None:
    out = tmp_path / "review.txt"
    out.write_text("No findings.\n```\nquoted fence\n```\n")
    done = verdict(env, "12", "--tier", "standard", "--result", "pass", "--reviewers", "fresh-reviewer",
                   "--file", str(out))
    assert done.returncode == 0, done.stderr
    body = (pr / "comment.txt").read_text()
    assert body.startswith("🤖 Review: pass (standard tier)")
    assert f"`{HEAD}`" in body and "fresh-reviewer" in body
    assert "<details>" in body and "No findings." in body
    assert "````text\n" in body  # a longer fence than any in the output
    w = status_write(env)
    assert w["endpoint"].endswith(f"/statuses/{HEAD}")
    assert w["fields"]["context"] == "loadout/review" and w["fields"]["state"] == "success"
    assert w["fields"]["target_url"].endswith("#issuecomment-7")


def test_verdict_fail_records_failure(pr: Path, env: dict[str, str], tmp_path: Path) -> None:
    out = tmp_path / "review.txt"
    out.write_text("BLOCKER: the guard fails open.\n")
    done = verdict(env, "12", "--tier", "sensitive", "--result", "fail", "--reviewers", "a, b",
                   "--file", str(out))
    assert done.returncode == 0, done.stderr
    assert (pr / "comment.txt").read_text().startswith("🤖 Review: fail (sensitive tier)")
    assert status_write(env)["fields"]["state"] == "failure"


def test_verdict_routine_needs_no_reviewer(pr: Path, env: dict[str, str]) -> None:
    done = verdict(env, "12", "--tier", "routine")
    assert done.returncode == 0, done.stderr
    body = (pr / "comment.txt").read_text()
    assert body.startswith("🤖 Review: pass (routine tier)")
    assert "needs gates only" in body and "<details>" not in body
    assert status_write(env)["fields"]["state"] == "success"


def test_verdict_standard_without_output_is_refused(pr: Path, env: dict[str, str]) -> None:
    done = verdict(env, "12", "--tier", "standard", "--result", "pass", "--reviewers", "x")
    assert done.returncode == 2 and "--file" in done.stderr
    assert writes(env) == []


def test_verdict_clips_output_to_the_comment_limit(pr: Path, env: dict[str, str], tmp_path: Path) -> None:
    out = tmp_path / "review.txt"
    out.write_text("é" * 70000 + "\nEND\n")
    done = verdict(env, "12", "--tier", "standard", "--result", "pass", "--reviewers", "x", "--file", str(out))
    assert done.returncode == 0, done.stderr
    body = (pr / "comment.txt").read_text()
    assert len(body) <= 65536
    assert "Clipped to fit GitHub's comment size" in body and "END" not in body
    assert body.rstrip().endswith("</details>")


def test_verdict_read_back_mismatch_fails_without_a_status(pr: Path, env: dict[str, str],
                                                           tmp_path: Path) -> None:
    out = tmp_path / "review.txt"
    out.write_text("fine\n")
    done = verdict({**env, "STUB_MANGLE": "1"}, "12", "--tier", "standard", "--result", "pass",
                   "--reviewers", "x", "--file", str(out))
    assert done.returncode != 0
    assert "does not hold the body that was sent" in done.stderr
    assert [c for c in writes(env) if "/statuses/" in c["endpoint"]] == []


def test_verdict_dry_run_posts_nothing(pr: Path, env: dict[str, str]) -> None:
    done = verdict(env, "12", "--tier", "routine", "--dry-run")
    assert done.returncode == 0, done.stderr
    assert writes(env) == []
    assert "dry-run: gh api -X POST repos/example-owner/example-repo/issues/12/comments" in done.stderr
    assert "dry-run: gh api -X POST repos/example-owner/example-repo/statuses/" + HEAD in done.stderr

"""The process-id check (`cloud/githooks/check-process-ids.py`) on throwaway repos.

Each test commits a baseline, stages a change, and runs the check the way the pre-commit hook does:
what it refuses (issue, PR, work-label and decision ids on added lines; record files in a repo on the
ways), and what it must leave alone (colours, anchors, shell, versions, standards, calls, upstream
links, lockfiles, vendored, generated and binary files, history, allowlisted tokens and paths).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parent.parent / "check-process-ids.py"
GIT = shutil.which("git") or "/usr/bin/git"
OPT_IN = "Ways of working: [ways](https://github.com/example-owner/example-collection/tree/main/ways)\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 (fixed arguments)
        [GIT, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "remote", "add", "origin", "https://github.com/example-owner/example-repo.git")
    (tmp_path / "README.md").write_text("# Example\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _stage(repo: Path, files: dict[str, str | bytes]) -> None:
    for name, body in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            f.write_bytes(body)
        else:
            f.write_text(body)
    _git(repo, "add", "-A")


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed arguments)
        [sys.executable, str(CHECK), *args, str(repo)], capture_output=True, text=True, timeout=60,
    )


REFUSED = {
    "a bare hash and number": "# Retry once (#123).\n",
    "an issue word": "# Fixed as issue 42 asked.\n",
    "an issue hash": "Tracked in issue #42.\n",
    "a PR": "# Restored by PR 17.\n",
    "a relative tracker link": "See [the bug](../../issues/5).\n",
    "this repo's tracker url": "<https://github.com/example-owner/example-repo/pull/9>\n",
    "a phase label": "## Phase 2: streaming\n",
    "a phase identifier": "def test_phase3_ingest():\n    pass\n",
    "a milestone": "# Milestone 4 adds retries.\n",
    "a sprint": "Done in sprint 12.\n",
    "a decision record": "# Tags are immutable (ADR-0038).\n",
    "a register id in parentheses": "# Image tags name their content (D16).\n",
    "a register id opening a comment": "# D12: retries live in the orchestrator, not here.\n",
    "a register id after a plan file": "# Off (PLAN.md D26): nothing runs on its own.\n",
    "a list of register ids": "# Keyless identities (M7, WC-5).\n",
    "a register id after see": "Masking follows the policy; see SL-3.\n",
    "a stage label": "Lessons for GKE (Stage 2) and Composer (Stage 3).\n",
}


@pytest.mark.parametrize("line", REFUSED.values(), ids=REFUSED.keys())
def test_refuses_an_added_process_id(repo: Path, line: str) -> None:
    _stage(repo, {"src/app.py": line})
    done = _run(repo)
    assert done.returncode == 1, done.stdout
    assert "src/app.py:" in done.stdout
    assert "commit message or the PR body" in done.stderr


ALLOWED = {
    "hex colours in css": ("web/site.css", ".a { color: #333; background: #123456; }\n#123 { }\n"),
    "hex colours in markup": ("web/page.html", '<rect fill="#000000"/><p style="color:#111">x</p>\n'),
    "hex colours in script": ("web/chart.js", "const palette = ['#111', '#222222'];\nline.stroke = '#333';\n"),
    "svg path commands": ("web/icon.svg", '<path d="M4 12 L20 12 M12 4 L12 20"/>\n'),
    "markdown headings and anchors": ("docs/a.md", "## Setup\n\nSee [setup](#setup) and [steps](b.md#12-steps).\n"),
    "shell comments and shebang": ("bin/x.sh", "#!/usr/bin/env bash\n# count\nn=${#arr[@]}; echo $#\n"),
    "shell arithmetic": ("bin/y.sh", 'curl -r $((L-8))-$((L-1)) "$U"\n'),
    "html entities": ("docs/e.html", "<p>&#123; and &#x7b;</p>\n"),
    "url fragments": ("docs/u.md", "Read <https://example.com/guide#1> and https://example.com/a#section-2.\n"),
    "versions": ("docs/v.md", "Needs Python 3.12, node-22, v1.2.3 and kubernetes 1.36.\n"),
    "standards": ("docs/s.md", "Dates are ISO-8601 (ISO-8601), text UTF-8 (UTF-8), hashes SHA-256 (SHA-256),\n"
                  "issuer per RFC 9207, transport HTTP-2 (HTTP-2), curve (P-256), keys (CVE-2024-1234).\n"),
    "well-known tokens": ("docs/t.md", "Store it in S3 (S3), on WSL2 (WSL2), licensed (CC0), p99 (P99) in Q4 (Q4).\n"),
    "a call with constants": ("src/c.py", 'await window.admit(APP, "a", T0)\nf(X, Y2)\n'),
    "linter codes": ("src/d.py", 'run(cmd)  # noqa: S603\n', ),
    "linter config": ("pyproject.toml", '[tool.ruff.lint]\nignore = ["D203", "E501"]\n'),
    "an upstream issue link": ("src/w.py", "# Works around https://github.com/other/proj/issues/12.\n"),
    "a docker build's stages": ("Dockerfile", "# Stage 1 builds the page; stage 2 runs it.\nFROM x AS build\n"),
    "a step in a procedure": ("docs/p.md", "Step 3: run the tests.\n"),
    "a ref-ok fixture line": ("tests/test_x.py", 'BODY = "Closes #1"  # ref-ok\n'),
    "a lockfile": ("uv.lock", "# see #12 (ADR-0001)\n"),
    "a vendored file": ("vendor/lib.js", "// fixed in #12 (Phase 2)\n"),
    "a minified file": ("web/app.min.js", "/* #12 */\n"),
    "a generated file": ("gen/api.py", "# Code generated by protoc. DO NOT EDIT.\n# see #12\n"),
    "a changelog": ("CHANGELOG.md", "## 1.2.0\n- Faster start (#12).\n"),
    "a binary file": ("img/x.png", b"\x89PNG\x00\x00#12 Phase 2\x00"),
    "pr images": (".pr-images/pr-12/after.png", b"\x89PNG\x00"),
}


@pytest.mark.parametrize(("path", "body"), ALLOWED.values(), ids=ALLOWED.keys())
def test_leaves_legitimate_text_alone(repo: Path, path: str, body: str | bytes) -> None:
    _stage(repo, {path: body})
    done = _run(repo)
    assert done.returncode == 0, done.stdout + done.stderr


def test_checks_only_added_lines(repo: Path) -> None:
    _stage(repo, {"src/old.py": "# Legacy note (#7).\nx = 1\n"})
    _git(repo, "commit", "-q", "--no-verify", "-m", "old")
    _stage(repo, {"src/old.py": "# Legacy note (#7).\nx = 2\n"})
    assert _run(repo).returncode == 0


def test_allowlist_and_skipped_paths(repo: Path) -> None:
    (repo / ".process-ids").write_text("# product codes\nE-0*\npath: fixtures/*\n")
    _stage(repo, {"src/q.sql": "-- late events (E-0011, E-0012)\n", "fixtures/deep/f.sql": "-- (#12)\n"})
    assert _run(repo).returncode == 0
    _stage(repo, {"src/r.sql": "-- returns (R-1)\n"})
    assert _run(repo).returncode == 1


def test_an_id_in_a_new_file_name(repo: Path) -> None:
    _stage(repo, {"tests/e2e/phase5-check.sh": "echo ok\n"})
    done = _run(repo)
    assert done.returncode == 1
    assert "phase5" in done.stdout


def test_record_files_only_in_a_repo_on_the_ways(repo: Path) -> None:
    records = {"PLAN.md": "x\n", "docs/ROADMAP.md": "x\n", "docs/migration-plan.md": "x\n",
               "docs/adr/use-postgres.md": "x\n", "ledger.d/fragment.md": "x\n", "LESSONS.md": "x\n"}
    _stage(repo, records)
    assert _run(repo).returncode == 0  # not opted in: a repo's own plan files are its call
    (repo / "CLAUDE.md").write_text(OPT_IN)
    done = _run(repo)
    assert done.returncode == 1
    for name in records:
        assert f"{name}: [record file" in done.stdout, name
    assert "on the tracker" in done.stderr


def test_record_file_rule_leaves_product_files_alone(repo: Path) -> None:
    (repo / "CLAUDE.md").write_text(OPT_IN)
    _stage(repo, {"src/billing/plan.py": "x = 1\n", "docs/planner.md": "x\n", "CHANGELOG.md": "x\n",
                  "docs/architecture.md": "x\n"})
    assert _run(repo).returncode == 0, _run(repo).stdout


def test_names_setting_overrides_detection(repo: Path) -> None:
    (repo / ".process-ids").write_text("names: on\n")
    _stage(repo, {"TODO.md": "x\n"})
    assert _run(repo).returncode == 1


def test_range_and_all_modes(repo: Path) -> None:
    _stage(repo, {"src/a.py": "# keep (D4)\n"})
    _git(repo, "commit", "-q", "--no-verify", "-m", "a")
    assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 1
    assert _run(repo, "--range", "HEAD~1..HEAD~1").returncode == 0
    done = _run(repo, "--all")
    assert done.returncode == 1
    assert "src/a.py:1: [D4]" in done.stdout

"""The autopilot skill's mechanical steps as scripts (`scripts/`).

The skill's SKILL.md stays the spec; each script does one step through `gh api` (REST only)
and prints every write under `--dry-run`. The tests run the dry runs against a stub `gh` that
answers reads from fixtures and refuses writes, so nothing reaches GitHub.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "/usr/bin/git"
DATE = shutil.which("date") or "/bin/date"
NAMES = ("lib.sh", "claim.sh", "file_issue.sh", "merge.sh")
SHELLCHECK_PY_VERSION = "0.11.0.1"  # shellcheck 0.11.0 from PyPI through `uvx`
UVX = shutil.which("uvx")

STUB_GH = """#!/usr/bin/env bash
# `gh api <endpoint> [--jq expr]`: reads answer from $STUB_DIR/<fixture>.json; a write fails loudly,
# unless STUB_WRITES is set: then it is logged to $STUB_DIR/writes.log and answers write.json.
# A call whose arguments contain $STUB_FAIL_ON fails the way gh does on a 502 error page.
set -euo pipefail
[ -z "${STUB_FAIL:-}" ] || { echo '{"message":"Not Found"}'; exit 1; }
shift
all="$*" ep="" jq="" write=""
if [ -n "${STUB_FAIL_ON:-}" ] && [[ "$all" == *"$STUB_FAIL_ON"* ]]; then
  echo "invalid character 'b' looking for beginning of value" >&2; exit 1
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --jq) jq="$2"; shift ;;
    -X|-f|-F)
      [ -n "${STUB_WRITES:-}" ] || { echo "stub gh: write refused: $*" >&2; exit 9; }
      write=1; shift ;;
    *) ep="$1" ;;
  esac
  shift
done
if [ -n "$write" ]; then
  echo "$all" >>"$STUB_DIR/writes.log"
  f=write.json
  if [ -n "$jq" ]; then jq -r "$jq" "$STUB_DIR/$f"; else cat "$STUB_DIR/$f"; fi
  exit 0
fi
case "$ep" in
  */commits/*/status*) f=status.json ;;
  */compare/*) f=compare.json ;;
  *pulls/*) f=pr.json ;;
  */comments*) f=comments.json ;;
  */issues/*) f=issue.json ;;
  *) echo "stub gh: no fixture for $ep" >&2; exit 9 ;;
esac
if [ -n "$jq" ]; then jq -r "$jq" "$STUB_DIR/$f"; else cat "$STUB_DIR/$f"; fi
"""


def test_scripts_exist_and_are_executable() -> None:
    for name in NAMES:
        path = SCRIPTS / name
        assert path.is_file(), name
        if name != "lib.sh":
            assert os.access(path, os.X_OK), f"{name} is not executable"


def test_bash_n_clean() -> None:
    for name in NAMES:
        subprocess.run([BASH, "-n", str(SCRIPTS / name)], check=True, timeout=30)  # noqa: S603


@pytest.mark.skipif(UVX is None, reason="uvx not installed")
def test_shellcheck_clean() -> None:
    assert UVX
    done = subprocess.run(  # noqa: S603 (fixed arguments)
        [
            UVX,
            "--from",
            f"shellcheck-py=={SHELLCHECK_PY_VERSION}",
            "shellcheck",
            "-x",
            "-P",
            str(ROOT),
        ]
        + [str(SCRIPTS / n) for n in NAMES],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr


HEAD = "a" * 40
PR = {
    "number": 70,
    "state": "open",
    "draft": False,
    "title": "Add the exporter",
    "base": {"ref": "main"},
    "head": {"sha": HEAD, "ref": "claude/12-exporter"},
    "labels": [{"name": "agent:claimed"}],
}
STATUS_GREEN = {
    "state": "success",
    "statuses": [
        {"context": "loadout/review", "state": "success"},
        {"context": "loadout/gates", "state": "success"},
        {"context": "loadout/gates", "state": "failure"},
    ],
}


@pytest.fixture
def stub(tmp_path: Path) -> dict[str, str]:
    """A PATH with the stub `gh` first and a fixture dir with the default answers."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(STUB_GH)
    gh.chmod(0o755)
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "comments.json").write_text("[]")
    (fx / "pr.json").write_text(json.dumps(PR))
    (fx / "status.json").write_text(json.dumps(STATUS_GREEN))
    (fx / "compare.json").write_text(json.dumps({"behind_by": 0, "ahead_by": 2}))
    (fx / "issue.json").write_text(json.dumps({"id": 123, "number": 5}))
    (fx / "write.json").write_text(json.dumps({"id": 99}))
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_DIR": str(fx),
        "WAKE_ID": "",
        "AUTOPILOT_REPO": "example-owner/example-repo",
    }
    env.pop("DRY_RUN", None)
    env.pop("AUTOPILOT_HOLD_LABELS", None)
    return env


def run(
    script: str, *args: str, env: dict[str, str], cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (our scripts)
        [str(SCRIPTS / script), *args], capture_output=True, text=True, timeout=60, env=env, cwd=cwd
    )


def test_claim_dry_run_prints_the_label_and_the_comment(stub: dict[str, str]) -> None:
    done = run("claim.sh", "257", "--wake", "abcd1234", "--dry-run", env=stub)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "abcd1234"
    assert "-X POST repos/example-owner/example-repo/issues/257/labels" in done.stderr
    assert "labels\\[\\]=agent:claimed" in done.stderr
    assert "issues/257/comments" in done.stderr and "claimed 20" in done.stderr
    assert "abcd1234" in done.stderr


def test_claim_yields_to_a_live_claim_and_ignores_a_stale_one(stub: dict[str, str]) -> None:
    fx = Path(stub["STUB_DIR"])
    stamp = subprocess.run(  # noqa: S603 (fixed arguments)
        [DATE, "-u", "+%FT%H:%MZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    fx.joinpath("comments.json").write_text(
        json.dumps([{"id": 1, "body": f"claimed {stamp} deadbeef"}])
    )
    held = run("claim.sh", "257", "--wake", "abcd1234", "--dry-run", env=stub)
    assert held.returncode == 2 and held.stdout.strip() == "deadbeef", held.stderr
    assert "dry-run: gh api" not in held.stderr, "a held issue gets no label or comment"
    # A handoff after the claim ends it; a claim over 3 hours old is stale.
    fx.joinpath("comments.json").write_text(
        json.dumps(
            [
                {"id": 1, "body": f"claimed {stamp} deadbeef"},
                {"id": 2, "body": "## Handoff\nleft for the next wake"},
                {"id": 3, "body": "claimed 2026-10-20T00:00Z feedface"},
            ]
        )
    )
    free = run("claim.sh", "257", "--wake", "abcd1234", "--dry-run", env=stub)
    assert free.returncode == 0 and free.stdout.strip() == "abcd1234", free.stderr


def test_claim_keeps_its_claim_over_one_a_handoff_ended(stub: dict[str, str]) -> None:
    """The re-read after posting ignores a claim a handoff ended, however recent it is."""
    fx = Path(stub["STUB_DIR"])
    stamp = subprocess.run(  # noqa: S603 (fixed arguments)
        [DATE, "-u", "+%FT%H:%MZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    fx.joinpath("comments.json").write_text(
        json.dumps(
            [
                {"id": 1, "body": f"🤖 claimed {stamp} deadbeef"},
                {"id": 2, "body": "🤖 Handoff — wake deadbeef\n\nPR opened"},
                {"id": 99, "body": f"🤖 claimed {stamp} abcd1234"},
            ]
        )
    )
    done = run("claim.sh", "7", "--wake", "abcd1234", env={**stub, "STUB_WRITES": "1"})
    assert done.returncode == 0 and done.stdout.strip() == "abcd1234", done.stderr
    assert "DELETE" not in fx.joinpath("writes.log").read_text()
    # Without the handoff the earlier live claim still wins and ours is deleted.
    fx.joinpath("comments.json").write_text(
        json.dumps(
            [
                {"id": 1, "body": f"🤖 claimed {stamp} deadbeef"},
                {"id": 99, "body": f"🤖 claimed {stamp} abcd1234"},
            ]
        )
    )
    fx.joinpath("writes.log").unlink()
    lost = run("claim.sh", "7", "--wake", "abcd1234", env={**stub, "STUB_WRITES": "1"})
    assert lost.returncode == 2 and lost.stdout.strip() == "deadbeef", lost.stderr
    assert "-X DELETE repos/example-owner/example-repo/issues/comments/99" in fx.joinpath(
        "writes.log"
    ).read_text()


def test_claim_carries_the_session_and_reads_the_robot_prefix(stub: dict[str, str]) -> None:
    fx = Path(stub["STUB_DIR"])
    stamp = subprocess.run(  # noqa: S603 (fixed arguments)
        [DATE, "-u", "+%FT%H:%MZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    url = "https://claude.ai/code/session_x"
    done = run("claim.sh", "7", "--wake", "abcd1234", "--session", url, "--dry-run", env=stub)
    assert done.returncode == 0, done.stderr
    assert f"abcd1234 {url}" in done.stderr
    fx.joinpath("comments.json").write_text(
        json.dumps([{"id": 1, "body": f"🤖 claimed {stamp} deadbeef {url}"}])
    )
    held = run("claim.sh", "7", "--wake", "abcd1234", "--dry-run", env=stub)
    assert held.returncode == 2 and held.stdout.strip() == "deadbeef", held.stderr
    fx.joinpath("comments.json").write_text(
        json.dumps(
            [
                {"id": 1, "body": f"🤖 claimed {stamp} deadbeef"},
                {"id": 2, "body": "🤖 Handoff — left for the next wake"},
            ]
        )
    )
    free = run("claim.sh", "7", "--wake", "abcd1234", "--dry-run", env=stub)
    assert free.returncode == 0, free.stderr


def _patched_body(stderr: str, marker: str = "-X PATCH") -> str:
    """The `body=` value of the dry run's `marker` line, unquoted the way bash's `%q` wrote it."""
    line = next(ln for ln in stderr.splitlines() if marker in ln)
    words = line.removeprefix("dry-run: gh api")
    script = 'eval "set -- $1"; for a; do case $a in body=*) printf %s "${a#body=}";; esac; done'
    unquoted = subprocess.run(  # noqa: S603 (bash unquotes its own %q output)
        [BASH, "-c", script, "_", words], capture_output=True, text=True, check=True
    )
    return unquoted.stdout


def test_file_issue_uses_the_template_and_places_the_sub_issue(stub: dict[str, str]) -> None:
    args = ["--epic", "27", "--title", "Do x", "--context", "ADR-0038", "--do", "thing"]
    args += [
        "--acceptance",
        "test passes",
        "--label",
        "agent:ready",
        "--before",
        "260",
        "--dry-run",
    ]
    done = run("file_issue.sh", *args, env=stub)
    assert done.returncode == 0, done.stderr
    for heading in ("## Context", "## Do", "## Acceptance", "## Blocked by\n- none"):
        assert heading in done.stderr, heading
    assert "labels\\[\\]=agent:ready" in done.stderr
    assert "issues/27/sub_issues -F sub_issue_id=" in done.stderr
    assert "sub_issues/priority" in done.stderr and "before_id=123" in done.stderr
    missing = run("file_issue.sh", "--epic", "27", "--title", "Do x", "--dry-run", env=stub)
    assert missing.returncode == 1 and "usage" in missing.stderr


def test_file_issue_keeps_multi_line_arguments_whole(stub: dict[str, str]) -> None:
    """A newline inside `--context` or `--do` stays in its value."""
    args = ["--epic", "27", "--title", "Do x", "--context", "line one\nline two"]
    args += ["--do", "step one\nstep two", "--acceptance", "test passes", "--dry-run"]
    done = run("file_issue.sh", *args, env=stub)
    assert done.returncode == 0, done.stderr
    body = _patched_body(done.stderr, "-X POST repos/example-owner/example-repo/issues ")
    assert "## Context\n- line one\n- line two\n" in body
    assert "## Do\n- step one\n- step two\n" in body


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 (fixed git arguments on a temp repo)
        [GIT, *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_claim_stops_when_the_comments_cannot_be_read(stub: dict[str, str]) -> None:
    """A failed read never claims blind over a claim it could not see."""
    done = run("claim.sh", "7", "--wake", "abcd1234", "--dry-run", env={**stub, "STUB_FAIL": "1"})
    assert done.returncode != 0
    assert "dry-run: gh api" not in done.stderr


COMMENT_POST = "-X POST repos/example-owner/example-repo/issues/7/comments"


def test_claim_takes_back_its_label_when_the_comment_fails(stub: dict[str, str]) -> None:
    """A comment that cannot be confirmed leaves no label behind and exits 1."""
    fx = Path(stub["STUB_DIR"])
    env = {**stub, "STUB_WRITES": "1", "STUB_FAIL_ON": COMMENT_POST}
    done = run("claim.sh", "7", "--wake", "abcd1234", env=env)
    assert done.returncode == 1, done.stderr
    writes = fx.joinpath("writes.log").read_text()
    assert "issues/7/labels -f labels[]=agent:claimed" in writes
    assert "-X DELETE repos/example-owner/example-repo/issues/7/labels/agent:claimed" in writes


def test_claim_keeps_a_comment_that_landed_although_its_answer_was_lost(
    stub: dict[str, str],
) -> None:
    fx = Path(stub["STUB_DIR"])
    stamp = subprocess.run(  # noqa: S603 (fixed arguments)
        [DATE, "-u", "+%FT%H:%MZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    fx.joinpath("comments.json").write_text(
        json.dumps([{"id": 99, "body": f"🤖 claimed {stamp} abcd1234"}])
    )
    env = {**stub, "STUB_WRITES": "1", "STUB_FAIL_ON": COMMENT_POST}
    done = run("claim.sh", "7", "--wake", "abcd1234", env=env)
    assert done.returncode == 0 and done.stdout.strip() == "abcd1234", done.stderr
    assert "DELETE" not in fx.joinpath("writes.log").read_text()


def test_claim_leaves_no_label_when_labelling_fails(stub: dict[str, str]) -> None:
    fx = Path(stub["STUB_DIR"])
    env = {**stub, "STUB_WRITES": "1", "STUB_FAIL_ON": "issues/7/labels -f"}
    done = run("claim.sh", "7", "--wake", "abcd1234", env=env)
    assert done.returncode == 1, done.stderr
    writes = fx.joinpath("writes.log").read_text()
    assert "comments" not in writes, "no claim comment after a failed label"
    assert "-X DELETE repos/example-owner/example-repo/issues/7/labels/agent:claimed" in writes


def test_file_issue_fails_when_the_create_answers_no_issue(stub: dict[str, str]) -> None:
    """An empty 200 from the create is no issue number to hand back."""
    Path(stub["STUB_DIR"], "write.json").write_text("")
    args = ["--title", "Do x", "--context", "c", "--do", "d", "--acceptance", "a"]
    done = run("file_issue.sh", *args, env={**stub, "STUB_WRITES": "1"})
    assert done.returncode == 1, done.stdout
    assert done.stdout.strip() == ""


def test_file_issue_without_an_epic_files_a_plain_issue(stub: dict[str, str]) -> None:
    args = ["--title", "Do x", "--context", "c", "--do", "d", "--acceptance", "a", "--dry-run"]
    done = run("file_issue.sh", *args, env=stub)
    assert done.returncode == 0, done.stderr
    assert "-X POST repos/example-owner/example-repo/issues " in done.stderr
    assert "sub_issues" not in done.stderr


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Owner/target",
        "https://github.com/Owner/target.git",
        "https://github.com/Owner/target/",
        "git@github.com:Owner/target.git",
        "http://local_proxy@127.0.0.1:1234/git/Owner/target",
    ],
)
def test_the_repo_comes_from_origin(tmp_path: Path, url: str) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", url)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AUTOPILOT_")}
    done = subprocess.run(  # noqa: S603 (our lib)
        [BASH, "-c", f'. {SCRIPTS / "lib.sh"}; echo "$REPO"'],
        capture_output=True, text=True, timeout=30, env=env, cwd=tmp_path,
    )
    assert done.stdout.strip() == "Owner/target", done.stderr


def test_the_scripts_refuse_to_target_their_own_clone(stub: dict[str, str]) -> None:
    env = {k: v for k, v in stub.items() if k != "AUTOPILOT_REPO"}
    done = run("claim.sh", "7", "--dry-run", env=env, cwd=SCRIPTS)
    assert done.returncode == 1 and "not the skill's own repo" in done.stderr


MERGE_PUT = "-X PUT repos/example-owner/example-repo/pulls/70/merge"


def test_merge_squashes_at_the_head_it_read_when_gated_and_reviewed(stub: dict[str, str]) -> None:
    done = run("merge.sh", "70", "--dry-run", env=stub)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "merged"
    assert MERGE_PUT in done.stderr
    assert "merge_method=squash" in done.stderr and f"sha={HEAD}" in done.stderr


def _merge_with(stub: dict[str, str], **changes: object) -> subprocess.CompletedProcess[str]:
    Path(stub["STUB_DIR"], "pr.json").write_text(json.dumps({**PR, **changes}))
    return run("merge.sh", "70", "--dry-run", env=stub)


@pytest.mark.parametrize(
    ("changes", "case"),
    [
        ({"draft": True}, "draft"),
        ({"base": {"ref": "claude/11-reader"}}, "stacked"),
        ({"labels": [{"name": "needs-local-verify"}]}, "held"),
        ({"labels": [{"name": "blocked: upstream"}, {"name": "needs-owner"}]}, "held"),
        ({"labels": [{"name": "needs-review"}]}, "held"),
        ({"title": "[speculative: #9 = B] Backfill thirty days"}, "held"),
    ],
    ids=["draft", "stacked", "local-verify", "needs-owner", "unreviewed-label", "speculative"],
)
def test_merge_writes_nothing_for_a_held_pr(
    stub: dict[str, str], changes: dict[str, object], case: str
) -> None:
    done = _merge_with(stub, **changes)
    assert done.returncode == 3, done.stderr
    assert done.stdout.strip() == case
    assert "dry-run: gh api" not in done.stderr


def test_merge_takes_the_profiles_hold_labels(stub: dict[str, str]) -> None:
    Path(stub["STUB_DIR"], "pr.json").write_text(
        json.dumps({**PR, "labels": [{"name": "needs-data-review"}]})
    )
    env = {**stub, "AUTOPILOT_HOLD_LABELS": "needs-data-review"}
    done = run("merge.sh", "70", "--dry-run", env=env)
    assert done.returncode == 3 and done.stdout.strip() == "held", done.stderr


@pytest.mark.parametrize(
    "statuses",
    [
        [{"context": "loadout/gates", "state": "success"}],
        [{"context": "loadout/review", "state": "success"}],
        [
            {"context": "loadout/gates", "state": "success"},
            {"context": "loadout/review", "state": "failure"},
        ],
        [
            {"context": "loadout/gates", "state": "pending"},
            {"context": "loadout/review", "state": "success"},
        ],
    ],
    ids=["no-review", "no-gates", "review-failed", "gates-pending"],
)
def test_merge_needs_both_statuses_on_the_head(
    stub: dict[str, str], statuses: list[dict[str, str]]
) -> None:
    Path(stub["STUB_DIR"], "status.json").write_text(json.dumps({"statuses": statuses}))
    done = run("merge.sh", "70", "--dry-run", env=stub)
    assert done.returncode == 3 and done.stdout.strip() == "unreviewed", done.stderr
    assert "dry-run: gh api" not in done.stderr


def test_merge_sends_a_head_behind_the_base_back_for_gates_and_review(
    stub: dict[str, str],
) -> None:
    Path(stub["STUB_DIR"], "compare.json").write_text(json.dumps({"behind_by": 2}))
    done = run("merge.sh", "70", "--dry-run", env=stub)
    assert done.returncode == 4 and done.stdout.strip() == "behind", done.stderr
    assert "dry-run: gh api" not in done.stderr


@pytest.mark.parametrize(
    "fail_on", ["pulls/70", "/status", "/compare/"], ids=["pr", "status", "compare"]
)
def test_merge_writes_nothing_when_a_read_fails(stub: dict[str, str], fail_on: str) -> None:
    done = run("merge.sh", "70", env={**stub, "STUB_WRITES": "1", "STUB_FAIL_ON": fail_on})
    assert done.returncode == 1, done.stdout
    assert not Path(stub["STUB_DIR"], "writes.log").exists()


@pytest.mark.parametrize(
    "answer", ["", json.dumps({"number": 71}), json.dumps({**PR, "head": {}})],
    ids=["empty-200", "another-pr", "no-head"],
)
def test_merge_writes_nothing_on_a_pr_read_that_is_not_the_pr(
    stub: dict[str, str], answer: str
) -> None:
    Path(stub["STUB_DIR"], "pr.json").write_text(answer)
    done = run("merge.sh", "70", env={**stub, "STUB_WRITES": "1"})
    assert done.returncode == 1, done.stdout
    assert not Path(stub["STUB_DIR"], "writes.log").exists()


def test_merge_fails_when_the_merge_answers_no_merge(stub: dict[str, str]) -> None:
    """A refused or empty merge answer is a failure, never reported as merged."""
    fx = Path(stub["STUB_DIR"])
    fx.joinpath("write.json").write_text(json.dumps({"merged": False}))
    done = run("merge.sh", "70", env={**stub, "STUB_WRITES": "1"})
    assert done.returncode == 1 and done.stdout.strip() == "", done.stderr
    fx.joinpath("write.json").write_text(json.dumps({"merged": True, "sha": "b" * 40}))
    ok = run("merge.sh", "70", env={**stub, "STUB_WRITES": "1"})
    assert ok.returncode == 0 and ok.stdout.strip() == "merged", ok.stderr
    assert f"pulls/70/merge -f merge_method=squash -f sha={HEAD}" in fx.joinpath(
        "writes.log"
    ).read_text()


def test_a_value_naming_the_flag_is_no_dry_run(stub: dict[str, str]) -> None:
    """Only a whole `--dry-run` argument sets the dry run; a value that mentions it writes."""
    args = ["--title", "Add --dry-run to the purge", "--context", "c", "--do", "d"]
    done = run("file_issue.sh", *args, "--acceptance", "a", env=stub)
    assert "stub gh: write refused: -X POST" in done.stderr, done.stderr
    assert "dry-run: gh api" not in done.stderr
